#!/usr/bin/env python
"""Difficulty calibration over independent rollouts (single arm; no model calls).

For each problem in one or more independent-rollout JSONL files (id, answer/gt,
responses[]), grade the N samples with the corrected exact-match evaluator and
report: solved_count/N, any_solved, fraction with an extractable answer, average
output length, and a difficulty bucket. Then recommend a subset for the formal
SE-vs-independent reachability experiment.

Buckets (defaults tuned for N=8; counts are absolute, so pass thresholds if N differs):
  easy   : solved_count >= --easy-threshold (default 6)
  hard   : solved_count <= --hard-threshold (default 0)
  medium : in between

Recommendation rule (advisory — confirm before the formal run): exclude `easy`
(saturated, like the ceiling pilot), then take the LEAST-saturated problems first
(solved_count ascending, ties broken by higher answer-extraction rate). These are
the ones most likely to stay non-saturated at a larger formal budget and thus
actually discriminate SE from independent. Capped to [--target-min, --target-max].
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from tts_sft.answer_extraction import extract_final_answer, is_exact_match  # noqa: E402
from tts_sft.io_utils import iter_jsonl, write_jsonl  # noqa: E402

logger = logging.getLogger("calibrate_difficulty")


def bucket_of(solved: int, easy_threshold: int, hard_threshold: int) -> str:
    if solved <= hard_threshold:
        return "hard"
    if solved >= easy_threshold:
        return "easy"
    return "medium"


def _dataset_of(pid: str) -> str:
    return pid.split("-", 1)[0] if "-" in pid else "unknown"


def grade_problem(rec: dict, easy_threshold: int = 6, hard_threshold: int = 0) -> dict:
    """Grade one independent-rollout record. Pure; unit-tested."""
    pid = str(rec.get("id", ""))
    gold = rec.get("answer")
    if gold is None:
        gold = rec.get("gt")
    gold = str(gold) if gold is not None else None

    resps = rec.get("responses")
    if isinstance(resps, str):
        resps = [resps]
    elif not isinstance(resps, list):
        resps = []
    resps = [r for r in resps if isinstance(r, str)]

    n = len(resps)
    preds = [extract_final_answer(r) for r in resps]
    n_with_answer = sum(1 for p in preds if p is not None)
    solved = sum(1 for p in preds if is_exact_match(p, gold))
    avg_chars = round(sum(len(r) for r in resps) / n, 1) if n else 0.0

    note = ""
    if n == 0:
        note = "no responses"
    elif gold is None:
        note = "no gold answer"
    elif n_with_answer < n:
        note = f"{n - n_with_answer}/{n} samples had no extractable answer"

    return {
        "id": pid,
        "dataset": _dataset_of(pid),
        "gold": gold,
        "question": rec.get("question"),
        "n_samples": n,
        "solved_count": solved,
        "any_solved": solved > 0,
        "n_with_extractable_answer": n_with_answer,
        "frac_with_answer": round(n_with_answer / n, 3) if n else 0.0,
        "avg_response_chars": avg_chars,
        "avg_response_tokens_est": round(avg_chars / 4.0),  # rough chars->tokens
        "bucket": bucket_of(solved, easy_threshold, hard_threshold),
        "note": note,
    }


def recommend_subset(summaries: list[dict], target_min: int = 10, target_max: int = 20) -> list[dict]:
    """Pick a non-saturated subset for the formal reachability run. Pure; unit-tested.

    Excludes `easy`; orders the rest least-saturated-first (solved_count asc, then
    higher answer-extraction rate), and returns up to `target_max` (best effort to
    reach `target_min`).
    """
    pool = [s for s in summaries if s["bucket"] != "easy"]
    pool.sort(key=lambda s: (s["solved_count"], -s["frac_with_answer"], s["id"]))
    return pool[:target_max]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--inputs", required=True, nargs="+", type=Path,
                   help="One or more independent-rollout JSONL files.")
    p.add_argument("--out-summary", required=True, type=Path, help="Per-problem calibration JSONL.")
    p.add_argument("--out-buckets", required=True, type=Path, help="Aggregate bucket/distribution JSON.")
    p.add_argument("--out-subset", type=Path, default=None,
                   help="If set, write recommended subset as seed JSONL {id,question,answer}.")
    p.add_argument("--easy-threshold", type=int, default=6)
    p.add_argument("--hard-threshold", type=int, default=0)
    p.add_argument("--target-min", type=int, default=10)
    p.add_argument("--target-max", type=int, default=20)
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    summaries: list[dict] = []
    for f in args.inputs:
        if not f.exists():
            logger.error("Input not found: %s", f)
            return 2
        for rec in iter_jsonl(f):
            summaries.append(grade_problem(rec, args.easy_threshold, args.hard_threshold))
    summaries.sort(key=lambda s: s["id"])
    write_jsonl(args.out_summary, summaries)

    # Aggregate buckets, overall + per dataset.
    def _dist(rows: list[dict]) -> dict:
        from collections import Counter
        c = Counter(s["bucket"] for s in rows)
        return {
            "total": len(rows),
            "easy": c.get("easy", 0), "medium": c.get("medium", 0), "hard": c.get("hard", 0),
            "any_solved": sum(1 for s in rows if s["any_solved"]),
            "solved_count_hist": dict(sorted(Counter(s["solved_count"] for s in rows).items())),
        }

    datasets = sorted({s["dataset"] for s in summaries})
    buckets = {
        "n_samples_per_problem": summaries[0]["n_samples"] if summaries else None,
        "easy_threshold": args.easy_threshold, "hard_threshold": args.hard_threshold,
        "overall": _dist(summaries),
        "by_dataset": {d: _dist([s for s in summaries if s["dataset"] == d]) for d in datasets},
    }
    args.out_buckets.parent.mkdir(parents=True, exist_ok=True)
    args.out_buckets.write_text(json.dumps(buckets, ensure_ascii=False, indent=2), encoding="utf-8")

    n_subset = 0
    if args.out_subset is not None:
        sel = recommend_subset(summaries, args.target_min, args.target_max)
        seed_rows = [{"id": s["id"], "question": s["question"], "answer": s["gold"]} for s in sel]
        n_subset = write_jsonl(args.out_subset, seed_rows)

    logger.info("Calibrated %d problems across %s.", len(summaries), datasets)
    logger.info("Overall buckets: easy=%d medium=%d hard=%d (N=%s)",
                buckets["overall"]["easy"], buckets["overall"]["medium"], buckets["overall"]["hard"],
                buckets["n_samples_per_problem"])
    if args.out_subset is not None:
        logger.info("Recommended subset: %d problems -> %s", n_subset, args.out_subset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
