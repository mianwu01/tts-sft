#!/usr/bin/env python3
"""Independent BoN generation for LCBV6 calibration (Node 1, 8-GPU replicas).

Independent sampling ONLY — no SqueezeEvolve, no test feedback. Each problem's
seed `question` (CODE_PROMPT-formatted) is sent verbatim as the user message; the
model never sees tests. Captures full per-sample metadata needed for calibration:
text, finish_reason, prompt_tokens, completion_tokens.

Round-robins requests across N OpenAI-compatible vLLM replica endpoints (one per
GPU). Resumable at problem granularity. Sampling: temperature/top_p/top_k/max_tokens
as given; per-sample seed = base_seed + sample_idx; top_k passed via extra_body so
it is explicit and logged (vLLM would otherwise inherit generation_config top_k=20).

Output (one record/problem):
  {"id","question_id","dataset","n_samples","model","generation_params",
   "samples":[{"sample_id","text","finish_reason","prompt_tokens","completion_tokens"}]}
"""
from __future__ import annotations

import argparse
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger("gen_lcbv6")


def existing_complete_ids(path: Path, n_samples: int) -> set[str]:
    done: set[str] = set()
    if not path.exists():
        return done
    for line in path.open():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if len(r.get("samples", [])) >= n_samples:
            done.add(r["id"])
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--model", required=True)
    ap.add_argument("--base-urls", required=True, help="comma-separated, one per replica")
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--n-samples", type=int, default=16)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--max-tokens", type=int, default=32768)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--concurrency", type=int, default=64)
    ap.add_argument("--request-timeout", type=float, default=7200.0)
    ap.add_argument("--max-retries", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from openai import OpenAI

    base_urls = [u.strip() for u in args.base_urls.split(",") if u.strip()]
    clients = [OpenAI(base_url=u, api_key=args.api_key, timeout=args.request_timeout)
               for u in base_urls]
    logger.info("replicas: %d  concurrency: %d", len(clients), args.concurrency)

    seeds = [json.loads(l) for l in args.input.open()]
    if args.limit:
        seeds = seeds[: args.limit]

    if args.overwrite and args.output.exists():
        args.output.unlink()
    done = existing_complete_ids(args.output, args.n_samples)
    todo = [s for s in seeds if s["id"] not in done]
    logger.info("problems: %d total, %d already complete, %d to do",
                len(seeds), len(done), len(todo))
    if not todo:
        logger.info("nothing to do."); return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    gen_params = {
        "model": args.model, "temperature": args.temperature, "top_p": args.top_p,
        "top_k": args.top_k, "max_tokens": args.max_tokens,
        "n_samples": args.n_samples, "seed": args.seed,
    }
    write_lock = threading.Lock()
    out_f = args.output.open("a")
    rr_counter = {"n": 0}
    rr_lock = threading.Lock()

    def next_replica() -> int:
        with rr_lock:
            r = rr_counter["n"] % len(clients)
            rr_counter["n"] += 1
            return r

    def one_call(question: str, sample_idx: int):
        last_err = None
        for attempt in range(args.max_retries):
            cli = clients[next_replica()]
            try:
                resp = cli.chat.completions.create(
                    model=args.model,
                    messages=[{"role": "user", "content": question}],
                    temperature=args.temperature,
                    top_p=args.top_p,
                    max_tokens=args.max_tokens,
                    seed=args.seed + sample_idx,
                    extra_body={"top_k": args.top_k},
                )
                ch = resp.choices[0]
                usage = resp.usage
                return {
                    "sample_id": sample_idx,
                    "text": ch.message.content or "",
                    "finish_reason": ch.finish_reason,
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                }
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(min(30.0, 2.0 ** attempt))
        raise RuntimeError(f"sample {sample_idx} failed after retries: {last_err}")

    # Flatten ALL (problem, sample) tasks into one global pool so every replica
    # stays busy (round-robin assignment). Accumulate per problem; write a problem
    # as soon as all N of its samples are in (resumable, never under-budget).
    pending = {s["id"]: {"seed": s, "samples": [None] * args.n_samples, "remaining": args.n_samples}
               for s in todo}
    t_start = time.time()
    completed = 0

    def task(pid, i):
        return pid, i, one_call(pending[pid]["seed"]["question"], i)

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [ex.submit(task, s["id"], i) for s in todo for i in range(args.n_samples)]
        n_failed_problems = set()
        for fut in as_completed(futs):
            try:
                pid, i, sample = fut.result()
            except Exception as e:  # noqa: BLE001
                logger.error("a sample permanently failed: %s", e)
                continue
            st = pending[pid]
            st["samples"][i] = sample
            st["remaining"] -= 1
            if st["remaining"] == 0:
                samples = st["samples"]
                rec = {
                    "id": pid, "question_id": st["seed"].get("question_id"), "dataset": "LCBV6",
                    "n_samples": args.n_samples, "model": args.model,
                    "generation_params": gen_params, "samples": samples,
                }
                with write_lock:
                    out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out_f.flush()
                completed += 1
                cap = sum(x["finish_reason"] == "length" for x in samples)
                avg_out = sum((x["completion_tokens"] or 0) for x in samples) / args.n_samples
                logger.info("[%d/%d] %s done | cap_hit %d/%d | avg_out_tok %.0f | elapsed %.0fs",
                            completed, len(todo), pid, cap, args.n_samples, avg_out,
                            time.time() - t_start)

    out_f.close()
    logger.info("DONE: wrote %d problems in %.0fs", completed, time.time() - t_start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
