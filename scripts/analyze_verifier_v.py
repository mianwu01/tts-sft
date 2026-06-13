#!/usr/bin/env python3
"""V-arm analysis: elite-dedup child yield per loop + reach/union sets + comparison vs A/C/(C2).

Elites carried by `livecodebench-elitist-replace` appear VERBATIM in later-loop populations, so
naive per-loop counts double-count them. A candidate at loop t>=1 is a CHILD iff its raw text was
not present in any earlier loop's population for that problem.
"""
import hashlib, json, sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
V = REPO / "outputs/node3_lcb_verifier_v"

ARMS = {  # graded arms to compare against (skip silently if not graded yet)
    "A_formal": REPO / "outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated",
    "C_vfonly": REPO / "outputs/node1_lcb_feedback_se_vfonly_pilot",
    "C2_disagreement": REPO / "outputs/node1_lcb_feedback_se_c2_disagreement",
    "B_stayclose": REPO / "outputs/node1_lcb_stayclose_b",
}

# 1) mark elites in V from the loop-candidates dump
seen = defaultdict(set)          # pid -> text hashes seen in earlier loops
elite_ids = set()                # candidate_ids that are carried repeats
by_loop_ids = defaultdict(list)
recs = defaultdict(list)
for line in open(V / "se.jsonl.loop_candidates.jsonl"):
    r = json.loads(line)
    recs[int(r["loop_index"])].append((r["id"], r["candidate_id"],
                                       hashlib.sha1((r["raw_candidate"] or "").encode("utf-8", "ignore")).hexdigest()))
for loop in sorted(recs):
    for pid, cid, hh in recs[loop]:
        if loop > 0 and hh in seen[pid]:
            elite_ids.add(cid)
        by_loop_ids[loop].append(cid)
    for pid, cid, hh in recs[loop]:
        seen[pid].add(hh)

# 2) V genlog -> per-loop child yield + per-problem per-loop solves
g = [json.loads(l) for l in open(V / "genlog.jsonl")]
child_tot = defaultdict(int); child_cor = defaultdict(int)
pop_cor = defaultdict(int)
solved_by_loop = defaultdict(set); first_solve = {}
for r in g:
    loop, ok, cid, pid = int(r["loop_index"]), bool(r["correct"]), r["candidate_id"], r["problem_id"]
    pop_cor[loop] += ok
    if loop == 0 or cid not in elite_ids:
        child_tot[loop] += 1; child_cor[loop] += ok
    if ok:
        solved_by_loop[loop].add(pid)
        first_solve.setdefault(pid, loop)

loops = sorted(child_tot)
union = set().union(*solved_by_loop.values()) if solved_by_loop else set()
late_only = union - solved_by_loop.get(0, set())
out = {
    "arm": "V_verifier_se",
    "per_loop": {str(t): {
        "children": child_tot[t], "children_correct": child_cor[t],
        "child_density": round(child_cor[t] / max(child_tot[t], 1), 4),
        "pop_correct_canonical": pop_cor[t],
        "solved_problems": len(solved_by_loop.get(t, set()))} for t in loops},
    "elites_marked": len(elite_ids),
    "children_total_loops1_4": sum(child_tot[t] for t in loops if t > 0),
    "children_correct_loops1_4": sum(child_cor[t] for t in loops if t > 0),
    "union_reach": len(union), "loop0_reach": len(solved_by_loop.get(0, set())),
    "solved_late_only": sorted(late_only),
}

# 3) cross-arm child-yield table from each graded arm's summary (replace arms: pop == children)
comp = {}
for name, d in ARMS.items():
    sp = d / "summary.json"
    if not sp.exists():
        continue
    s = json.load(open(sp))
    pl = s["per_loop"]
    comp[name] = {
        "children_correct_loops1_4": sum(pl[str(t)]["correct_candidates"] for t in (1, 2, 3, 4) if str(t) in pl),
        "se_all": s.get("se_all_solved"), "se_final": s.get("se_final_solved"),
        "per_loop_correct": {t: pl[t]["correct_candidates"] for t in pl},
        "per_loop_solved": {t: pl[t]["solved_problems"] for t in pl},
    }
out["comparison_arms"] = comp

json.dump(out, open(V / "analysis_v.json", "w"), indent=2)
print(json.dumps(out, indent=2))
