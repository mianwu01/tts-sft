# LCB R2c Refined Confirmation (cleaner V2-concise)

**Change tested.** vs the prior R2c: removed the per-candidate `CHECK` field; moved the safety
instruction to the **top of the prompt once**; visible-failed candidates keep only concrete execution
facts; `all_pass` candidates get a **one-line** visible-status note (`STATUS: visible_passed — public/
sample tests passed; no visible failure observed`); never says "correct"/"hidden". Stay-close wording
kept. Single arm `R2c_refined_stayclose_v2_concise`, run on the **exact same 560 confirmation groups +
per-group seeds**; `R0_stayclose` and old `R2c` **reused** from `outputs/node1_lcb_r2c_confirm/` for
pairing. Baseline/orchestrator untouched. No V3/V4, no SFT. Outputs `outputs/node1_lcb_r2c_refined_confirm/`.

## Results (560 groups; 399 visible-failed, 161 visible-passed)
| arm | correct/560 | density | code-valid | visible-failed (399) | visible-passed (161) |
|---|---|---|---|---|---|
| R0_stayclose (reused) | 380 | 0.679 | 100% | 262 (0.657) | 118 |
| **old R2c (reused)** | **386** | **0.689** | 100% | **272 (0.682)** | 114 |
| **R2c_refined** | 379 | 0.677 | **100%** | 265 (0.664) | 114 |

**Per-group flips:**
- refined vs R0_stayclose: **19 wins / 20 losses (net −1 overall)**.
  - visible-failed: 18 wins / **15 losses** (net **+3**).
  - visible-passed: 1 win / 5 losses (net **−4**).
- refined vs **old R2c**: **10 wins / 17 losses (net −7)**.

## Answers to the two refinement questions
1. **Does removing the per-candidate CHECK keep the visible-failed gain?** **No — it shrinks it.** Old R2c was **272/399 (+10 over baseline, 18 win/8 loss)**; refined is **265/399 (+3, 18 win/15 loss)**. Removing the CHECK ("use this to find bugs but do not overfit to the shown test") roughly **tripled the visible-failed losses (8→15)** — the gain collapses toward noise. The CHECK guidance was apparently doing useful work (likely discouraging overfitting to the one shown public test).
2. **Does the one-line all_pass note reduce the visible-passed penalty?** **No — unchanged.** Refined visible-passed = **114/161, identical to old R2c (114)** and still **below R0_stayclose (118), net −4 flips**. Shortening the all_pass block did **not** help; the penalty is from attaching *any* feedback block to all_pass candidates, not from its length.

## Net
- **The refinement regressed:** overall 379 ≈ R0_stayclose (380) and **below old R2c (386)**; refined-vs-old-R2c flips are net **−7**. (All deltas are within ±noise at n=560, but the direction is consistently negative.)
- **The visible-failed gain only reproduces with the fuller (CHECK-bearing) feedback;** the trimmed version loses it.
- **The visible-passed penalty (−4) is format-independent** → it comes from feeding an uninformative block on all_pass candidates at all.

## Decision (per the rule)
The refined format **worsened** (didn't keep the visible-failed gain at full strength, didn't remove the
visible-passed loss). Per the stated fallback — **do not adopt the refined format.** Two concrete options
before the multi-loop pilot:
1. **Fall back to the previous R2c format** (old R2c: 386, visible-failed +10) — the strongest arm so far.
2. **Principled fix for the persistent visible-passed penalty: OMIT the feedback block entirely for
   `all_pass` candidates** (show only the candidate), keeping the **old (CHECK-bearing) format** on
   visible-failed candidates. This is the one combination not yet tested and directly targets the −4
   penalty while preserving the +10 visible-failed gain.

**Recommendation:** run **one more pairing** — *old-R2c format on visible-failed candidates + no feedback
block on all_pass candidates* — on the same 560 groups. If that keeps the +10 visible-failed gain and
removes the −4 visible-passed loss (net ≈ +10 overall), proceed to the small multi-loop Feedback-SE pilot
with that configuration. Otherwise proceed to the pilot with the **old R2c format as-is** (it's the best
confirmed arm). Do **not** use the refined (CHECK-removed) format.

**Artifacts:** `scripts/probe_lcb_r2c_refined.py`; `outputs/node1_lcb_r2c_refined_confirm/{recomb_records.jsonl, feedback_records.jsonl, summary.json}`. Prior outputs/baseline untouched; no SFT.
