# Feedback-Augmented SqueezeEvolve — Offline Probe (AIME/HMMT)

**Offline probe only.** No change to the SE orchestrator; no baseline outputs modified; separate
script `scripts/probe_feedback_recombination.py`. Real model calls (critic + recombination) on the
existing vLLM endpoint, small-scale. Date 2026-06-10. Goal: decide (1) gold-aware vs gold-free
critic, (2) full-reasoning vs stripped-response feedback view — **before** touching the real loop.

**Fixed design choice (per spec):** recombination ALWAYS inserts the **stripped** candidate
(strip=true fixed). Only the *feedback-generation* view varies between full and stripped.

---

## Step 1 — Data located
- **AIME:** `outputs/node1_se_loop5_32k_temp1_aime_non_saturated/se.jsonl.loop_candidates.jsonl` — 18 problems, **16 loop-0 candidates/problem**.
- **HMMT:** `outputs/node1_se_loop5_32k_temp1_hmmt_non_saturated/se.jsonl.loop_candidates.jsonl` — 21 problems, 16 loop-0 candidates/problem.
- Schema (per candidate row): `id, question, answer (gold), loop_index, candidate_id, group_id, parent_ids, parent_texts, full_response, thinking_trace, final_answer, fitness, score, routing_metadata, …`.
- **Full reasoning traces available?** Yes — `full_response` contains the complete generation incl. `<think>` (e.g. aime25-000001 loop-0 cand: 53,426 chars full → 3,863 chars stripped).
- **Stripped versions stored?** Not directly; built on the fly with SE's own `strip_think_blocks` (`external/squeeze-evolve/.../common.py`) — identical to what SE recombination uses at strip=true.
- **Gold answers available?** Yes (`answer`), for AIME and HMMT.
- **Verifier used:** `src/tts_sft/answer_extraction.py` → `extract_final_answer` + `is_exact_match` (LaTeX-aware, last `\boxed{}`). Same one used by all prior AIME/HMMT grading.
- **Groups:** reused the **real loop-1 `parent_ids`** (k=4, 16 groups/problem) so groups are faithful to SE; probe used the first 5 groups/problem.

**Probe size:** 10 problems (5 AIME + 5 HMMT), chosen for *mixed* loop-0 correctness (5–12/16) so feedback-verdict-vs-truth is measurable: AIME 000006/008/009/017/028, HMMT 000002/005/006/007/010. 5 groups/problem. 488 feedback calls (4 arms), 250 recombination calls (5 arms).

## Step 2 — Candidate views
- `full_view` = `full_response` verbatim (incl. `<think>`; ~20–70k chars).
- `stripped_view` = `strip_think_blocks(full_response)` (~2–6k chars; final solution + `\boxed{}`).
- Recombination prompt uses `stripped_view` only; feedback prompt uses whichever the arm dictates.

## Step 3 — Four feedback variants + leakage checks
Arms: `gold_free_full`, `gold_free_stripped`, `gold_aware_full`, `gold_aware_stripped`. Prompts (verbatim in the script): gold-free asks the critic to flag errors/missing steps without solving or revealing the answer; gold-aware gives the gold "for judgement only — DO NOT REVEAL", asks consistency + concise feedback; both must start `VERDICT: appears correct|likely has errors`. Leakage detector flags: exact gold substring, normalized-gold substring, reveal phrases ("the correct answer is", …); `\boxed{}` tracked info-only (critics legitimately write math).

## Step 4 — Recombination (candidates always stripped)
Per group, 5 arms: `no_feedback` (stripped candidates only) and the 4 feedback arms (stripped candidate + its feedback interleaved), ending "…End with the final answer in `\boxed{}`." Identical groups + seeds across arms (seed = base+group).

## Step 5 — Recombination results (50 groups/arm)
| arm | solved /10 | correct traces /50 | **density** | recomb prompt-tok | recomb completion-tok |
|---|---|---|---|---|---|
| no_feedback (baseline) | 10/10 | 39 | **0.78** | 1,809,866 | 235,482 |
| gold_free_full | 10/10 | 38 | 0.76 | 1,954,059 | 97,879 |
| gold_free_stripped | 10/10 | 40 | 0.80 | 2,178,728 | 122,930 |
| gold_aware_full | 10/10 | 43 | 0.86 | 2,016,096 | 77,219 |
| **gold_aware_stripped** | 10/10 | **46** | **0.92** | 2,160,063 | 77,270 |

**Solved is saturated (10/10 all arms)** — these problems all have correct loop-0 members, so reach isn't the discriminator; **density (correct-trace yield) is.** Per-problem correct-traces /5 vs baseline — gains concentrate on the HARD (low-baseline) problems:
| pid | no_fb | gf_full | gf_strip | ga_full | ga_strip |
|---|---|---|---|---|---|
| hmmt25-000002 | 1 | 1 | 1 | 3 | **5** |
| hmmt25-000010 | 2 | 2 | 2 | 3 | 3 |
| aime25-000028 | 4 | 4 | 5 | 5 | 5 |
| aime25-000006 | 5 | **3** | 5 | **3** | 5 |
| (others 4–5 → ~5) | | | | | |

**Tokens:** feedback-gen total **9.53M** (8.88M prompt + 0.65M completion); recomb total 10.73M. Full-view feedback prompt cost ≈ **2.8×** stripped (3.26M vs 1.18M per arm) for *no* density benefit. Adding feedback *reduced* recomb completion tokens (235k → 77–123k: feedback makes recombination converge shorter). Per-arm end-to-end cost (feedback+recomb): no_feedback ≈ 2.05M; gold_aware_stripped ≈ 3.6M ≈ **1.75×**.

## Step 6 — Feedback quality
| arm | avg chars | **leak rate** | % says correct | % says error | verdict-vs-truth agreement | fb prompt-tok | fb completion-tok |
|---|---|---|---|---|---|---|---|
| gold_free_full | 2,856 | 0.45 | 0.74 | 0.26 | 0.68 | 3,258,174 | 89,616 |
| gold_free_stripped | 5,954 | 0.30 | 0.20 | 0.61 | 0.45 | 1,175,553 | 224,011 |
| gold_aware_full | 3,851 | **0.95** | 0.80 | 0.17 | 0.69 | 3,262,102 | 124,079 |
| gold_aware_stripped | 5,623 | **0.96** | 0.46 | 0.32 | 0.60 | 1,179,481 | 214,881 |

- **Leakage:** gold-aware critics **reveal the gold ~95%** of the time despite "DO NOT REVEAL" — e.g. *"check if the candidate's final answer is consistent with the correct answer of 821… The correct answer is 821, so…"* (aime25-000006). Gold-free "leak" 0.30–0.45 is a **false-positive baseline** — the critic restating the *candidate's own* final value (which equals gold when the candidate is correct), with **no oracle knowledge** (no real leak).
- **Verdict accuracy:** gold-aware barely beats gold-free on agreement (0.69 vs 0.68 full) — the oracle helps *density* more than *verdict correctness*. `gold_free_full` is over-lenient (74% "correct"); `gold_free_stripped` over-harsh (61% "error", agreement 0.45 ≈ chance).
- **Examples — helped (9 groups no_fb✗→gold_aware_stripped✓):** hmmt25-000002 group0, aime25-000009 group0, aime25-000017 group0, hmmt25-000010 group1. **Hurt (2 groups no_fb✓→gold_free_full✗):** aime25-000006 groups 3,4 — full-view gold-free feedback misjudged and steered recombination wrong.
- **Good gold-free feedback** (correctly flags a wrong candidate, aime25-000006): *"The candidate starts by discussing that all first letters are distinct… [identifies the flawed assumption]"* (verdict: likely has errors, candidate was wrong ✓).
- **Bad gold-free feedback** (wrongly endorses a wrong candidate, aime25-000006, gold_free_full): verdict "appears correct" on an incorrect solution — the over-lenient failure mode that *hurt* recombination.

## Step 7 — Conclusions

1. **Does gold-aware feedback improve recombination over no-feedback?** **Yes** — density 0.86 (full) / **0.92** (stripped) vs 0.78 baseline (+10% / +18% correct-trace yield), with gains concentrated on hard problems (hmmt25-000002 1→5). It's a real oracle-driven gain.
2. **Does gold-free feedback improve over no-feedback?** **No / marginal** — 0.76 (full, slightly *worse*) and 0.80 (stripped, +0.02, within noise). The gold-free critic isn't accurate enough (agreement 0.45–0.68; over-lenient or over-harsh) to reliably help, and it *hurt* 2 groups.
3. **Full-reasoning vs stripped-response feedback?** **Stripped wins** — higher density in both gold conditions (gf 0.80>0.76; ga 0.92>0.86) **and** ~2.8× cheaper feedback-prompt cost. Feeding the critic the full `<think>` trace dilutes/distracts and costs far more for no benefit.
4. **Does feedback leak gold answers?** **Gold-aware: yes, ~95%** — it routinely prints/uses the gold despite instructions → **not deployable** as a self-distillation data source (the "feedback" would just leak the target). Gold-free: no real leak (the ~0.3–0.45 flagged is the candidate's own value).
5. **Token cost too much?** **Moderate, manageable if stripped.** Best arm ≈ 1.75× no-feedback end-to-end; full-view arms are needlessly ~2.8× costlier on feedback prompt. Stripped keeps it reasonable; feedback also shortens recombination decode.
6. **Enough signal to implement in-loop Feedback-SE?** **Yes for the *diagnostic*, not yet for a *deployable* method.** gold_aware_stripped gives a clear, real upper-bound (+18% density) — worth wiring in as an **oracle ceiling** to quantify how much feedback *could* help. But the only *deployable* (non-leaking) arm, gold-free, is currently ~neutral → it needs a better critic before in-loop integration is worthwhile.
7. **Which arm first?** Implement **gold_aware_stripped as an oracle upper-bound diagnostic** (clearly labelled leaky/non-deployable) to measure the ceiling, and in parallel **improve the gold-free critic** (better prompt / verdict calibration / maybe a stronger critic model) since it is the only path that can ship.

---

## Recommended implementation
- **feedback access:** start with **gold-aware** *as an oracle upper-bound diagnostic only* (it leaks ~95% → NOT deployable); the deployable target is **gold-free**, which needs a stronger/better-calibrated critic before it helps.
- **feedback input view:** **stripped** (better density *and* ~2.8× cheaper than full; full-reasoning feedback gave no benefit).
- **recombination candidate view:** **strip=true fixed** (unchanged; confirmed as the right setting).
- **proceed to real in-loop Feedback-SE:** **YES — but as a two-track plan.** (a) Wire **gold_aware_stripped** in-loop as a *ceiling* experiment to confirm the +18% density gain compounds over loops; (b) do **not** ship gold-aware (leakage); invest in making **gold-free-stripped** actually beat no-feedback first. If gold-free can't be made to help, Feedback-SE has no deployable advantage and we stop.

**Open question for Harman:** is an **oracle/leaky** arm acceptable purely as a measurement (to bound feedback value), given it cannot produce clean self-distillation traces? And is improving the gold-free critic (prompt/model) in scope, or should round-1 in-loop use gold-aware only as a ceiling?

**Artifacts:** `scripts/probe_feedback_recombination.py`; `outputs/node1_feedback_probe/{feedback_records.jsonl, recomb_records.jsonl, summary.json}`. No orchestrator change, no SFT, no baseline modified.

---

# Appendix — Harman "stay-close" constraint ablation

**Setup.** Reused the existing feedback (no regeneration), the **same 10 problems / 50 groups /
stripped candidate views / recombination seeds**. Appended Harman's constraint to the recombination
prompt ("…keep the final solution close to the candidate attempts. Prefer repairing, combining,
clarifying… only deviate substantially if approaches are clearly flawed."). 3 arms only (stripped):
`no_feedback_stayclose`, `gold_free_stripped_stayclose`, `gold_aware_stripped_stayclose`. Gold-aware
remains oracle/leaky/diagnostic. Script `scripts/probe_feedback_stayclose.py`; outputs
`outputs/node1_feedback_probe_stayclose/`. (Integrity-checked: reconstructed problems/candidates ==
the feedback file's.)

**Result — stay-close is inert (no measurable effect).**
| arm | solved /10 | correct traces /50 | density | recomb prompt-tok | recomb completion-tok |
|---|---|---|---|---|---|
| old no_feedback | 10 | 39 | 0.78 | 1,809,866 | 235,482 |
| old gold_free_stripped | 10 | 40 | 0.80 | 2,178,728 | 122,930 |
| old gold_aware_stripped | 10 | 46 | 0.92 | 2,160,063 | 77,270 |
| **new no_feedback_stayclose** | 10 | **39** | **0.78** | 1,812,766 | 210,162 |
| **new gold_free_stripped_stayclose** | 10 | **40** | **0.80** | 2,181,628 | 131,157 |
| **new gold_aware_stripped_stayclose** | 10 | **46** | **0.92** | 2,162,963 | 78,909 |

Aggregate correct-traces are **identical** (39 / 40 / 46) for all three arms. Per-group (same seeds):
the constraint flips a few groups symmetrically — no_feedback 2 wrong→right / 2 right→wrong (46/50
unchanged), gold_free 2/2 (46/50), gold_aware 3/3 (44/50) — i.e. **net-zero sampling noise, not a
systematic effect**. Per-problem deltas wiggle ±1–2 in both directions (e.g. hmmt25-000002 no_fb
1→2, hmmt25-000010 no_fb 2→1, aime25-000006 gold_aware 5→3) with no consistent direction. Recomb
decode was roughly flat (no_feedback 235k→210k, −11%, within noise; others ±).

**Answers.**
1. **Does stay-close improve recombination?** **No measurable effect** — density unchanged across all
   three arms; flips are symmetric noise.
2. **Does it make gold-free feedback more useful?** **No** — gold-free stays at 0.80 (≈ no-feedback
   0.78) with and without the constraint; still ~neutral.
3. **Does it reduce solving-from-scratch?** **Cannot confirm from this probe.** Correctness is
   unchanged, and we did not measure output↔candidate *similarity* (the behavioral quantity the
   constraint targets). Critically, this is a **single recombination step**; the constraint's
   hypothesized value is preventing *drift across many loops*, which a one-step offline probe cannot
   exhibit. So "no effect in one step" does NOT rule out a multi-loop benefit.
4. **Include it in future in-loop Feedback-SE?** **Yes, as a zero-cost guardrail** — it neither helped
   nor hurt correctness here and costs nothing, and its intended benefit (anti-drift over loops) is
   only testable in-loop. Keep it on, but it is **not** the lever; the lever is feedback quality
   (gold-free must be made to actually help, per the main probe).

**Caveats:** n=50 groups (±2–3 flips ≈ noise floor; an effect <~6% density would be invisible);
single-step only; correctness-only (no similarity metric). **Artifacts:**
`scripts/probe_feedback_stayclose.py`, `outputs/node1_feedback_probe_stayclose/{recomb_records.jsonl,summary.json}`.
Previous outputs untouched; no orchestrator change; no SFT.
