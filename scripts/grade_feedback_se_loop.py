#!/usr/bin/env python3
"""Post-hoc per-loop grading for the Feedback-SE vfonly pilot (hidden tests OFFLINE only).
Grades a loop's candidates from its SE checkpoint: density (correct/N), reach (problems solved by any
candidate), code-valid rate, and the visible-failed vs visible-passed split (a child's group is
visible-failed iff any of its loop-0 parents had a visible PUBLIC failure). Deterministic; reuses the
same extractor/harnesses as the operator + offline grader.
"""
from __future__ import annotations
import argparse, json, subprocess, sys, tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))
from eval_lcbv6_calibration import extract_code, HARNESS  # noqa: E402
PUB = _REPO / "scripts/lcb_public_probe_harness.py"


from lcb_grading import GradingCache, run_harness_cached  # noqa: E402
_CACHE = GradingCache(_REPO / "outputs/grading_cache/lcb_verdicts.jsonl")


def run_harness(harness, code, tj, n, tl=6.0):
    return run_harness_cached(harness, code, tj, n, tl=tl, retries_on_timeout=1, cache=_CACHE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckdir", required=True, type=Path)
    ap.add_argument("--run", default="tts_sft_se_feedback_vfonly_pilot_node1")
    ap.add_argument("--loop", type=int, required=True)
    ap.add_argument("--ids", required=True, type=Path, help="pinned_subset.jsonl (order == checkpoint order).")
    ap.add_argument("--concurrency", type=int, default=48)
    args = ap.parse_args()

    ids = [json.loads(l)["id"] for l in args.ids.open()]
    hidden = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_non_saturated.jsonl").open()}
    public = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_public_tests.jsonl").open()}
    ck = json.loads((args.ckdir / f"{args.run}_loop{args.loop}.json").read_text())
    ck0 = json.loads((args.ckdir / f"{args.run}_loop0.json").read_text())
    P = ck["problems"]; P0 = ck0["problems"]
    assert len(P) == len(ids), f"{len(P)} problems vs {len(ids)} ids"

    # visible-failed group classification per loop>=1 child via its parents' public categories (loop-0 parents)
    pubcat_cache = {}
    def pub_cat(pi, cand_text):
        key = (pi, hash(cand_text))
        if key in pubcat_cache: return pubcat_cache[key]
        code = extract_code(cand_text)
        if not code: r = "no_code"
        else:
            pj = public[ids[pi]]["public_tests"]; n = len(json.loads(pj)["inputs"])
            res = run_harness(PUB, code, pj, n) or {"category": "unknown"}
            r = res["category"]
        pubcat_cache[key] = r; return r

    # build grading jobs: (problem_idx, cand_idx, code, hidden_json, n_hidden, vf_group_bool_or_None)
    jobs = []
    for pi, prob in enumerate(P):
        h = hidden[ids[pi]]["tests"]; nth = len(json.loads(h)["inputs"])
        groups = prob.get("candidate_groups") or [[] for _ in prob["candidates"]]
        for ci, cand in enumerate(prob["candidates"]):
            vf = None
            if args.loop >= 1 and ci < len(groups) and groups[ci]:
                vf = any(pub_cat(pi, parent) != "all_pass" for parent in groups[ci])  # groups store parent TEXTS
            jobs.append((pi, ci, extract_code(cand), h, nth, vf))

    def grade(job):
        pi, ci, code, h, nth, vf = job
        ok = bool(code) and bool((run_harness(HARNESS, code, h, nth) or {}).get("passed"))
        return (pi, ci, bool(code), ok, vf)

    res = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for r in ex.map(grade, jobs):
            res.append(r)

    n = len(res); code_valid = sum(r[2] for r in res); correct = sum(r[3] for r in res)
    solved = {pi for (pi, ci, cv, ok, vf) in res if ok}
    vf_res = [r for r in res if r[4] is True]; vp_res = [r for r in res if r[4] is False]
    out = {
        "loop": args.loop, "n_candidates": n, "n_problems": len(P),
        "density": round(correct / n, 4), "correct": correct,
        "reach_any_of_n": len(solved), "reach_frac": round(len(solved) / len(P), 4),
        "code_valid": code_valid, "code_valid_rate": round(code_valid / n, 4),
        "visible_failed_groups": {"n": len(vf_res), "correct": sum(r[3] for r in vf_res),
                                  "density": round(sum(r[3] for r in vf_res) / max(1, len(vf_res)), 4)},
        "visible_passed_groups": {"n": len(vp_res), "correct": sum(r[3] for r in vp_res),
                                  "density": round(sum(r[3] for r in vp_res) / max(1, len(vp_res)), 4)},
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
