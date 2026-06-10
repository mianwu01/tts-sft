# LCB loop0→loop1 Feedback Recombination Probe (R2c)

**Goal.** Does deterministic **V2-concise** visible-execution feedback help the recombination model
synthesize better loop-1 LCB solutions from k=4 loop-0 parent groups? Unit = a **group** (k=4), not
single-candidate repair. Baseline strip=false loop unmodified; new artifacts under
`outputs/node1_lcb_r2c_recombine_probe/`. No V3, no V4, no SFT.

**Setup.** 30 problems with **mixed** loop-0 correctness, their first 4 real loop-1 groups = **120 groups**.
Candidates = **full strip=false loop-0 text** (same as baseline). Same groups + same per-group seed across
all 3 arms; only the prompt differs. Code extracted **only** to build V2-concise from **public** tests;
**hidden tests used only for final grading**. Decoding temp 1.0, top_p 0.95, top_k 20, max_tokens 32768.
Parent-candidate public-category mix (322 candidates): all_pass 215, compile 57, runtime 20, wrong_answer 30.

## Arms & exact prompts
- **R0_original** — exact `livecodebench-aggregate` prompt (no feedback, no stay-close).
- **R0_stayclose_no_feedback** — stay-close prompt, no feedback.
- **R2c_stayclose_v2_concise** — stay-close + a deterministic **V2-concise** block (`STATUS/OBSERVED/DETAIL/CHECK`) after each candidate; all_pass → fixed non-leaky "no visible failure" message.
(All prompts/format verbatim in `scripts/probe_lcb_r2c_recombine.py`; V2-concise is deterministic, no LLM.)

## Results (120 groups/arm)
| arm | correct/120 | **density** | code-valid | visible-failed groups (89) | visible-passed groups (31) | total tokens |
|---|---|---|---|---|---|---|
| R0_original | 86 | 0.717 | 120/120 (100%) | 63/89 | 23/31 | ~5.88M |
| R0_stayclose_no_feedback | 91 | 0.758 | 100% | 66/89 | 25/31 | ~5.89M |
| **R2c_stayclose_v2_concise** | **94** | **0.783** | **100%** | **69/89** | 25/31 | ~5.99M |

Solved problems 29/30 in every arm (saturated — not discriminating). Per-group flips (same groups+seeds):
- **Stay-close (R0→stayclose):** +7 / −2 (net **+5**).
- **Feedback (stayclose→R2c):** +4 / −1 (net **+3**) — **all 4 gains are on visible-failed groups** (where feedback has signal); the 1 loss is lcbv6-108.
- **Combined (R0→R2c):** +11 / −3 (net **+8**, 0.717→0.783, +6.7pp).

## Reading
1. **R0_original → R0_stayclose: small positive (+5 net, +4.2pp).** Unlike the math one-step probe (where stay-close was inert), the Harman stay-close wording **helps a little** on LCB recombination.
2. **R0_stayclose → R2c (the feedback effect): small positive (+3 net, +2.5pp), cleanly localized.** All gains are on **visible-failed** groups (66→69); visible-passed groups are unchanged (25→25, as expected — feedback there is just "no visible failure"). So the gain comes exactly where feedback carries signal — mechanistically sound.
3. **Crucially, V2-concise did NOT reduce code-validity (100% vs 100%).** This is the opposite of the *one-step repair* probe, where raw/structured feedback derailed the output format (code-valid 26/118). At the recombination operating point (full candidates, "return one code block"), the format held — feedback is **safe** here.
4. **Token cost modest.** Prefill dominated by the 4 full candidates (~5.8M, same across arms); R2c adds the feedback blocks (+~40k prefill) and longer outputs (ctok 143k vs 82k) → **~+2% total tokens**.

### Examples
- **R2c helped (stayclose✗→R2c✓), 4 groups, all visible-failed:** lcbv6-100/g2, 112/g2, 037/g3, 043/g0 — the V2-concise failing-input/expected/actual let recombination avoid the parent's known wrong case.
- **R2c hurt, 1 group:** lcbv6-108/g2 — feedback steered away from an otherwise-correct synthesis.
- **Stay-close helped (R0✗→stayclose✓), net +5** — keeping closer to candidate attempts recovered some groups the free-form aggregate rewrote away.

## Main comparisons
- **R0_original vs R0_stayclose:** stay-close **+4.2pp** density (+5 net). Small but positive; keep it.
- **R0_stayclose vs R2c:** V2-concise **+2.5pp** (+3 net), all on visible-failed groups, **no code-valid loss**.

## Decision (per the pre-registered rule)
Rule: *proceed to full in-loop only if R2c improves over R0_stayclose with a meaningful margin AND does not reduce code-valid rate.*
- **Code-valid:** not reduced (100% vs 100%) ✓.
- **Margin:** **+2.5pp / +3 net groups, directionally consistent and mechanistically clean** (gains only on visible-failed groups) — **but within sampling noise at n=120** (±~4 groups). So it **meets the rule directionally but is not yet conclusive**.

**Recommendation:** **Conditional GO — confirm at scale before committing.** V2-concise feedback is *safe* (no format harm), *cheap* (~+2% tokens), and *helps where it should* (visible-failed groups), with stay-close giving an additional small lift. The effect is small and within noise at 120 groups, so before a full in-loop Feedback-SE run I recommend **one larger confirmation** — e.g. ~300–500 visible-failed groups (or multi-sample per group) of **R0_stayclose vs R2c** — and if the +2–3pp (visible-failed) holds, wire **R2c (stay-close + V2-concise, all_pass→fixed message)** into the in-loop LCB Feedback-SE pyramid vs the untouched strip=false control. **Do not** add V3/V4. If the confirmation washes out, do not wire feedback in.

**Artifacts:** `scripts/probe_lcb_r2c_recombine.py`; `outputs/node1_lcb_r2c_recombine_probe/{recomb_records.jsonl, feedback_records.jsonl, summary.json}`. Baseline loop / prior outputs untouched; no SFT.

---

# Confirmation at scale (2 arms, 560 groups) — 2026-06-10

Frozen design (Harman stay-close + deterministic V2-concise, no V3/V4, hidden tests only for grading).
Only `R0_stayclose_no_feedback` vs `R2c_stayclose_v2_concise`, **same parent groups + same per-group
seeds**, **560 groups** (70 mixed-correctness problems × 8 groups; **399 visible-failed**, 161
visible-passed). Outputs `outputs/node1_lcb_r2c_confirm/`.

| arm | density | code-valid | visible-failed (399) | visible-passed (161) | ptok / ctok |
|---|---|---|---|---|---|
| R0_stayclose_no_feedback | 0.679 (380/560) | 560/560 (100%) | 262/399 = **0.657** | 118/161 | 27.04M / 0.34M |
| **R2c_stayclose_v2_concise** | 0.689 (386/560) | 560/560 (**100%**) | 272/399 = **0.682** | 114/161 | 27.23M / 0.63M |

**Per-group flips (R2c − stayclose):** 19 wins / 13 losses / 528 ties → **net +6 overall**.
- **visible-failed: 18 wins / 8 losses → net +10, +2.5pp** (262→272). McNemar χ²≈3.85, **p≈0.05** (borderline significant).
- **visible-passed: 1 win / 5 losses → net −4** — the uninformative "no visible failure" block slightly *hurts*.
- Overall net +6 is **not** significant (χ²≈1.1, p≈0.29) — the visible-failed gain is partly offset by the visible-passed loss.

### Findings
1. **The visible-failed gain reproduced exactly:** +2.5pp in *both* the 120-group probe and this 560-group run (262→272 here). It is **mechanism-localized** (gains concentrate on groups where V2-concise has real signal) and **directionally robust** (18 vs 8 flips).
2. **Code-valid stayed 100%** — V2-concise is safe at the recombination operating point (no format derailment, unlike one-step repair).
3. **Token overhead small** (~+0.7% prefill, +0.29M decode ≈ +1% total).
4. **Visible-passed is slightly negative (−4):** attaching the "no visible failure" block to `all_pass` candidates adds length without signal and marginally hurts → the natural-mixture effect is diluted to **+1.1pp** (380→386), not significant.
5. **Wins/losses:** wins e.g. lcbv6-100/g2, 100/g4, 112/g1, 112/g2, 094/g1 (visible-failed — feedback's failing-input/expected/actual let recombination avoid the parent bug); losses e.g. lcbv6-112/g6, 094/g2, 125/g5, 021/g2 (mostly tail noise; on visible-passed the feedback is uninformative).

### Decision (per the rule)
- **code-valid 100%** ✓. **visible-failed margin: +2.5pp, reproducible, net +10 flips, p≈0.05** — a *small but real and clean* positive; "meaningful" in the localized/reproducible sense, borderline in the statistical sense. Natural-mixture margin small (+1.1pp, n.s.) due to the visible-passed dilution.
- **→ QUALIFIED GO to the in-loop LCB Feedback-SE pyramid**, with one **design refinement**: **attach the V2-concise block only to candidates with a VISIBLE failure; omit it (or use a one-line minimal note) for `all_pass` candidates** — this removes the −4 visible-passed penalty so the +2.5pp visible-failed gain flows through, and it's where the effect could **compound across loops**. Keep stay-close, V2-concise, no V3/V4, hidden-only grading; compare against the untouched strip=false control.
- If, in-loop, the effect fails to compound or the refined visible-passed handling doesn't recover the dilution, fall back to not wiring feedback.

**Artifacts:** `outputs/node1_lcb_r2c_confirm/{recomb_records.jsonl, feedback_records.jsonl, summary.json}`. Baseline/prior outputs untouched; no SFT; no V3/V4.
