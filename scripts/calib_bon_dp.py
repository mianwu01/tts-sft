#!/usr/bin/env python
"""Calibration BoN driver with rich per-sample logging (tokens + finish_reason).

Like run_independent_rollouts_dp.py (concurrent, round-robin over many vLLM
endpoints, incremental per-problem write, whole-problem resume), but calls the
OpenAI chat API directly so it can record, per sample: input/output/total tokens
and finish_reason (vLLM returns finish_reason="length" iff the generation hit
max_tokens — the authoritative cap-hit signal). top_k is set EXPLICITLY via
extra_body so it's unambiguous. NEVER runs SqueezeEvolve; never grades (grading
is offline). Output: one JSONL record per problem:

  {dataset, id, question, answer, model, generation_params,
   responses:[text...], sample_meta:[{sample_id,input_tokens,output_tokens,
   total_tokens,finish_reason}...]}
"""
from __future__ import annotations

import argparse, logging, sys, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
from tts_sft.io_utils import append_jsonl, iter_jsonl, read_existing_ids  # noqa: E402
from tts_sft.prompts import DEFAULT_MATH_PROMPT, build_math_user_message  # noqa: E402

logger = logging.getLogger("calib_bon_dp")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--dataset", required=True, help="Label stored on each record (e.g. aime/hmmt).")
    p.add_argument("--model", required=True)
    p.add_argument("--base-urls", required=True, help="Comma-separated OpenAI-compatible endpoints.")
    p.add_argument("--api-key", default="EMPTY")
    p.add_argument("--n-samples", type=int, default=16)
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--top-p", type=float, default=0.95)
    p.add_argument("--top-k", type=int, default=20)
    p.add_argument("--max-tokens", type=int, default=32768)
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--concurrency", type=int, default=48)
    p.add_argument("--request-timeout", type=float, default=7200.0)
    p.add_argument("--max-retries", type=int, default=3)
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()
    from openai import OpenAI

    if not args.input.exists():
        logger.error("Input not found: %s", args.input); return 2
    base_urls = [u.strip() for u in args.base_urls.split(",") if u.strip()]
    if not base_urls:
        logger.error("No --base-urls"); return 2
    if args.overwrite and args.output.exists():
        args.output.unlink()
    already = read_existing_ids(args.output)
    if already:
        logger.info("Resume: %d ids already present", len(already))

    clients = [OpenAI(base_url=u, api_key=args.api_key, timeout=args.request_timeout) for u in base_urls]
    gp = {"temperature": args.temperature, "top_p": args.top_p, "top_k": args.top_k,
          "max_tokens": args.max_tokens, "seed": args.seed, "n_samples": args.n_samples}

    seeds = [s for s in iter_jsonl(args.input)
             if str(s.get("id", "")) and isinstance(s.get("question"), str) and str(s.get("id")) not in already]
    if not seeds:
        logger.info("Nothing to do."); return 0
    qmap = {str(s["id"]): s for s in seeds}
    results = {str(s["id"]): [None] * args.n_samples for s in seeds}  # (text, meta) tuples
    tasks = [(str(s["id"]), i) for s in seeds for i in range(args.n_samples)]
    logger.info("Dispatching %d generations (%d problems x %d) over %d endpoints, concurrency=%d, temp=%s top_k=%s max_tokens=%d",
                len(tasks), len(seeds), args.n_samples, len(base_urls), args.concurrency,
                args.temperature, args.top_k, args.max_tokens)

    write_lock = threading.Lock(); written = set()

    def maybe_write(sid):
        r = results[sid]
        if any(x is None for x in r):
            return
        with write_lock:
            if sid in written:
                return
            s = qmap[sid]; gold = s.get("answer")
            append_jsonl(args.output, {
                "dataset": args.dataset, "id": sid, "question": s.get("question"),
                "answer": str(gold) if gold is not None else None, "model": args.model,
                "generation_params": dict(gp),
                "responses": [t for (t, m) in r],
                "sample_meta": [m for (t, m) in r],
            })
            written.add(sid)
            logger.info("problem %s complete (%d samples) -> written", sid, args.n_samples)

    def run_task(task):
        sid, i = task
        msgs = [{"role": "user", "content": build_math_user_message(qmap[sid]["question"], template=DEFAULT_MATH_PROMPT)}]
        client = clients[(hash(sid) + i) % len(clients)]
        last = None
        for _ in range(args.max_retries):
            try:
                resp = client.chat.completions.create(
                    model=args.model, messages=msgs, temperature=args.temperature,
                    top_p=args.top_p, max_tokens=args.max_tokens, seed=args.seed + i,
                    extra_body={"top_k": args.top_k})
                ch = resp.choices[0]
                u = resp.usage
                meta = {"sample_id": i,
                        "input_tokens": getattr(u, "prompt_tokens", None),
                        "output_tokens": getattr(u, "completion_tokens", None),
                        "total_tokens": getattr(u, "total_tokens", None),
                        "finish_reason": ch.finish_reason}
                return sid, i, (ch.message.content or "", meta)
            except Exception as e:  # noqa: BLE001
                last = e
        raise RuntimeError(f"id={sid} sample={i} failed after {args.max_retries}: {last}")

    done = 0; failures = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [ex.submit(run_task, t) for t in tasks]
        for fut in as_completed(futs):
            try:
                sid, i, val = fut.result(); results[sid][i] = val; done += 1; maybe_write(sid)
                if done % 16 == 0 or done == len(tasks):
                    logger.info("progress %d/%d", done, len(tasks))
            except Exception as e:  # noqa: BLE001
                failures.append(str(e)); logger.error("%s", e)

    logger.info("Wrote %d/%d problems -> %s", len(written), len(seeds), args.output)
    if failures:
        logger.error("%d generation failures.", len(failures)); return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
