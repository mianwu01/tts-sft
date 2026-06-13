#!/usr/bin/env python3
"""Post-smoke verification for the V arm: audit completeness + elite carry-through in checkpoints."""
import json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ODIR = REPO / "outputs/node3_lcb_verifier_v_smoke"
CKDIR = REPO / "external/squeeze-evolve/outputs/node3_lcb_verifier_v_smoke/checkpoints"
RUN = "tts_sft_se_verifier_v_smoke_node3"

audit = [json.loads(l) for l in open(ODIR / "verifier_operator_audit.jsonl")]
by_ev = {}
for a in audit:
    by_ev.setdefault(a["event"], []).append(a)

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

pre = by_ev.get("verdict_precompute", [])
check(len(pre) == 2 and [p["loop"] for p in pre] == [0, 1],
      f"2 precompute events for ckpt loops [0,1] (got {[p.get('loop') for p in pre]})")
check(all(p["skipped_problems"] == 0 for p in pre), "no problems skipped in verdict lookup")
check(not by_ev.get("selection_fallback") and not by_ev.get("update_fallback")
      and not by_ev.get("update_groups_misalign"), "0 operator fallbacks / misalignments")
sel = by_ev.get("selection", [])
check(len(sel) == 4, f"4 selection events (2 problems x 2 loops), got {len(sel)}")
upd = by_ev.get("update", [])
check(len(upd) == 4, f"4 update events, got {len(upd)}")
for u in upd:
    check(u["carried"] == min(u["n_correct_old"], 2),
          f"update {u['pid']}: carried {u['carried']} == min(C={u['n_correct_old']},2)")

# elite carry-through: every carried elite text must appear verbatim in the NEXT checkpoint's pop
cks = {t: json.load(open(CKDIR / f"{RUN}_loop{t}.json")) for t in (0, 1, 2)}
vh = {}
for t in (0, 1):
    for p in cks[t]["problems"]:
        for c in p["candidates"]:
            vh.setdefault(t, set()).add(c)
carried_total = 0
for t in (1, 2):
    for p_prev, p_now in zip(cks[t - 1]["problems"], cks[t]["problems"]):
        kept = [c for c in p_now["candidates"] if c in set(p_prev["candidates"])]
        carried_total += len(kept)
        check(len(set(p_now["candidates"])) >= 15, f"loop{t} pop has >=15 unique candidates")
exp = sum(u["carried"] for u in upd)
check(carried_total == exp, f"elites carried into checkpoints verbatim: {carried_total} == audit {exp}")

fb = [json.loads(l) for l in open(ODIR / "feedback_operator_audit.jsonl")]
fb_fall = [r for r in fb if r.get("fallback")]
check(not fb_fall, f"C2 feedback audit: 0 fallbacks (got {len(fb_fall)})")

print("\n" + ("SMOKE VERIFICATION: ALL PASS" if not fails else f"SMOKE VERIFICATION: {len(fails)} FAILURES"))
sys.exit(1 if fails else 0)
