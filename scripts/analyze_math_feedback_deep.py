#!/usr/bin/env python3
"""Deep-dive analysis of the answer-hidden math feedback probe. READ-ONLY over
outputs/node2_math_feedback_answer_hidden_probe/ + the source loop_candidates files.

Questions:
  A. Mechanism: do M2/M4 wins come from groups WITH a correct parent (select/preserve channel)
     or WITHOUT one (population value-import channel, M4-only by construction)?
  B. Complementarity: do M2 and M4 win on the same trials (redundant) or different ones (combine!)?
  C. Hurt forensics: where do feedback arms flip M0-correct trials to wrong?
  D. Trace cleanliness: do feedback-conditioned recombinations cite the feedback/distribution
     meta-info in their final text (bad for self-distillation data)?
  E. M1 placebo + verdict-quality conditioning.
  F. Output length / truncation by arm.
  G. Per-problem appendix table.
"""
import json, re, sys
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))
from tts_sft.answer_extraction import extract_final_answer, is_exact_match  # noqa: E402

OUT = _REPO / "outputs/node2_math_feedback_answer_hidden_probe"
fb = [json.loads(l) for l in (OUT / "feedback_records.jsonl").open()]
rc = [json.loads(l) for l in (OUT / "recomb_records.jsonl").open()]
summ = json.load((OUT / "summary.json").open())
probs = summ["problems"]
arms = summ["arms_run"]
M0, M1, M2, M4, M3 = arms  # order as run

R = {(r["pid"], r["group"], r["sample"], r["arm"]): r for r in rc}
trials = sorted({(r["pid"], r["group"], r["sample"]) for r in rc})
F = {(r["pid"], r["cand_idx"], r["arm"]): r for r in fb}

# ---- rebuild group->parents + per-candidate loop0 correctness (same code path as the probe) ----
groups = defaultdict(list)
cand_ok = {}
for ds in ["aime", "hmmt"]:
    f = _REPO / f"outputs/node1_se_loop5_32k_temp1_{ds}_non_saturated/se.jsonl.loop_candidates.jsonl"
    for line in f.open():
        r = json.loads(line)
        pid = r["id"]
        if pid not in probs:
            continue
        if r["loop_index"] == 0:
            c = int(r["candidate_id"].rsplit("cand", 1)[-1])
            cand_ok[(pid, c)] = is_exact_match(extract_final_answer(r["full_response"] or ""),
                                               str(r["answer"]))
        elif r["loop_index"] == 1 and r.get("parent_ids") is not None:
            groups[pid].append(list(r["parent_ids"]))
parents_of = {(pid, gi): groups[pid][gi] for pid in probs for gi in range(16)}
has_corr = {(pid, gi): any(cand_ok[(pid, c)] for c in parents_of[(pid, gi)])
            for pid in probs for gi in range(16)}
n_corr_parents = {(pid, gi): sum(cand_ok[(pid, c)] for c in parents_of[(pid, gi)])
                  for pid in probs for gi in range(16)}

def correct(t, arm): return R[(t[0], t[1], t[2], arm)]["correct"]

# ================= A. mechanism: flips split by group composition =================
print("=" * 88)
print("A. FLIPS vs M0 split by 'group has >=1 correct parent' (mixed tiers only)")
mixed_trials = [t for t in trials if probs[t[0]]["tier"] != "reach_floor"]
for arm in [M1, M2, M4, M3]:
    for label, cond in [("HAS correct parent ", lambda t: has_corr[(t[0], t[1])]),
                        ("NO  correct parent ", lambda t: not has_corr[(t[0], t[1])])]:
        sel = [t for t in mixed_trials if cond(t)]
        w = sum(1 for t in sel if correct(t, arm) and not correct(t, M0))
        l = sum(1 for t in sel if correct(t, M0) and not correct(t, arm))
        base = sum(1 for t in sel if correct(t, M0))
        print(f"  {arm:32s} {label} n={len(sel):4d}  M0-correct {base:3d}  win {w:3d} loss {l:3d} net {w-l:+d}")
print("  (NO-correct-parent wins = recombination reached beyond its 4 parents)")

# ================= B. complementarity M2 vs M4 =================
print("\n" + "=" * 88)
print("B. M2/M4 WIN OVERLAP (vs M0, all trials)")
W2 = {t for t in trials if correct(t, M2) and not correct(t, M0)}
W4 = {t for t in trials if correct(t, M4) and not correct(t, M0)}
L2 = {t for t in trials if correct(t, M0) and not correct(t, M2)}
L4 = {t for t in trials if correct(t, M0) and not correct(t, M4)}
print(f"  wins:  M2-only {len(W2-W4):3d} | both {len(W2&W4):3d} | M4-only {len(W4-W2):3d}")
print(f"  losses: M2-only {len(L2-L4):3d} | both {len(L2&L4):3d} | M4-only {len(L4-L2):3d}")
best = sum(1 for t in trials if (correct(t, M2) or correct(t, M4))) - \
       sum(1 for t in trials if correct(t, M0) and not (correct(t, M2) or correct(t, M4)))
either_w = len(W2 | W4); either_l = len(L2 & L4)
print(f"  hypothetical OR-arm: win {either_w} / irrecoverable loss {either_l} -> net ceiling {either_w-either_l:+d}"
      f"  (vs M2 {len(W2)-len(L2):+d}, M4 {len(W4)-len(L4):+d})")
ovl = len(W2 & W4) / max(1, min(len(W2), len(W4)))
print(f"  win overlap (Jaccard-on-min): {ovl:.2f}  -> {'mostly redundant' if ovl > .7 else 'substantially complementary'}")

# ================= C. hurt forensics =================
print("\n" + "=" * 88)
print("C. LOSS FORENSICS (M0 correct -> arm wrong)")
for arm, L in [(M2, L2), (M4, L4)]:
    by_pid = defaultdict(int)
    for t in L: by_pid[t[0]] += 1
    top = sorted(by_pid.items(), key=lambda kv: -kv[1])[:5]
    print(f"  {arm}: {len(L)} losses; top problems: {top}")
# M4 losses: was the group's correct parent a minority answer (feedback discourages it)?
m4_min = 0
for t in L4:
    pid, gi, _ = t
    for c in parents_of[(pid, gi)]:
        r = F.get((pid, c, M4))
        if r and r["candidate_correct"] and not r["own_matches_mode"]:
            m4_min += 1
            break
print(f"  M4 losses where the group's correct parent was a MINORITY answer (fb discourages it): {m4_min}/{len(L4)}")
# mode wrong context
m4_mw = sum(1 for t in L4 if not probs[t[0]]["mode_equals_gold"])
print(f"  M4 losses on problems where population mode != gold: {m4_mw}/{len(L4)}")

# ================= D. trace cleanliness =================
print("\n" + "=" * 88)
print("D. META-INFO CITATION in recombination OUTPUT text (bad for clean SFT traces)")
PATS = {
    "feedback_word": re.compile(r"\bfeedback\b", re.I),
    "verifier": re.compile(r"\bverifier|verified by the external\b", re.I),
    "population": re.compile(r"\b(majority|consensus|most common answer|attempts|distribution of)\b", re.I),
}
for arm in arms:
    rows = [r for r in rc if r["arm"] == arm]
    n = len(rows)
    hits = {k: sum(1 for r in rows if p.search(r["text"] or "")) for k, p in PATS.items()}
    hc = {k: sum(1 for r in rows if r["correct"] and p.search(r["text"] or "")) for k, p in PATS.items()}
    ncor = sum(r["correct"] for r in rows)
    print(f"  {arm:32s} fb-word {hits['feedback_word']:4d}/{n} | verifier {hits['verifier']:3d} | "
          f"population {hits['population']:4d}  (among correct: {hc['population']}/{ncor})")

# ================= E. M1 placebo + verdict conditioning =================
print("\n" + "=" * 88)
print("E. M1 CONDITIONING")
def m1_group_quality(pid, gi):
    sts = []
    for c in parents_of[(pid, gi)]:
        r = F.get((pid, c, M1))
        if r is None: continue
        st = r["status"]
        if st == "unparsed": sts.append("placeholder")
        else:
            pred = st in ("likely_correct",) if st in ("likely_correct", "likely_wrong") else None
            if pred is None: sts.append("soft")
            else: sts.append("right" if pred == r["candidate_correct"] else "wrong")
    return sts
buckets = defaultdict(lambda: [0, 0, 0])  # bucket -> [n, win, loss]
for t in mixed_trials:
    sts = m1_group_quality(t[0], t[1])
    if "placeholder" in sts: b = "has_placeholder"
    elif "wrong" in sts: b = "has_wrong_verdict"
    else: b = "all_verdicts_ok"
    buckets[b][0] += 1
    if correct(t, M1) and not correct(t, M0): buckets[b][1] += 1
    if correct(t, M0) and not correct(t, M1): buckets[b][2] += 1
for b, (n, w, l) in sorted(buckets.items()):
    print(f"  {b:18s} n={n:4d}  win {w:3d} loss {l:3d} net {w-l:+d}")

# ================= F. output length / truncation =================
print("\n" + "=" * 88)
print("F. RECOMB OUTPUT SIZE / TRUNCATION by arm")
for arm in arms:
    rows = [r for r in rc if r["arm"] == arm]
    mean_ct = sum(r["ctok"] for r in rows) / len(rows)
    trunc = sum(1 for r in rows if r["finish"] == "length")
    print(f"  {arm:32s} mean ctok {mean_ct:7.0f}  finish=length {trunc:3d}/{len(rows)}")

# ================= G. per-problem appendix =================
print("\n" + "=" * 88)
print("G. PER-PROBLEM correct counts (mixed: /48, reach_floor: /16)")
print(f"  {'problem':18s} {'tier':12s} {'l0':>5s} {'modeOK':6s} " + "".join(f"{a.split('_')[0]:>5s}" for a in arms))
for pid in sorted(probs, key=lambda p: (probs[p]["tier"], probs[p]["loop0_correct"])):
    cnt = {a: sum(1 for t in trials if t[0] == pid and correct(t, a)) for a in arms}
    m = probs[pid]
    print(f"  {pid:18s} {m['tier']:12s} {m['loop0_correct']:2d}/16 {str(m['mode_equals_gold']):6s} " +
          "".join(f"{cnt[a]:5d}" for a in arms))
