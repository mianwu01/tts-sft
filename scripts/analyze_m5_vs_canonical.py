#!/usr/bin/env python3
"""Pair the M5_combined run against the canonical answer-hidden probe arms. READ-ONLY.

Reports: overall/tier density + flips vs M0/M2/M4; headroom capture vs the M2|M4 OR-ceiling;
channel split (group has/lacks a correct parent); gated-problem outcomes (hmmt10 recovery,
hmmt5 cost); mention-suppression effect; feedback quality."""
import json, re, sys
from collections import defaultdict
from math import comb
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))
from tts_sft.answer_extraction import extract_final_answer, is_exact_match  # noqa: E402

CANON = _REPO / "outputs/node2_math_feedback_answer_hidden_probe"
M5DIR = _REPO / "outputs/node2_math_feedback_m5_combined"
canon_rc = [json.loads(l) for l in (CANON / "recomb_records.jsonl").open()]
m5_rc = [json.loads(l) for l in (M5DIR / "recomb_records.jsonl").open()]
m5_fb = [json.loads(l) for l in (M5DIR / "feedback_records.jsonl").open()]
summ = json.load((CANON / "summary.json").open())
m5_sum = json.load((M5DIR / "summary.json").open())
probs = summ["problems"]
M0, M1, M2, M4, M3 = summ["arms_run"]

R = {(r["pid"], r["group"], r["sample"], r["arm"]): r["correct"] for r in canon_rc}
T5 = {(r["pid"], r["group"], r["sample"]): r for r in m5_rc}
for k, r in T5.items():
    R[(k[0], k[1], k[2], "M5")] = r["correct"]
trials = sorted(T5)
ARMS = [M0, M1, M2, M4, "M5", M3]


def sign_p(w, l):
    n = w + l
    if n == 0: return 1.0
    return min(1.0, 2 * sum(comb(n, k) for k in range(max(w, l), n + 1)) / 2 ** n)


def flips(sel, arm, ref=M0):
    w = sum(1 for t in sel if R[(*t, arm)] and not R[(*t, ref)])
    l = sum(1 for t in sel if R[(*t, ref)] and not R[(*t, arm)])
    return w, l


print("=" * 88)
print("1. OVERALL (1200 paired trials)")
for arm in ARMS:
    d = sum(R[(*t, arm)] for t in trials)
    w, l = flips(trials, arm)
    extra = "" if arm == M0 else f"  vs M0: {w:3d}w/{l:3d}l net {w-l:+4d} (p={sign_p(w,l):.1e})"
    print(f"  {arm:34s} density {d/len(trials):.4f}  traces {d:4d}{extra}")
print("\n  M5 vs M2:", "%dw/%dl net %+d (p=%.2g)" % (*flips(trials, "M5", M2), flips(trials, "M5", M2)[0]-flips(trials, "M5", M2)[1], sign_p(*flips(trials, "M5", M2))))
print("  M5 vs M4:", "%dw/%dl net %+d (p=%.2g)" % (*flips(trials, "M5", M4), flips(trials, "M5", M4)[0]-flips(trials, "M5", M4)[1], sign_p(*flips(trials, "M5", M4))))

print("\n" + "=" * 88)
print("2. BY TIER (density | net flips vs M0)")
for tier in ["mid", "hard", "reach_floor"]:
    sel = [t for t in trials if probs[t[0]]["tier"] == tier]
    line = f" [{tier}] (n={len(sel)})  "
    for arm in ARMS:
        d = sum(R[(*t, arm)] for t in sel) / len(sel)
        w, l = flips(sel, arm)
        line += f"{arm.split('_')[0]} {d:.3f}({w-l:+d})  "
    print(line)

print("\n" + "=" * 88)
print("3. HEADROOM CAPTURE vs the M2|M4 OR-ceiling")
W2 = {t for t in trials if R[(*t, M2)] and not R[(*t, M0)]}
W4 = {t for t in trials if R[(*t, M4)] and not R[(*t, M0)]}
W5 = {t for t in trials if R[(*t, "M5")] and not R[(*t, M0)]}
L5 = {t for t in trials if R[(*t, M0)] and not R[(*t, "M5")]}
print(f"  M5 wins {len(W5)} / losses {len(L5)} (net {len(W5)-len(L5):+d}); OR-ceiling was win {len(W2|W4)}")
print(f"  of M2-only wins ({len(W2-W4)}): M5 captures {len(W5 & (W2-W4))}")
print(f"  of M4-only wins ({len(W4-W2)}): M5 captures {len(W5 & (W4-W2))}")
print(f"  of shared wins  ({len(W2&W4)}): M5 captures {len(W5 & (W2&W4))}")
print(f"  NEW wins beyond M2|M4: {len(W5 - (W2|W4))}")

print("\n" + "=" * 88)
print("4. CHANNEL SPLIT (mixed tiers): group has >=1 correct parent?")
groups = defaultdict(list)
cand_ok = {}
for ds in ["aime", "hmmt"]:
    for line in (_REPO / f"outputs/node1_se_loop5_32k_temp1_{ds}_non_saturated/se.jsonl.loop_candidates.jsonl").open():
        r = json.loads(line)
        pid = r["id"]
        if pid not in probs: continue
        if r["loop_index"] == 0:
            c = int(r["candidate_id"].rsplit("cand", 1)[-1])
            cand_ok[(pid, c)] = is_exact_match(extract_final_answer(r["full_response"] or ""), str(r["answer"]))
        elif r["loop_index"] == 1 and r.get("parent_ids") is not None:
            groups[pid].append(list(r["parent_ids"]))
has_corr = {(pid, gi): any(cand_ok[(pid, c)] for c in groups[pid][gi]) for pid in probs for gi in range(16)}
mixed = [t for t in trials if probs[t[0]]["tier"] != "reach_floor"]
for arm in [M2, M4, "M5"]:
    for label, cond in [("HAS corr parent", lambda t: has_corr[(t[0], t[1])]),
                        ("NO  corr parent", lambda t: not has_corr[(t[0], t[1])])]:
        sel = [t for t in mixed if cond(t)]
        w, l = flips(sel, arm)
        print(f"  {arm:34s} {label}  n={len(sel):4d}  win {w:3d} loss {l:3d} net {w-l:+d}")

print("\n" + "=" * 88)
print("5. GATED PROBLEMS (gate target: recover hmmt10; gate cost check: hmmt5) + star cases")
for pid in ["hmmt25-000010", "hmmt25-000005", "aime25-000027", "hmmt25-000002", "aime25-000029"]:
    sel = [t for t in trials if t[0] == pid]
    cnt = {a: sum(R[(*t, a)] for t in sel) for a in ARMS}
    gated = pid in m5_sum["gated_problems"]
    print(f"  {pid} (gated={gated}, loop0 {probs[pid]['loop0_correct']}/16): " +
          "  ".join(f"{a.split('_')[0]} {cnt[a]:2d}" for a in ARMS) + f"  /{len(sel)}")

print("\n" + "=" * 88)
print("6. MENTION-SUPPRESSION effect (recomb OUTPUT text)")
PATS = {"feedback": re.compile(r"\bfeedback\b", re.I),
        "verifier": re.compile(r"\bverifier\b", re.I),
        "population": re.compile(r"\b(majority|consensus|most common answer|attempts|distribution of)\b", re.I)}
rows = {"M2(canon)": [r for r in canon_rc if r["arm"] == M2],
        "M4(canon)": [r for r in canon_rc if r["arm"] == M4],
        "M5(suppressed)": m5_rc,
        "M0(base)": [r for r in canon_rc if r["arm"] == M0]}
for name, rs in rows.items():
    n = len(rs)
    h = {k: sum(1 for r in rs if p.search(r["text"] or "")) for k, p in PATS.items()}
    print(f"  {name:16s} feedback {h['feedback']:4d}/{n} | verifier {h['verifier']:4d} | population {h['population']:4d}")

print("\n" + "=" * 88)
print("7. M5 FEEDBACK QUALITY")
n = len(m5_fb)
unp = sum(r["status"] == "unparsed" for r in m5_fb)
leak = sum(r["leak"]["leak_any"] for r in m5_fb)
phr = sum(r["leak"]["leak_phrase"] for r in m5_fb)
sd = defaultdict(int)
for r in m5_fb: sd[r["status"]] += 1
agree = known = 0
for r in m5_fb:
    if r["status"] in ("verifier_accepted",): pred = True
    elif r["status"] in ("verifier_rejected", "no_final_answer"): pred = False
    else: continue
    known += 1
    agree += (pred == r["candidate_correct"])
print(f"  n {n}  unparsed {unp}  leak_any {leak/n:.3f} (phrase {phr})  verdict-agree {agree/max(1,known):.3f}")
print(f"  status: {dict(sorted(sd.items(), key=lambda kv: -kv[1]))}")
mt = sum(r["ctok"] for r in m5_rc) / len(m5_rc)
tr = sum(1 for r in m5_rc if r["finish"] == "length")
print(f"  recomb mean ctok {mt:.0f}  finish=length {tr}/{len(m5_rc)}")
