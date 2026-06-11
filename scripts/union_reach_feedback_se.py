#!/usr/bin/env python3
"""Union any-of-N reach across all loops for a Feedback-SE run (replace-erosion check):
a problem counts as reached if ANY candidate in ANY loop checkpoint (0..L) passes hidden tests.
Reports per-loop reach + the union (= SE-all) + final-pop reach. Code-hash cache dedupes work.
"""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))
from eval_lcbv6_calibration import extract_code, HARNESS  # noqa: E402


from lcb_grading import GradingCache, run_harness_cached  # noqa: E402
_CACHE = GradingCache(_REPO / "outputs/grading_cache/lcb_verdicts.jsonl")


def grade(code, tj, n):
    if not code: return False
    v = run_harness_cached(HARNESS, code, tj, n, tl=6.0, retries_on_timeout=1, cache=_CACHE)
    return bool(v and v.get("passed"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckdir", required=True, type=Path)
    ap.add_argument("--run", required=True)
    ap.add_argument("--loops", type=int, default=4)
    ap.add_argument("--ids", required=True, type=Path)
    ap.add_argument("--concurrency", type=int, default=48)
    args = ap.parse_args()

    ids = [json.loads(l)["id"] for l in args.ids.open()]
    hidden = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_non_saturated.jsonl").open()}
    htests = {pid: (hidden[pid]["tests"], len(json.loads(hidden[pid]["tests"])["inputs"])) for pid in ids}

    # collect unique (problem_idx, code) jobs across all loops; track which loop each appears in
    cache = {}; jobs = {}; loop_cands = {L: [] for L in range(args.loops + 1)}
    for L in range(args.loops + 1):
        ck = json.loads((args.ckdir / f"{args.run}_loop{L}.json").read_text())
        for pi, prob in enumerate(ck["problems"]):
            codes = [extract_code(c) for c in prob["candidates"]]
            loop_cands[L].append(codes)
            for code in codes:
                key = (pi, hashlib.md5((code or "").encode("utf-8", "ignore")).hexdigest())
                if key not in jobs: jobs[key] = (pi, code)

    def run(item):
        key, (pi, code) = item
        tj, n = htests[ids[pi]]
        return key, grade(code, tj, n)
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for key, ok in ex.map(run, list(jobs.items())):
            cache[key] = ok

    def solved_at(L):
        s = set()
        for pi, codes in enumerate(loop_cands[L]):
            for code in codes:
                if cache[(pi, hashlib.md5((code or "").encode("utf-8", "ignore")).hexdigest())]:
                    s.add(pi); break
        return s
    per_loop = {L: solved_at(L) for L in range(args.loops + 1)}
    union = set().union(*per_loop.values())
    out = {"run": args.run, "n_problems": len(ids),
           "per_loop_reach": {L: len(per_loop[L]) for L in per_loop},
           "final_pop_reach": len(per_loop[args.loops]),
           "union_any_of_n": len(union),
           "replace_erosion_union_minus_finalpop": len(union) - len(per_loop[args.loops])}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
