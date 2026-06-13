#!/usr/bin/env python
"""Data-parallel driver for matched independent rollouts across a vLLM fleet.

Node 2 THROUGHPUT wrapper. It produces exactly the same thing as
``scripts/run_independent_rollouts.py`` — N independent rollouts per problem,
same prompt (``tts_sft.prompts``), same per-sample seeds (``seed + i``), same
output record schema — but fans the ``problems x N`` generations out
CONCURRENTLY and round-robin across MANY single-GPU vLLM endpoints so all GPUs
are used (the sibling script issues one request at a time against one endpoint).

It NEVER runs SqueezeEvolve and NEVER grades (grading is offline via
``scripts/eval_reachability.py``). Output record (one JSONL line per problem),
byte-for-byte compatible with the sibling script's ``build_record``::

    {"id","question","answer","responses":[...N...],"n_rollouts",
     "model","generation_params","source":"independent_rollouts"}

Resume: whole-problem (ids already in the output are skipped). Incremental: each
problem is appended as soon as all N of its samples return, so a crash keeps
completed problems. A problem with ANY failed sample (after retries) is NOT
written (never emit an under-budget record that would break compute-matching).
"""
from __future__ import annotations

import argparse
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from tts_sft.io_utils import append_jsonl, iter_jsonl, read_existing_ids  # noqa: E402
from tts_sft.openai_client import GenerationParams, OpenAIChatClient  # noqa: E402
from tts_sft.prompts import DEFAULT_MATH_PROMPT, build_math_user_message  # noqa: E402

logger = logging.getLogger("run_independent_rollouts_dp")


def build_record(*, sid, question, answer, responses, model, generation_params) -> dict:
    """IDENTICAL schema to scripts/run_independent_rollouts.py:build_record."""
    return {
        "id": sid,
        "question": question,
        "answer": answer,
        "responses": list(responses),
        "n_rollouts": len(responses),
        "model": model,
        "generation_params": dict(generation_params),
        "source": "independent_rollouts",
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path, help="Seed JSONL (id, question, answer?).")
    p.add_argument("--output", required=True, type=Path, help="Output JSONL (one record per problem).")
    p.add_argument("--model", required=True, help="Served model name (must match --served-model-name).")
    p.add_argument("--base-urls", required=True,
                   help="Comma-separated OpenAI-compatible endpoints, one per GPU replica.")
    p.add_argument("--api-key", default="EMPTY")
    p.add_argument("--n-samples", type=int, default=32, help="Independent rollouts per problem (N).")
    p.add_argument("--temperature", type=float, default=0.6)
    p.add_argument("--top-p", type=float, default=0.95)
    p.add_argument("--max-tokens", type=int, default=32768)
    p.add_argument("--seed", type=int, default=1234, help="Base seed; sample i uses seed+i.")
    p.add_argument("--concurrency", type=int, default=64, help="Max in-flight requests across the fleet.")
    p.add_argument("--max-retries", type=int, default=3, help="Per-request retries on transient errors.")
    p.add_argument("--request-timeout", type=float, default=600.0,
                   help="Per-request HTTP timeout (s). Raise for large --max-tokens at high concurrency "
                        "(full-cap thinking traces can exceed 600s when many share a GPU).")
    p.add_argument("--prompt-template", default=DEFAULT_MATH_PROMPT)
    p.add_argument("--system-prompt", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    if args.n_samples < 1:
        logger.error("--n-samples must be >= 1"); return 2
    if not args.input.exists():
        logger.error("Input not found: %s", args.input); return 2
    base_urls = [u.strip() for u in args.base_urls.split(",") if u.strip()]
    if not base_urls:
        logger.error("No endpoints in --base-urls"); return 2

    if args.overwrite and args.output.exists():
        logger.info("Overwrite: removing %s", args.output)
        args.output.unlink()
    already = read_existing_ids(args.output)
    if already:
        logger.info("Resume: %d ids already present in %s", len(already), args.output)

    seeds = list(iter_jsonl(args.input))
    if args.limit is not None:
        seeds = seeds[: args.limit]

    # One client per endpoint; the openai SDK client is safe to share across threads.
    clients = [OpenAIChatClient(model=args.model, base_url=u, api_key=args.api_key, timeout=args.request_timeout) for u in base_urls]

    gen_params = {
        "temperature": args.temperature, "top_p": args.top_p,
        "max_tokens": args.max_tokens, "n_samples": args.n_samples, "seed": args.seed,
    }

    # Valid, not-yet-done problems.
    valid: list[tuple[int, dict, str, str]] = []
    for qi, s in enumerate(seeds):
        sid = str(s.get("id", ""))
        q = s.get("question")
        if not sid or not isinstance(q, str):
            logger.warning("skip malformed seed: %r", s); continue
        if sid in already:
            continue
        valid.append((qi, s, sid, q))
    if not valid:
        logger.info("Nothing to do (all problems already present)."); return 0

    qmap = {qi: (s, sid, q) for (qi, s, sid, q) in valid}
    results: dict[int, list] = {qi: [None] * args.n_samples for (qi, _, _, _) in valid}
    tasks = [(qi, i) for (qi, _, _, _) in valid for i in range(args.n_samples)]
    logger.info("Dispatching %d generations (%d problems x %d) over %d endpoints, concurrency=%d",
                len(tasks), len(valid), args.n_samples, len(base_urls), args.concurrency)

    write_lock = threading.Lock()
    written: set[int] = set()

    def maybe_write(qi: int) -> None:
        resps = results[qi]
        if any(r is None for r in resps):
            return
        with write_lock:
            if qi in written:
                return
            s, sid, q = qmap[qi]
            answer = s.get("answer")
            answer = str(answer) if answer is not None else None
            append_jsonl(args.output, build_record(
                sid=sid, question=q, answer=answer, responses=resps,
                model=args.model, generation_params=gen_params))
            written.add(qi)
            logger.info("problem %s complete (%d samples) -> written", sid, args.n_samples)

    def run_task(task):
        qi, i = task
        _, sid, q = qmap[qi]
        user = build_math_user_message(q, template=args.prompt_template)
        msgs: list[dict[str, str]] = []
        if args.system_prompt:
            msgs.append({"role": "system", "content": args.system_prompt})
        msgs.append({"role": "user", "content": user})
        params = GenerationParams(
            temperature=args.temperature, top_p=args.top_p,
            max_tokens=args.max_tokens, seed=args.seed + i)
        client = clients[(qi * args.n_samples + i) % len(clients)]  # round-robin across the fleet
        last = None
        for _ in range(args.max_retries):
            try:
                return qi, i, client.chat(msgs, params)
            except Exception as e:  # noqa: BLE001
                last = e
        raise RuntimeError(f"id={sid} sample={i} failed after {args.max_retries} tries: {last}")

    done = 0
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [ex.submit(run_task, t) for t in tasks]
        for fut in as_completed(futs):
            try:
                qi, i, text = fut.result()
                results[qi][i] = text
                done += 1
                maybe_write(qi)
                if done % 16 == 0 or done == len(tasks):
                    logger.info("progress %d/%d generations", done, len(tasks))
            except Exception as e:  # noqa: BLE001
                failures.append(str(e))
                logger.error("%s", e)

    incomplete = [qmap[qi][1] for (qi, _, _, _) in valid if qi not in written]
    logger.info("Wrote %d/%d problems (N=%d each) -> %s", len(written), len(valid), args.n_samples, args.output)
    if incomplete:
        logger.error("INCOMPLETE (not written): %s", incomplete)
    if failures:
        logger.error("%d generation failures.", len(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
