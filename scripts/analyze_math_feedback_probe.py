#!/usr/bin/env python3
"""Post-analysis for the answer-hidden math feedback probe: per-tier breakdown, qualitative
example extraction (helped / hurt / M2-helps-not-M1 / M2-generic), leakage detail. Read-only over
outputs/node2_math_feedback_answer_hidden_probe/."""
import json
from collections import defaultdict
from pathlib import Path

OUT = Path("outputs/node2_math_feedback_answer_hidden_probe")
fb = [json.loads(l) for l in (OUT / "feedback_records.jsonl").open()]
rc = [json.loads(l) for l in (OUT / "recomb_records.jsonl").open()]
summ = json.load((OUT / "summary.json").open())
probs = summ["problems"]

# recomb indexed by (pid, group, arm)
R = {(r["pid"], r["group"], r["sample"], r["arm"]): r for r in rc}
arms = summ["arms_run"]
cells_by_pid = defaultdict(set)          # pid -> set of (group, sample) trial keys
for r in rc:
    cells_by_pid[r["pid"]].add((r["group"], r["sample"]))
TIERS = ["mid", "hard", "reach_floor"]


def tier(pid):
    return probs[pid]["tier"]


# ---- per-tier density/solved per arm ----
print("=== PER-TIER density (correct recomb trials / trials) ===")
for t in TIERS:
    pids = [p for p in probs if tier(p) == t]
    if not pids:
        continue
    print(f"\n{t}  ({len(pids)} problems)")
    for arm in arms:
        tot = sum(1 for p in pids for k in cells_by_pid[p])
        cor = sum(R[(p, g, s, arm)]["correct"] for p in pids for (g, s) in cells_by_pid[p])
        solved = sum(1 for p in pids if any(R[(p, g, s, arm)]["correct"] for (g, s) in cells_by_pid[p]))
        print(f"  {arm:34s} density {cor/max(1,tot):.3f}  traces {cor:4d}/{tot:4d}  solved {solved}/{len(pids)}")

# ---- per-group flips vs M0, per tier (paired by group+sample) ----
print("\n=== FLIPS vs M0 (per tier, paired by group+sample) ===")
for arm in arms:
    if arm == "M0_no_feedback":
        continue
    for t in TIERS:
        pids = [p for p in probs if tier(p) == t]
        if not pids:
            continue
        win = sum(1 for p in pids for (g, s) in cells_by_pid[p]
                  if R[(p, g, s, arm)]["correct"] and not R[(p, g, s, "M0_no_feedback")]["correct"])
        loss = sum(1 for p in pids for (g, s) in cells_by_pid[p]
                   if R[(p, g, s, "M0_no_feedback")]["correct"] and not R[(p, g, s, arm)]["correct"])
        print(f"  {arm:34s} {t:12s} win {win:3d} loss {loss:3d} net {win-loss:+d}")

# ---- feedback indexed for example mining ----
F = defaultdict(dict)  # (pid,cand_idx) -> arm -> rec
for r in fb:
    F[(r["pid"], r["cand_idx"])][r["arm"]] = r


# ---- example trials: M2 helps where M0 & M1 fail ----
def find(cond, limit=8):
    out = []
    for p in probs:
        for (g, s) in cells_by_pid[p]:
            v = {a: R[(p, g, s, a)]["correct"] for a in arms}
            if cond(v):
                out.append((p, g, s, v))
    return out[:limit]


print("\n=== EXAMPLE TRIALS ===")
m2 = "M2_verifier_aware_answer_hidden"; m1 = "M1_gold_free_structured"; m0 = "M0_no_feedback"
m4 = "M4_consistency_aware" if "M4_consistency_aware" in arms else None
m3 = "M3_gold_aware_oracle" if "M3_gold_aware_oracle" in arms else None
print("\n[M2 helps where M0 fails]:", find(lambda v: v[m2] and not v[m0]))
print("\n[M2 helps where BOTH M0 and M1 fail]:", find(lambda v: v[m2] and not v[m0] and not v[m1]))
print("\n[M1 helps where M0 fails]:", find(lambda v: v[m1] and not v[m0]))
print("\n[feedback HURT: M0 right, M1 or M2 wrong]:",
      find(lambda v: v[m0] and (not v[m1] or not v[m2])))
if m4:
    print("\n[M4 helps where M0 fails]:", find(lambda v: v[m4] and not v[m0]))
    print("\n[M4 helps where M2 does NOT]:", find(lambda v: v[m4] and not v[m2]))
    print("\n[M2 helps where M4 does NOT]:", find(lambda v: v[m2] and not v[m4]))
    print("\n[M4 HURT: M0 right, M4 wrong]:", find(lambda v: v[m0] and not v[m4]))
if m3:
    print("\n[only M3 oracle solves (capability/feedback gap)]:",
          find(lambda v: v[m3] and not v[m0] and not v[m1] and not v[m2]))

# ---- M4 self-consistency signal quality ----
if m4:
    m4rows = [r for r in fb if r["arm"] == m4]
    tp = sum(1 for r in m4rows if r["own_matches_mode"] and r["candidate_correct"])
    fp = sum(1 for r in m4rows if r["own_matches_mode"] and not r["candidate_correct"])
    fn = sum(1 for r in m4rows if not r["own_matches_mode"] and r["candidate_correct"])
    tn = sum(1 for r in m4rows if not r["own_matches_mode"] and not r["candidate_correct"])
    print(f"\n=== M4 self-consistency signal (matches-mode as a correctness predictor) ===")
    print(f"  TP {tp}  FP {fp}  FN {fn}  TN {tn}  acc {(tp+tn)/max(1,len(m4rows)):.2f}")
    by_t = defaultdict(lambda: [0, 0])
    for p, d in probs.items():
        by_t[d["tier"]][0] += 1
        if d.get("mode_equals_gold"):
            by_t[d["tier"]][1] += 1
    for t, (n, ok) in by_t.items():
        print(f"  mode==gold on {t}: {ok}/{n} problems")

# ---- M2 generic/uninformative feedback rate (on rejected candidates) ----
def is_generic(txt):
    t = (txt or "").lower()
    return ("no structured feedback available" in t) or (len(txt) < 200) or \
           ("review this candidate independently" in t)


m2rej = [r for r in fb if r["arm"] == m2 and r["status"] == "verifier_rejected"]
m2gen = [r for r in m2rej if is_generic(r["feedback"])]
print(f"\n=== M2 feedback informativeness (rejected candidates) ===")
print(f"  rejected: {len(m2rej)}, generic/uninformative: {len(m2gen)} ({len(m2gen)/max(1,len(m2rej)):.0%})")

# ---- leakage detail ----
print("\n=== LEAKAGE (by arm) ===")
for arm in [a for a in arms if a != m0]:
    rows = [r for r in fb if r["arm"] == arm]
    leak = [r for r in rows if r["leak"]["leak_any"]]
    phrase = sum(r["leak"]["leak_phrase"] for r in rows)
    print(f"  {arm:34s} leak_any {len(leak)}/{len(rows)} ({len(leak)/max(1,len(rows)):.0%})  phrase-leak {phrase}")
