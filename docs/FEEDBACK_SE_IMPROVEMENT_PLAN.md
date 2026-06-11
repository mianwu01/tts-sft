# Feedback-SE: Post-Pilot Review & Improvement Plan

## EXECUTION STATUS (updated 2026-06-11 19:35 — plan now partially executed)
| item | status | outcome / pointer |
|---|---|---|
| **P1 disagreement feedback** | ✅ **offline gate PASSED → in-loop C2 COMPLETE** | probe: 19.8% incidence, **5W/0L p≈0.031, blind-spot 0/58→2/58** (`docs/LCB_DISAGREEMENT_PROBE.md`). **In-loop C2 (done 06-11 23:58):** treated-slice replicated (loop-1 paired 40→44, 6W/2L; pooled 11W/2L p≈0.011); aggregate ~neutral-to-slightly-positive vs C (harvest 3,992 vs 3,983; union 91=91; late-only {120} kept, fragile {004} not); 0 fallbacks/8,064 calls; coverage 49–73% vs C's 28–67%. **Lesson: prompt-level feedback alone doesn't compound under blind selection/replace → P2/P3 are the next levers** (`docs/LCB_FEEDBACK_SE_C2_B_RUN.md`). |
| **P4 B-arm attribution** | ▶ **RUNNING** (auto-started after C2) | `livecodebench-stayclose-aggregate` (stay-close, no feedback), same pinned anchor → completes A/B/C/C2; B−A = wording, C−B = vfonly feedback, C2−C = disagreement add-on. |
| **P5 measurement hardening** | ✅ shipped | `scripts/lcb_grading.py`: persistent code-hash→verdict cache (`outputs/grading_cache/`) + retry-on-timeout-only; wired into `grade_feedback_se_loop.py` + `union_reach_feedback_se.py`; canonical `score_se_subset.py` untouched. Operator `extract_code` now **imports the grader's extractor** (verbatim-regex fallback) — the ~4% no_code mislabels are gone (loop-1 cross-check: 1348 vs 1349). |
| method git-save | ✅ pushed | `se_patches/` snapshot (operators + SE tracked-diff + INSTALL.md) + scripts/configs/docs; branch `feedback-se-recombine-probe` @ `7d68f58`, P1 @ `ed6ddc3`. |
| **P2 public-aware selection** | ⏸ pending | additive `selection` operator (registry verified open); revisit after C2/B results — pairs with P1 to avoid concentrating the blind spot. |
| **P3 elitist/accumulate update** | ⏸ pending | run winner × `update:accumulate` (turnkey pipeline exists, task #12) or additive elitist-replace, after C2/B. |
| **P6 dead ends** | ✖ closed | funnel, V3/V4 critics, CHECK-removed format, gold-aware, custom-fitness route. |

Probe-input policy used for P1 (was an open ask): model-proposed inputs, INPUTS ONLY (no expected
outputs anywhere), cached at `data/filtered/lcbv6_probe_inputs.jsonl` (125/126 problems, median 6).

*(Original plan below, written before execution.)*

---

Synthesizes the Node1 vfonly multi-loop pilot (`LCB_FEEDBACK_SE_VFONLY_PILOT.md`), Node3's pyramid pilot
(`NODE3_PYRAMID_PILOT.md`), and Node2's answer-hidden math probe (`MATH_FEEDBACK_ANSWER_HIDDEN_PROBE.md`)
into a diagnosis of what limits the current design and a prioritized, feasibility-checked upgrade path.
All proposals respect the hard gates: official SE codebase (additive registry operators only), public/sample
tests only for feedback, hidden tests post-hoc only, no V3/V4, no SFT yet, Harman sign-off before generation.

## 1) What the evidence now says (cross-node)
1. **The vfonly prompt-feedback gain is real, replicated, and modest.** Loop-1 density gain replicates
   cross-box to 3 decimals (Node1 .494, Node3 .497 vs A .456); C > A at every loop (final +5.0pp); Node3's
   independent grading of our run shows mild late-loop density compounding at constant width (.509/.514).
2. **Set-level reachability is the sharpest finding (canonical grading, both arms):**
   - **A (no-feedback SE): solved-late-only = ∅** — zero problems beyond its own loop-0 in 4×16 recombs (union 90 = loop-0 90).
   - **C (feedback-SE): solved-late-only = {lcbv6-004, lcbv6-120}** (union 92 ⊋ A's 90; A∖C = ∅).
   - **lcbv6-120 is robust, not noise: 7 correct traces across all 4 loops** (1/2/1/3); lcbv6-004 is marginal (1 trace, loop 4).
   - **Mechanism check passes:** both gained problems had ~100% *visible-failed* parents every loop (e.g.
     lcbv6-120 loop-1: 54 wrong_answer + 10 runtime_error, ~0 all_pass) — the gains came exactly from the
     regime where vfonly feedback has material.
   - **Both are 0/80 under parallel BoN (N=80)** and unsolved by plain SE → **first concrete instance of the
     core thesis: execution-feedback evolution reached problems neither independent sampling nor plain SE
     reached** (caveat: C's recombination prefill makes compute not exactly BoN-matched; this is an
     existence proof, not yet a matched-compute claim).
3. **The funnel is dead for quality:** Node3's 16→8→4→2 schedule ties traces/call at matched compute but
   loses −19 live-pop coverage and −24 final-pop erosion. Only use it for cheap wall-clock runs.
4. **Label-free population-consistency feedback works on math (M4: +65 net flips, p≈5e-9, ties the
   verifier-verdict arm, best on HARD problems)** — population→group information flow, no labels. This is
   the strongest evidence-backed direction not yet ported to code.
5. **Replace-erosion is arm-independent (−10 both):** the reached frontier doesn't survive to the final pop.
6. **Code-valid dip at loop-2 children (~5%) is recombination-generic** (both Node1 runs + Node3) — not a
   feedback cost.
7. **Grading noise:** ±1–2 problems per pass from SIGALRM/TLE nondeterminism → absolute reach counts are
   noise-band; set-level invariants (e.g. #2) and large-n density are the trustworthy statements.

## 2) Diagnosed limiters (each with evidence)
- **L1 — The blind spot dominates: ~44% of all_pass parents are hidden-WRONG and receive NO signal.**
  Loop-0: 72.3% of parents all_pass vs 40.3% hidden-correct. By loop 4 only 18.1% of parents carry a
  visible failure → vfonly's raw material shrinks every loop. This is the binding constraint, and exactly
  the regime Node2's M4 fixed on math.
- **L2 — Feedback only enters the PROMPT.** Selection is uniform and update is blind replace: the loop
  applies zero survival pressure toward publicly-passing lineages, and recombination groups are random
  (can be all-failed or all-passed). The evolutionary machinery itself is feedback-free.
- **L3 — Replace-erosion (−10)**: solved problems drop out of the population; nothing preserves the frontier.
- **L4 — Measurement noise**: ±1–2 reach per grading pass; operator `extract_code` stricter than the grader
  (~4% `no_code` mislabels, loop-3 spike 352).
- **NOT a limiter:** population diversity (12–13/16 unique codes per problem in both arms — no
  stay-close/feedback homogenization collapse).

## 3) Prioritized improvements (feasibility-checked)
**P1 — Disagreement feedback for all_pass candidates (the M4-analog for code). Highest expected value.**
Targets L1 directly. For groups whose parents pass all public tests, manufacture label-free signal by
**differential testing**: run the k parents on a small set of probe inputs (deterministic mutations/extensions
of public inputs, optionally + cached model-proposed edge cases) and report only **facts**: "Solutions 1 and 3
produce different outputs on input X (S1: …, S3: …); at most one can be correct" / "Solution 2 crashes on
input X". No expected outputs are claimed → non-leaky, label-free, exactly M4's population-consistency
mechanism. Crash-guard: only report disagreement when candidates run cleanly on the probe input.
*Validation gate first (offline, ~1 day, cheap):* one-step probe à la R2c on existing loop-1 groups whose
parents are all all_pass but the problem is unsolved — disagreement blocks vs vfonly(=nothing there) vs
no-feedback. Proceed in-loop only if it wins there.

**P2 — Feedback-aware SELECTION (additive registry operator). Second lever, zero core patches.**
`CODE-SUPPORTED`: `selection` is an open registry (`uniform`/`weighted` registered in
`algorithm/operators.py`; custom ops welcome per its docstring), and selection receives the candidate texts →
a `public-aware` selection operator can run the same cached public-exec side-table as the feedback operator and
(a) weight parent sampling toward public-passers, and/or (b) **compose mixed groups** (passers + failers
together: a working scaffold plus known bugs + their feedback blocks). Keep `fitness: diversity` so
`validate_scoring_policy` never triggers (a custom *fitness* would demand a scoring model — avoid that path).
Risk: selecting for public-pass concentrates the L1 blind spot → pair with P1.

**P3 — Elitist/accumulate UPDATE to stop replace-erosion (targets L3).**
`CODE-SUPPORTED`: `update` is also an open registry (`replace`/`accumulate`). Two options:
(a) `update: accumulate` — native, zero code, pop grows 16→80 (cost grows per loop); turnkey pipeline for
this already exists (task #12). (b) additive `elitist-replace` — children replace pop EXCEPT the top
public-pass candidate(s) per problem are carried forward (constant pop, frontier preserved in-pop).
For the self-distillation harvest the union is what we mine, so P3 is about final-pop quality / the SE story.

**P4 — Attribution B arm (stay-close only) on the SAME pinned anchor. Scientific necessity.**
C-vs-A bundles stay-close+feedback. One run (loops 1–4, same pin, original-prompt-minus-feedback) gives
C−B = feedback alone and B−A = stay-close alone, paired at loop 1 by construction. Without it we cannot
attribute the pilot's edge to feedback.

**P5 — Measurement hardening (do regardless, cheap).**
(a) Grading: per-test TLE 6s→10s + best-of-2 re-run for timeout-category fails + persistent code-hash→verdict
cache → kills the ±1–2 noise and makes reach claims defensible. (b) Fix operator `extract_code` to match the
grader (recovers ~4% mislabeled no_code blocks). (c) Keep reporting set-level invariants (solved-late-only
sets), not just counts.

**P6 — Do NOT pursue:** funnel schedules (Node3: no quality win), V3/V4 LLM critics (truncate/hallucinate),
CHECK-removed format (regressed), gold-aware feedback (leaks ~95%), custom *fitness* route (config validation
demands scoring models — selection route is clean).

## 4) Why this matters for the actual mission (TTS-SFT)
The harvest stat: over loops 1–4 from the same loop-0 and ~+1% tokens, **C produced 3,983 correct traces vs
A's 3,657 (+326, +8.9%)**, with slightly broader problem coverage (union 91 vs 89; A added zero problems).
For self-distillation data generation, feedback-SE is already a strictly better correct-trace generator at
equal budget; P1–P3 aim to grow that gap and make the reach gain unambiguous.

## 5) Proposed sequence (each step gated on Harman for generation)
1. **Now (offline, no GPU):** P5 fixes + P1 offline disagreement probe on existing loop-1 all_pass groups.
2. **Run A:** P4 B-arm on the pinned anchor (≈ the pilot's cost; completes attribution of what we already have).
3. **Run B:** C2 = vfonly + P1 disagreement (+P2 mixed-group selection if its offline sanity check passes),
   same anchor, vs the existing C → does filling the blind spot turn the modest edge into a clear one?
4. **Run C (cheap config change):** the winner × `update: accumulate` (or elitist-replace) → does the frontier
   survive into the final pop?
5. Only then: scale / SFT-data generation discussion with Harman.

## 6) Open asks for Harman
- OK to spend ~2 pilot-equivalents on steps 2–3? Preferred order (attribution-first vs method-first)?
- Probe-input policy for P1: deterministic public-input mutations only, or also allow cached model-proposed
  edge-case inputs (still label-free — used only for disagreement, never as expected outputs)?
- Is elitist-replace acceptable as an additive update operator, or stick to native accumulate?

**Canonical C grading artifacts:** `outputs/node1_lcb_feedback_se_vfonly_pilot/{per_problem.jsonl, genlog.jsonl,
summary.json}` (standard `score_se_subset.py` pipeline, same as all prior runs). §1.2's set facts come from
these + the formal run's `per_problem.jsonl`.
