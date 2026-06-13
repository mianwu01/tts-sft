#!/usr/bin/env python
"""Group SqueezeEvolve per-loop candidates into per-problem reachability input.

The normalized SE output (run_squeeze_evolve.py) keeps only the FINAL population
(~`population` candidates), so grading it is "SE final-any-K". For the
compute-matched reachability diagnostic the SE arm should be judged over ALL of
its generations across every loop (loop0 + loop1 + ... = the budget N_i). Those
live one-row-per-candidate in `<output>.loop_candidates.jsonl`
(scripts/se_loop_candidates.py). This tool regroups them BY PROBLEM into the
exact per-problem schema `scripts/eval_reachability.py` consumes
(`{id, question, gt, candidates:[...]}`), so the same offline grader can do an
honest SE-all-N vs independent-N comparison.

It NEVER calls a model and NEVER runs SqueezeEvolve — pure JSONL reshaping.
Extra per-candidate provenance (loop_index, candidate_id, parent_ids, fitness,
final_answer) is preserved under `candidate_meta` (eval_reachability ignores it).
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter, OrderedDict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from tts_sft.io_utils import iter_jsonl, write_jsonl  # noqa: E402

logger = logging.getLogger("group_se_loop_candidates")


def _sort_key(rec: dict) -> tuple:
    li = rec.get("loop_index")
    gid = rec.get("group_id")
    return (li if isinstance(li, int) else 0, gid if isinstance(gid, int) else 0)


def group_candidates(records: list[dict], include_loops: set[int] | None = None) -> list[dict]:
    """Group per-candidate loop records into one per-problem record. Pure; tested.

    Output per problem (eval_reachability-compatible):
      {id, question, gt, candidates:[full_response...], candidate_meta:[...],
       source:"squeeze_evolve_all_loops", metadata:{n_candidates, n_by_loop}}
    Candidates are ordered by (loop_index, group_id) so loop0 precedes loop1.
    """
    by_id: "OrderedDict[str, list[dict]]" = OrderedDict()
    for r in records:
        pid = str(r.get("id", ""))
        if not pid:
            continue
        if include_loops is not None and r.get("loop_index") not in include_loops:
            continue
        by_id.setdefault(pid, []).append(r)

    out: list[dict] = []
    for pid, recs in by_id.items():
        recs_sorted = sorted(recs, key=_sort_key)
        candidates = [r.get("full_response") if isinstance(r.get("full_response"), str) else "" for r in recs_sorted]
        candidate_meta = [
            {
                "loop_index": r.get("loop_index"),
                "candidate_id": r.get("candidate_id"),
                "parent_ids": r.get("parent_ids"),
                "fitness": r.get("fitness"),
                "final_answer": r.get("final_answer"),
            }
            for r in recs_sorted
        ]
        gold = next((r.get("answer") for r in recs_sorted if r.get("answer") is not None), None)
        if gold is None:
            gold = next((r.get("gt") for r in recs_sorted if r.get("gt") is not None), None)
        question = next((r.get("question") for r in recs_sorted if r.get("question")), None)
        by_loop = Counter(r.get("loop_index") for r in recs_sorted)
        out.append({
            "id": pid,
            "question": question,
            "gt": str(gold) if gold is not None else None,
            "candidates": candidates,
            "candidate_meta": candidate_meta,
            "source": "squeeze_evolve_all_loops",
            "metadata": {
                "n_candidates": len(candidates),
                "n_by_loop": {str(k): v for k, v in sorted(by_loop.items(), key=lambda x: (x[0] is None, x[0]))},
            },
        })
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path, help="SE loop_candidates JSONL (one row per candidate).")
    p.add_argument("--output", required=True, type=Path, help="Per-problem JSONL (eval_reachability SE input).")
    p.add_argument("--include-loops", default=None,
                   help="Comma-separated loop indices to include (e.g. '0,1'). Default: all loops.")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()
    if not args.input.exists():
        logger.error("Input not found: %s", args.input)
        return 2
    include_loops = None
    if args.include_loops:
        include_loops = {int(x) for x in args.include_loops.split(",") if x.strip() != ""}

    records = list(iter_jsonl(args.input))
    grouped = group_candidates(records, include_loops=include_loops)
    n = write_jsonl(args.output, grouped)
    logger.info("Grouped %d candidate rows -> %d problems -> %s", len(records), n, args.output)
    for g in grouped:
        logger.info("  id=%s candidates=%d by_loop=%s gt=%s",
                    g["id"], g["metadata"]["n_candidates"], g["metadata"]["n_by_loop"], g["gt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
