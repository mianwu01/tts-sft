# LCB Feedback-SE C2 + B Runs — completing the attribution set (A/B/C/C2)

**Status: RUNNING (launched 2026-06-11 18:33, sequential: C2 first, then B auto-starts).**
With **A** (original aggregate) and **C** (feedback-vfonly) already complete on the pinned anchor, these
two runs complete the four-arm attribution set, all from the **identical pinned loop-0** (strip=false
rerun #1, sha16 `e41da9146d46c474`, 126 problems × 16 candidates):

| arm | recombination operator | feedback | status |
|---|---|---|---|
| A | `livecodebench-aggregate` (original) | none, no stay-close | done (formal run) |
| **B** | `livecodebench-stayclose-aggregate` (new, additive) | none — stay-close wording only | **queued (auto-starts after C2)** |
| C | `livecodebench-feedback-aggregate` (frozen vfonly) | V2-concise on visible-failed only | done (pilot) |
| **C2** | `livecodebench-feedback-disagreement-aggregate` (new, additive) | vfonly **+ disagreement comparison** for all-all_pass groups | **RUNNING** |

**Attribution algebra (paired at loop 1 by construction; trajectory comparison at loops 2–4):**
B−A = stay-close wording · C−B = vfonly feedback · C2−C = disagreement add-on.

## C2 design (gate-passed in `docs/LCB_DISAGREEMENT_PROBE.md`: 5W/0L, p≈0.031; blind-spot 0/58→2/58)
Per recombination group:
- any parent **visible-failed** (public tests) → EXACT frozen vfonly behavior (CHECK-bearing V2-concise
  blocks on failed parents, nothing on all_pass parents).
- **all parents all_pass** → differential-test the 4 parents on cached **model-proposed probe inputs**
  (`data/filtered/lcbv6_probe_inputs.jsonl`; INPUTS only — no expected outputs exist anywhere) → if
  cross-candidate disagreement exists, ONE factual `Cross-candidate execution comparison` section
  (≤2 most informative inputs, behaviors clustered, no claim of who is right); else no feedback.
- Leakage policy unchanged: public tests + label-free behavior comparison only; **hidden tests never
  in-loop** (post-hoc grading only). No V3/V4, no SFT.

## Launch report
| item | value |
|---|---|
| launcher | `scripts/run_feedback_se_b_c2.sh` (sequential C2 → B), PID `1168451` |
| log | `/tmp/node1_b_c2.log` |
| C2 output | `outputs/node1_lcb_feedback_se_c2_disagreement/` (run `tts_sft_se_feedback_c2_disagreement_node1`) |
| B output | `outputs/node1_lcb_stayclose_b/` (run `tts_sft_se_stayclose_b_node1`) |
| configs | `configs/squeeze_evolve_feedback_c2_node1.yaml`, `configs/squeeze_evolve_stayclose_b_node1.yaml` |
| hyperparams | identical to A/C: pop 16 / k 4 / groups 16 / loops 5 (pinned loop-0 → loops 1–4 generated), update=replace, fitness=diversity, strip=false, temp 1.0 / top_p 0.95 / top_k 20 / max_tokens 32768, seed 1234 |
| anchor | loop-0 REUSED verbatim from #1 (no new loop-0 generation; `build_pinned_loop0.py` + resume-continue) |
| env contract | `LCB_FB_SEED/PUBLIC/HARNESS/LOG` + new `LCB_FB_PROBE_INPUTS` / `LCB_FB_PROBE_EXEC` |
| ETA | ~5 h per arm (~10–11 h total) |
| git | branch `feedback-se-recombine-probe` @ `ed6ddc3` + the two new operators (snapshot to se_patches on completion) |

## Pre-launch validation (all passed)
1. **Unit (real parents):** B emits stay-close with zero feedback mentions; C2 emits 3 V2 blocks on
   lcbv6-001's visible-failed group and the comparison section (no V2 blocks) on lcbv6-105's
   disagreement group; audit records `none_stayclose_b` / `visible_failed` / `disagreement`.
2. **In-loop smoke (2 problems, real SE client, pinned loop-0):** resume from loop-0 → loop 1 ran; all
   three C2 paths fired in-loop (`visible_failed 4, disagreement 3, none_allpass_agree 1, fallbacks 0`).
3. **Operator hygiene:** extractor = grader's `extract_code` (imported, verbatim-regex fallback); all
   paths wrapped (any error → stay-close no-feedback fallback, audited).

## Live audit — C2 loop 1 (all 2,016 prompts built; generation in progress)
| feedback_type | groups |
|---|---|
| visible_failed (vfonly V2 blocks) | 1,348 |
| **disagreement (new path)** | **132** |
| none_allpass_agree (silent) | 536 |
| fallbacks / lookup misses | **0 / 0** |

Cross-checks: 132 disagreement groups **exactly matches** the offline probe's 132 (deterministic probe
exec, cached); visible-failed 1,348 ≈ the C pilot's 1,349 (1-group shift from the extractor fix).
**Feedback coverage: 66.9% (C) → 73.4% (C2) of groups**, the increase aimed entirely at the blind spot.

## Measurement plan (as each loop checkpoint lands; auto-monitor armed)
Per loop, per arm, with the P5 hardened cached grader (`grade_feedback_se_loop.py`): density, reach,
code-valid; at completion: union any-of-N + **solved-late-only sets** (the noise-robust statement),
`union_reach_feedback_se.py`. Four-way table A/B/C/C2 + the three attribution differences. Key questions:
1. **C2 vs C:** does disagreement feedback add density/reach beyond vfonly — especially new
   solved-late-only problems from all_pass-dominated populations (where C was blind)?
2. **B vs A / C vs B:** how much of C's edge was stay-close wording vs actual feedback?
3. code-valid stays ~100% under the comparison section in-loop?

## Results — PENDING (filled per loop by the auto-monitor workflow)
*(four-way per-loop table + attribution differences + union/solved-late-only sets + examples will be
appended here as checkpoints land.)*
