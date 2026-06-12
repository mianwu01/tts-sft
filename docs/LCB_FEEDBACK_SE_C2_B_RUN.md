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

## Results — Loop 1 (C2 graded 2026-06-11 20:5x; B not started yet)
**Aggregate (vs the already-graded arms at loop 1, identical pinned loop-0):**
| arm | density | correct/2016 | reach | code-valid |
|---|---|---|---|---|
| A original | 0.456 | 919 | 84 | 100% |
| C vfonly | 0.494 | 996 | 85 | 100% |
| **C2 vfonly+disagreement** | **0.495** | **998** | 84 | **100%** |

C2 ≈ C at the aggregate — expected by construction: the arms differ on only 132/2016 groups (6.5%).

**The paired slice that matters — the 132 disagreement groups (identical parents across arms, same seed):**
| | correct /132 |
|---|---|
| C (vfonly = silent on these groups) | 40 |
| **C2 (+factual disagreement comparison)** | **44** |
**Flips: C2 wins 6 / losses 2 (net +4).** This **replicates the offline probe in-loop** (offline: 41→46,
5W/0L). Pooled offline+in-loop: **11W/2L, p≈0.011.** The disagreement signal survives the transition into
the real SE loop at the same per-group effect size (~+3pp on treated groups), with code-valid 100%.

Whether the treated groups' better children compound through loops 2–4 (and add solved-late-only problems)
is what the remaining loops + union grading will show.

## Results — Loop 2 (C2 graded 2026-06-11 22:1x)
| loop | A density | C density | **C2 density** | A reach | C reach | **C2 reach** | C2 code-valid |
|---|---|---|---|---|---|---|---|
| 1 | 0.456 | 0.494 | **0.495** | 84 | 85 | 84 | 100% |
| 2 | 0.408 | 0.464 | **0.467** | 82 | 85 | **81** | 95.6% |

- **Density: C2 keeps a small edge over C** (941 vs 935; both well above A's 822). The loop-2 code-valid
  dip (95.6%) is the known recombination-generic effect (seen in A, C, node3).
- **Reach 81 vs C's 85 — watch item.** Within trajectory-divergence + TLE noise (per-loop reach swings
  ±1–2; the union/solved-late-only sets at completion are the meaningful comparison), but worth tracking.
- **Audit shift (the designed mechanism visibly working):** loop-2 groups = visible_failed **759** (down
  from 1348 as children pass public tests) + **disagreement 223** (UP from 132 — the comparison path
  fires more as populations turn all_pass) + silent 1034; 0 fallbacks. Feedback coverage at loop 2:
  **48.7% for C2 vs ~37% for C** — disagreement keeps feedback alive exactly where vfonly goes silent.

## Results — Loop 3 (C2 graded 2026-06-11 23:1x)
| loop | A density | C density | **C2 density** | A reach | C reach | **C2 reach** | C2 code-valid |
|---|---|---|---|---|---|---|---|
| 3 | 0.488 | 0.506 | **0.508** | 82 | 85 | **84** | 98.9% |

- C2 density 1025 — slightly above C's 1020 again (C2 ≥ C at every loop so far: 998/996, 941/935, 1025/1020).
- **Reach recovered 81→84** (the loop-2 dip was trajectory/TLE noise as suspected); code-valid recovered to 98.9% (same pattern as C).
- Loop-3 audit: visible_failed 984, **disagreement 137**, silent 895; 0 fallbacks. Coverage 55.6%.

## C2 COMPLETE (loops 1–4 done 2026-06-11 23:58; B auto-started, running)

**Per-loop (A and C = same-anchor references):**
| loop | A density | C density | **C2 density** | A reach | C reach | **C2 reach** | C2 code-valid |
|---|---|---|---|---|---|---|---|
| 1 | 0.456 | 0.494 | **0.495** (998) | 84 | 85 | 84 | 100% |
| 2 | 0.408 | 0.464 | **0.467** (941) | 82 | 85 | 81 | 95.6% |
| 3 | 0.488 | 0.506 | **0.508** (1025) | 82 | 85 | 84 | 98.9% |
| 4 | 0.462 | 0.512 | 0.510 (1028) | 80 | 82 | 80 | 96.7% |

**Full-run aggregates (union-pass methodology, same as A/C):**
| | A | C | **C2** |
|---|---|---|---|
| harvest (correct traces, loops 1–4) | 3,657 | 3,983 | **3,992** |
| union any-of-N | 89 | 91 | **91** |
| solved-late-only set | ∅ | {004 (fragile), 120} | **{120}** |
| replace-erosion (union − final-pop) | 10 | 10 | 11 |
| operator fallbacks (8,064 calls) | n/a | 0 | **0** |

**Honest reading of C2 vs C (trajectory level):**
1. **The treated-slice effect is real and replicated** (loop-1 paired slice on the 132 disagreement
   groups: 40→44, 6W/2L; pooled with the offline probe 11W/2L, p≈0.011) — disagreement feedback helps
   exactly where it fires.
2. **At the aggregate level the add-on is ~neutral-to-slightly-positive:** harvest +9 traces over C
   (3,992 vs 3,983; both ≈ +9% over A); same union (91); C2 ≥ C on density at loops 1–3, −4 at loop 4.
   The treatment touches only ~7–11% of groups per loop, and its localized gains are diluted by replace
   churn and sampling noise across the other ~90%.
3. **Reachability: C2 retains the robust gain ({lcbv6-120}, again multi-trace) but not C's fragile one
   ({lcbv6-004}, which was a single trace in C).** No new late-only problems this trajectory.
4. **Operator health perfect:** 8,064 calls, 0 fallbacks; disagreement path fired 132/223/137/~ per loop —
   keeping feedback coverage ~49–73% vs C's shrinking ~28–67%.

**Interim conclusion:** the disagreement add-on is *safe, cheap, mechanistically validated, and slightly
positive*, but at pop16/replace it does **not** yet translate into trajectory-level gains beyond vfonly —
consistent with the broader lesson that prompt-level feedback alone has limited compounding under blind
selection/replace (→ P2 selection-level feedback and P3 elitism are the levers that would let treated
groups' better children actually shape the population). Final attribution awaits **B** (running).

## B Loop 1 → the four-way PAIRED attribution at loop 1 (graded 2026-06-12 01:5x)
All four arms share the identical pinned loop-0 AND identical loop-1 group compositions (same seed):
| arm | density | correct/2016 | reach | code-valid |
|---|---|---|---|---|
| A original | 0.456 | 919 | 84 | 100% |
| **B stay-close only** | **0.477** | **961** | **86** | 100% |
| C stay-close+vfonly | 0.494 | 996 | 85 | 100% |
| C2 +disagreement | 0.495 | 998 | 84 | 100% |

**Attribution (paired differences at loop 1):**
- **Stay-close wording (B−A): +42 correct (+2.1pp)**
- **vfonly execution feedback (C−B): +35 correct (+1.7pp)**
- Disagreement add-on (C2−C): +2 aggregate (treated 132-group slice: +4, 6W/2L)

**Reading:** C's loop-1 edge over the original operator (+77) splits roughly **half wording, half feedback**
— both real, neither dominant. Directionally consistent with the offline one-step probes (stay-close +4–5pp,
vfonly +2.5pp there). Reach at loop 1: B's 86 is the highest single-loop value (±1–2 noise band).
B loops 2–4 will show whether the wording-only arm erodes like A (the no-feedback arms eroded fastest in
trajectory) or holds like the feedback arms.

## FINAL — both arms complete (B done 2026-06-12 04:48; graded 10:1x). The four-way attribution.

**Density per loop (correct/2016; all arms from the identical pinned loop-0):**
| loop | A original | B stay-close | C +vfonly | C2 +disagreement |
|---|---|---|---|---|
| 1 | 0.456 (919) | 0.477 (961) | 0.494 (996) | 0.495 (998) |
| 2 | 0.408 (822) | 0.450 (908) | 0.464 (935) | 0.467 (941) |
| 3 | 0.488 (984) | 0.490 (987) | 0.506 (1020) | 0.508 (1025) |
| 4 | 0.462 (932) | 0.494 (996) | **0.512 (1032)** | 0.510 (1028) |

**Reach per loop / union / sets / harvest:**
| | A | B | C | C2 |
|---|---|---|---|---|
| reach 1→4 | 84/82/82/80 | 86/81/82/80 | **85/85/85/82** | 84/81/84/80 |
| union any-of-N | 89–90 | 91 | 91–92 | 91 |
| **solved-late-only** | **∅** | {004: 1 trace} | {004: 1 trace, **120: 7 traces**} | {**120**: multi-trace} |
| harvest (correct traces L1–4) | 3,657 | 3,852 | **3,983** | **3,992** |
| replace-erosion | 10 | 11 | 10 | 11 |

### Attribution (the answers)
1. **Stay-close wording (B−A): real, ~+2pp/loop, +195 harvest.** Pure prompt-framing effect, costs nothing.
2. **vfonly execution feedback (C−B): real ON TOP of wording, +131 harvest (+1.4–1.8pp/loop), and —
   decisively — it is what PRESERVES THE FRONTIER:** C holds reach 85/85/85 across loops while B erodes
   like A (86→81→82→80). Wording does not protect reach; feedback does.
3. **Reachability is feedback-specific:** lcbv6-004 (1 trace each in B and C) is a borderline problem any
   stay-close arm occasionally hits — NOT a feedback effect. **lcbv6-120 is the real reachability gain:
   reached repeatedly by BOTH feedback arms (C: 7 traces; C2: multi-trace) and NEVER by A or B** (0/80
   under BoN N=80 too). The only robust frontier expansion in the whole study is attributable to
   execution feedback specifically.
4. **Disagreement add-on (C2−C): +9 harvest, ~0 aggregate; real on its treated slice** (132 groups:
   40→44, 6W/2L; pooled with offline 11W/2L p≈0.011) but diluted by blind selection/replace.

### Bottom line
- **Best deployable configuration today: C (stay-close + vfonly), with C2 equal-or-slightly-better and
  strictly better-covered.** Feedback's contributions decompose cleanly: wording lifts density; execution
  feedback lifts density further, preserves reach across loops, and is solely responsible for the robust
  reachability gain.
- **The ceiling of prompt-level feedback is now mapped:** all arms erode ~10–11 problems under blind
  replace, and treated-slice gains don't compound through uniform selection. The next lever is putting
  the signal into the machinery (P2 selection / P3 elitist update) — coordinate with the parallel
  verifier-ops (arm V) line before building.
- Operator health across both new runs: **0 fallbacks / 16,128 calls**; code-valid ≈93–100% (loop-2 dip
  recombination-generic, all arms).
