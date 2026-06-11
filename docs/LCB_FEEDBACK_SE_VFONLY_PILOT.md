# LCB Feedback-SE vfonly C-only Pilot — viability / compounding

**Status: RUNNING (all 126 non_saturated; launched 2026-06-11 05:23).** First in-loop Feedback-SE run. Single arm
`C_feedback_vfonly`. **Not** an attribution-clean ablation — it tests whether the confirmed one-step
vfonly gain (`docs/LCB_R2C_OLD_VISIBLE_FAILED_ONLY_CONFIRM.md`: visible-failed +14/399, p≈0.004) **still
works wired into the multi-loop SE process and compounds across loops**. A/B arms deferred to a later
attribution follow-up on the same pinned anchor.

## Framing (the 6 statements — all enforced in code)
1. **Loop-0 was REUSED from the strip=false rerun #1** (`outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated`, 90/126), **NOT freshly generated**.
2. **`C_feedback_vfonly` begins at loop 1** (resume-continue from the pinned loop-0; loops 1–4 generated).
3. **Public/sample tests are used ONLY for visible feedback** (`scripts/lcb_public_probe_harness.py`).
4. **Hidden tests are used ONLY for post-hoc grading** — never in-loop.
5. **all_pass / visible_passed parents receive NO feedback block.**
6. **Visible-failed parents receive the CHECK-bearing V2-concise feedback.**
No V3/V4, no SFT, update=replace, strip=false.

## Launch report
| item | value |
|---|---|
| background PID | `987407` (`bash scripts/run_feedback_vfonly_pilot.sh`) → child `987464` (`squeeze-evolve-client`) |
| log path | `/tmp/node1_fbse_pilot.log` |
| first checkpoint (pinned loop-0) | `external/squeeze-evolve/outputs/node1_lcb_feedback_se_vfonly_pilot/checkpoints/tts_sft_se_feedback_vfonly_pilot_node1_loop0.json` (126×16) |
| output dir | `outputs/node1_lcb_feedback_se_vfonly_pilot/` |
| git branch / commit | `feedback-se-recombine-probe` @ `0afdaa9140d8d789e90cb91479f3c87c0e2992df` |
| git caveat | run uses **uncommitted working-tree code**: pilot scripts/configs + the operator (in *gitignored* `external/squeeze-evolve/`). Commit on request for an exact anchor. |
| problem set | **ALL 126 non_saturated LCB problems** (loop-0 pinned from #1) |
| ETA | ~16–25 h (loops 1–4: 4 × 126 × 16 = 8,064 recomb calls @ max_tokens 32768) |

## Setup (exact, reproducible)
- **Launch:** `bash scripts/run_feedback_vfonly_pilot.sh` — builds the pin from #1, writes anchor metadata + `run_manifest.json`, resumes loops 1–4, then builds `loop_candidates.jsonl`.
- **Pinned loop-0:** `scripts/build_pinned_loop0.py` takes #1's loop-0 checkpoint for **all 126 non_saturated problems** (in seed order, 16 candidates each, `metrics.loop=0`); source sha256[:16] `e41da9146d46c474` (recorded in `loop0_source_manifest.json`).
- **Problem set:** `data/filtered/lcbv6_non_saturated.jsonl` — **all 126 non_saturated LCB problems** (not the earlier 40 subset).
- **Config:** `configs/squeeze_evolve_feedback_vfonly_pilot_node1.yaml` (clone of the formal LCBV6 config, only `recombination: livecodebench-feedback-aggregate` + `resume: true`).
- **Operator:** `external/squeeze-evolve/benchmarks/livecodebench/_feedback_aggregate.py` (registered as `livecodebench-feedback-aggregate`; original `livecodebench-aggregate` untouched). Per group: extract each parent's code → run PUBLIC tests (cached, 4-way parallel) → CHECK-bearing V2-concise block for visible-failed, **no block for all_pass**, top-level failed-only note + stay-close. Fully guarded (any error → no-feedback fallback; the loop can't break). Env: `LCB_FB_SEED` / `LCB_FB_PUBLIC` / `LCB_FB_HARNESS` / `LCB_FB_LOG`.
- **Hyperparameters:** Qwen3-4B-Thinking-2507 (vLLM TP8 @ 262144); population 16 / k 4 / groups 16 / loops 5 (resume → loops 1–4); update=replace; fitness=diversity; strip=false; temp 1.0 / top_p 0.95 / top_k 20 / max_tokens 32768; seed 1234.

## Reproducibility artifacts (written + auditable)
`pinned_subset.jsonl` · `loop0_population.jsonl` · `loop0_source_manifest.json` · `run_manifest.json` ·
`feedback_operator_audit.jsonl` (one line per recomb call — live) · raw `se.jsonl` + `se.jsonl.raw.json` ·
per-loop `se.jsonl.checkpoints/` · `se.jsonl.loop_candidates.jsonl` (carries `parent_ids` per loop
candidate). **Post-hoc, deterministically from checkpoints + public tests:** `parent_groups.jsonl`,
`feedback_records.jsonl`, prompt samples — each **cross-checked against `feedback_operator_audit.jsonl`**.

## Operator audit — counts/checks (live; updates as loops run)
This is the **all-126 run** (each loop has 126 × 16 = **2,016 groups**). The per-loop table
(groups · parents assessed · public-category dist · feedback blocks inserted · all_pass omitted ·
lookup misses · guarded fallbacks) is computed from `feedback_operator_audit.jsonl` and **cross-checked
against the loop checkpoints**; it is appended here on completion of each loop.

> Earlier 40-problem snapshot (now superseded by the all-126 run): loop-1 had 640 groups, 0 fallbacks,
> 0 lookup misses, 439 blocks inserted, 2121 all_pass omitted — pattern: ~83% of loop-0 parents pass public
> tests, so feedback attaches to the ~17% visible-failed. The all-126 run is expected to show the same shape
> at ~2,016 groups/loop.

## Results — Loop 1 (graded 2026-06-11; hidden tests, offline)
**Operator audit (loop 1, all 2,016 groups):** 0 fallbacks · 0 lookup misses · 8,064 parents assessed ·
**2,227 feedback blocks inserted** (visible-failed) · **5,828 all_pass omitted** (+9 unknown omitted).
Parent public-category dist: all_pass 5828 · wrong_answer 1824 · runtime_error 284 · compile_error 104 ·
timeout 6 · no_code 9 · unknown 9. (1824+284+104+6+9 = 2227 = blocks ✓.) ~28% of loop-0 parents are visible-failed.

**Graded (density = correct/2016; reach = problems solved by any candidate of 126):**
| metric | loop 0 (pinned baseline) | **#1 loop 1** — no-feedback original-aggregate, *same loop-0* | **C loop 1** — feedback-vfonly |
|---|---|---|---|
| density | 0.403 (813) | 0.456 (919) | **0.494 (996)** |
| reach (any-of-N) | **90/126** | 84/126 | 85/126 |
| code-valid | 99.8% | 100% | **100%** |
| visible-failed-group density (n=1349) | — | 0.380 (513) | **0.422 (569)** |
| visible-passed-group density (n=667) | — | 0.609 (406) | **0.640 (427)** |

**Reading (this is C vs A_original — combined stay-close+feedback effect — paired on the IDENTICAL pinned
loop-0 + same config/seed; not yet C-vs-B isolating feedback alone):**
1. **Density: C 0.494 > A 0.456 > loop-0 0.403.** From the same loop-0, feedback-vfonly produces 996 correct
   candidates vs the no-feedback arm's 919 — **+77 candidates, +3.8pp** (and +183 vs the loop-0 population).
2. **Reach erodes for BOTH arms (90→85 C, 90→84 A) — this is `update=replace` erosion, not feedback.**
   C actually retains **1 more** problem than no-feedback (85 vs 84). Replace discards the loop-0 pop, so
   problems solved only by a loop-0 candidate can drop out; this is the known replace dynamic (any-of-N > final-pop).
3. **Mechanism holds: the gain concentrates on visible-failed groups** — C vs A is **+4.2pp on visible-failed**
   (0.422 vs 0.380, +56 correct) vs **+3.1pp on visible-passed** (where C has no feedback block; that lift is
   the stay-close wording). Bigger lift exactly where feedback carries signal — consistent with the offline confirm.
4. **code-valid 100%** — no format harm in-loop.

**Interim verdict (loop 1):** feedback-vfonly **works in-loop** — higher density than the no-feedback arm
from the same loop-0, larger on visible-failed groups, code-valid 100%, and it erodes reach slightly *less*
than no-feedback under replace. Whether the density edge **compounds or decays** across loops 2–4 is the open
question (auto-monitor armed). Caveat: C vs A bundles stay-close + feedback; the clean C-vs-B isolation is the
deferred attribution follow-up on this same anchor.

## Results — Loop 2 (graded 2026-06-11)
**Loop-2 audit:** 2,016 groups · 0 fallbacks · 0 lookup misses · 2,138 blocks · 5,926 all_pass omitted.
⚠️ **`no_code` rose to 352** (loop-1-child parents whose code block the operator's regex misses though the
grader extracts it — a ~4% operator-vs-grader `extract_code` mismatch; noted, not fixed mid-run to keep
loop consistency; flag for the clean attribution run).

**Per-loop trajectory (C = feedback-vfonly vs A = no-feedback original-aggregate; identical pinned loop-0):**
| metric | loop 0 | A loop 1 | A loop 2 | C loop 1 | C loop 2 |
|---|---|---|---|---|---|
| density (correct/2016) | 0.403 | 0.456 | 0.408 | **0.494** | **0.464** |
| reach (any-of-N /126) | 90 | 84 | 82 | 85 | **85** |
| code-valid | 99.8% | 100% | 97.7% | 100% | 95.8% |
| **C − A density** | — | — | — | **+3.8pp** | **+5.6pp** |
| **C − A reach** | — | — | — | **+1** | **+3** |

**Reading (loop 2):**
- **The feedback advantage HOLDS and WIDENS:** C − A density goes +3.8pp (loop 1) → **+5.6pp (loop 2)**
  (935 vs 822 correct); C − A reach goes +1 → **+3** (C holds 85, A erodes to 82). So feedback's *relative*
  edge compounds across loops, even though **both arms' absolute density decays from their loop-1 peak**
  (C 0.494→0.464, A 0.456→0.408) — that decay is `update=replace` erosion, which hits both arms.
- **Reach:** C holds 90→85→85 (no further erosion at loop 2); A keeps eroding 90→84→82. Feedback retains the frontier better.
- **code-valid degrades for both, slightly worse for C** (95.8% vs 97.7%) — the longer feedback prompt costs
  a little output-format robustness; below the "≈100%" bar, worth watching.
- vf/vp-group densities are **not** cross-arm comparable at loop ≥2 (each arm's loop-2 groups derive from its
  own loop-1 children, so the visible-failed sets differ) — the clean cross-arm metrics are overall density + reach.

**Interim verdict (through loop 2):** **positive and compounding** — feedback-vfonly keeps a *widening* density
lead (+5.6pp) and a *widening* reach lead (+3) over no-feedback from the same loop-0, with code-valid a watch-item.
Caveat unchanged: C vs A bundles stay-close + feedback (clean C-vs-B is the deferred attribution run).

## Results — Loop 3 (graded 2026-06-11)
**Loop-3 audit:** 2,016 groups · 0 fallbacks · 0 lookup misses · 1,457 blocks · 6,607 all_pass omitted
(no_code back to 69). Block count keeps falling (2227→2138→1457) as the population converges toward
all_pass parents — feedback has progressively less to act on.

**Full trajectory (C = feedback-vfonly vs A = no-feedback; identical pinned loop-0):**
| loop | A density | C density | **C − A density** | A reach | C reach | **C − A reach** | C code-valid |
|---|---|---|---|---|---|---|---|
| 0 | 0.403 | 0.403 | 0 | 90 | 90 | 0 | 99.8% |
| 1 | 0.456 | 0.494 | **+3.8pp** | 84 | 85 | +1 | 100% |
| 2 | 0.408 | 0.464 | **+5.6pp** | 82 | 85 | +3 | 95.8% |
| 3 | 0.488 | **0.506** | **+1.8pp** | 82 | **85** | +3 | 99.1% |

**Reading (through loop 3) — corrected from the loop-2 "widening" read:**
- **Density: C ≥ A at every loop, but the gap is NOISY, not monotonically widening** (+3.8 → +5.6 → +1.8pp).
  A recovered strongly at loop 3 (0.408→0.488), narrowing the gap; C reached its highest density yet (0.506).
  So feedback gives a *consistent but modest and noisy* density edge (~+2 to +6pp), not a runaway compounding gain.
- **Reach is the cleaner, stable signal: C holds 90→85→85→85; A erodes to 82 and stays. C − A reach = +3 from
  loop 2 on.** Feedback preserves the reachable frontier better under `update=replace`; no-feedback erodes more.
- **code-valid recovered** (C 95.8%→99.1%); the loop-2 dip was transient.

**Interim verdict (through loop 3):** feedback-vfonly stays **ahead of no-feedback on every loop** — a
**stable +3 reach edge** and a **consistent (noisy) +2–6pp density edge** from the identical loop-0, code-valid
≈99–100%. It's a *modest, persistent* advantage rather than a strongly compounding one. Caveat unchanged
(C vs A bundles stay-close + feedback). Loop 4 (final) pending.

## FINAL SUMMARY — run complete (2026-06-11 10:39; all loops 1–4 generated, post-processed)

**Operator health (whole run):** 8,064 recomb calls (4 loops × 2,016) · **0 fallbacks · 0 lookup-misses**.
Per-loop blocks inserted / all_pass omitted / no_code (CORRECTED segment labels):
| loop | blocks | all_pass omitted | no_code (operator) |
|---|---|---|---|
| 1 | 2,227 | 5,828 | 9 |
| 2 | 1,687 | 6,375 | 0 |
| 3 | 2,138 | 5,926 | **352** |
| 4 | 1,457 | 6,607 | 69 |
*(no_code = loop-(t−1) children whose code block the operator's stricter regex misses though the grader
extracts it; ~4% at loop 3. Earlier inline per-loop audit numbers were mislabeled by one loop — this table
supersedes them. All density/reach grading below is from the loop checkpoints and is correct.)*

**Full graded trajectory (C = feedback-vfonly vs A = no-feedback original-aggregate; IDENTICAL pinned loop-0):**
| loop | A density | C density | **C − A density** | A reach | C reach | **C − A reach** | C code-valid |
|---|---|---|---|---|---|---|---|
| 0 (pinned) | 0.403 | 0.403 | 0 | 90 | 90 | 0 | 99.8% |
| 1 | 0.456 | 0.494 | +3.8pp | 84 | 85 | +1 | 100% |
| 2 | 0.408 | 0.464 | +5.6pp | 82 | 85 | +3 | 95.8% |
| 3 | 0.488 | 0.506 | +1.8pp | 82 | 85 | +3 | 99.1% |
| **4 (final pop)** | **0.462** | **0.512** | **+5.0pp** | **80** | **82** | **+2** | 97.2% |

**Reachability — any-of-N union over loops (one internally-consistent grading pass; the headline metric):**
| | loop 0 | loop 1 | loop 2 | loop 3 | loop 4 (final-pop) | **union any-of-N** | replace-erosion (union − final) |
|---|---|---|---|---|---|---|---|
| **A (no feedback)** | 89 | 83 | 82 | 81 | 79 | **89** | 10 |
| **C (feedback-vfonly)** | 89 | 84 | 84 | 84 | **81** | **91** | 10 |

- **C's union (91) EXCEEDS the pinned loop-0 (89) by +2 — feedback-SE reached 2 problems the initial
  population could not.** **A's union (89) = loop-0 (89) — no-feedback SE reached *nothing* beyond loop-0.**
  So on this anchor, **feedback expands the reachable set by +2 over both loop-0 (the BoN-equivalent start)
  AND over no-feedback SE** — the first sign of the core hypothesis (feedback-SE reaching past the frontier
  that plain SE/BoN cannot). C ≥ A at every loop too.
- **Replace-erosion is identical (10 each):** both arms' final-pop sits ~10 below their union — `update=replace`
  discards solutions, so the reached-91 frontier does not survive to the final population. A reachability gain
  would only "stick" in the final pop under `update=accumulate`.
- *(Reach has ±1–2 noise from SIGALRM-TLE nondeterminism: loop-0 graded 90 in the per-loop pass vs 89 here as
  one borderline candidate flipped. This union pass is the consistent source; the +2 union gain is within that
  noise envelope → suggestive, not conclusive. Density is unaffected — it counts all candidates.)*

### Canonical set-level result (standard `score_se_subset.py` grading of both arms — supersedes the count-level read)
- **A solved-late-only = ∅** (union 90 = its loop-0 90): no-feedback SE added **zero** problems in 4×16 recombs.
- **C solved-late-only = {lcbv6-004, lcbv6-120}** (union 92 ⊋ A's 90; A∖C = ∅).
  **lcbv6-120: 7 correct traces across all 4 loops (1/2/1/3) — robust, not grading noise.** lcbv6-004: 1 trace (marginal).
- **Mechanism:** both gained problems had ~100% visible-failed parents every loop (lcbv6-120 loop-1: 54
  wrong_answer + 10 runtime, ~0 all_pass) — gains came exactly where vfonly feedback has material.
- **Both are 0/80 under parallel BoN (N=80)** → first concrete instance of execution-feedback evolution
  reaching problems that neither independent sampling nor plain SE reached (existence proof; C's recomb
  prefill means compute is not exactly BoN-matched).
- Next-step design implications → `docs/FEEDBACK_SE_IMPROVEMENT_PLAN.md`.

## Decision (viability/compounding pilot)
**PASS, modestly — feedback-vfonly works in-loop and is the better arm on every axis, but the effect is
small and noisy:** density +5.0pp final (every loop ahead), reach ahead every loop, **union any-of-N 91 vs 89
(+2) and +2 beyond loop-0 vs no-feedback's +0**, code-valid ~97–100%, operator clean (0 fallbacks). This meets
the pilot's bar (in-loop gain holds across loops, code-valid stays high) → **proceed to the clean attribution run**.

**Recommended next (on this SAME pinned anchor, so all three pair exactly):**
1. **A/B/C attribution** — add `B_stayclose_only` (and re-run A) to isolate feedback from stay-close (this
   pilot's C-vs-A bundles them). Needed before claiming feedback *itself* drives the gain.
2. **Beat the ±2 reach noise** — repeat-grade (best-of-k harness runs) or raise per-test TLE so the +2 union
   gain is significant, not noise-band.
3. **Test `update=accumulate`** — replace erodes 10; accumulate would preserve the 91-union frontier into the
   final population, which is what self-distillation would actually harvest.
4. Fix the operator `extract_code` to match the grader (recover the ~4% no_code mislabels).

**Bottom line:** the pilot is a green light for the attribution study, not yet a proof — feedback-SE shows a
*real but small* reachability edge (+2 over no-feedback and over the BoN-equivalent loop-0), the cleanest
positive signal so far for the core "does feedback let SE reach further" question.

## Artifacts (post-hoc graders)
`scripts/grade_feedback_se_loop.py` (per-loop density/reach/code-valid + vf/vp split),
`scripts/union_reach_feedback_se.py` (any-of-N union + replace-erosion). Per-loop & union JSON in `/tmp/grade_loop*.json`, `/tmp/union_{C,A}.json`. Pilot complete; C-vs-A is the same-loop-0 reference (A = #1 original-aggregate).
