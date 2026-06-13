# LCB C-strip run — vfonly Feedback-SE with strip_think=true (node3)

**Status: RUNNING (launched 2026-06-12 ~03:0x, node3 box, wrapper PID 302160, log
`/tmp/node3_cstrip.log`). User-directed 2026-06-12.**

**One-variable experiment:** exact clone of arm C (vfonly: deterministic PUBLIC/sample-test
execution feedback on visible-failed parents only) with the ONLY change `strip_think: true` —
parents' `<think>` blocks are stripped by the orchestrator when recombination prompts are
assembled at loops ≥1. Loop-0 is PINNED verbatim from strip=false rerun #1 (sha16
`e41da9146d46c474`) — the identical anchor used by A/B/C/C2/V, so all comparisons stay paired.
(The pinned loop-0 candidates themselves still contain thinking; stripping affects only what the
recombiner READS, not what is stored/graded.)

| | C (done) | **C-strip (this run)** |
|---|---|---|
| recombination | livecodebench-feedback-aggregate | same |
| feedback | public tests, visible-failed only | same |
| strip_think | false (full thinking in prompts) | **true (post-think text only)** |
| everything else | pop16/k4/groups16, loops 1–4, temp 1.0/top_p .95/top_k 20, 32k, seed 1234, update=replace, uniform selection | identical |

Comparators: C (strip=false vfonly, `outputs/node1_lcb_feedback_se_vfonly_pilot/`) isolates the
strip effect under feedback; the strip=true plain-SE runs (`outputs/node1_se_loop5_32k_temp1_strip_
lcbv6_non_saturated/`, `outputs/node1_se_strip_lcbv6_fixedloop0/`) bracket the no-feedback side.
Context: prior strip comparisons were on plain SE only — strip × feedback interaction is untested;
strip=true means much shorter prompts (no 20k-token thinking traces), so cheaper/faster loops and
more in-context room for the feedback blocks.

Artifacts: config `configs/squeeze_evolve_feedback_vfonly_strip_node3.yaml`, launcher
`scripts/run_feedback_vfonly_strip_node3.sh`, output `outputs/node3_lcb_feedback_vfonly_strip/`
(+ checkpoints under `external/squeeze-evolve/outputs/...`). Grade post-hoc with the standard
`score_se_subset.py` (--max-tokens 32768 default OK).

## RESULTS (run DONE 21:42, canonical grading 2026-06-12 ~21:55; `RESULT-DEPENDENT`,
artifacts `outputs/node3_lcb_feedback_vfonly_strip/{genlog,per_problem,summary}.json[l]`)

**Run integrity:** loops 1–4 completed (~2h15m/loop), all 2,016 prompts/loop built with **0
fallbacks, 0 test-lookup misses**; loop-0 graded 813 correct (other passes of the same anchor:
812/814 — within the known ±1–2 TLE-flake band).

### Anchor-paired table (identical pinned loop-0 across all arms)

| arm | union (SE-all) | SE-final | children-correct loops 1–4 (of 8,064) | per-loop child density |
|---|---|---|---|---|
| A (plain, strip=false) | 90 | 80 | 3,661 (45.4%) | ~flat |
| A-strip (plain, strip=true, fixedloop0) | 91 | 82 | 3,742 (46.4%) | mild growth |
| C (vfonly, strip=false) | 92 | 82 | 3,989 (49.5%) | ~flat 49–51% |
| **C-strip (vfonly, strip=true — this run)** | **91** | **85** | **4,492 (55.7%)** | **GROWING 52.4 → 55.0 → 56.9 → 58.5%** |
| V (verifier machinery, C2 prompts, strip=false) | 90 | 90 | 3,126 obs. (42.5%) | declining |

### Headline findings
1. **C-strip is the best correct-trace generator of any arm to date: +503 traces (+12.6%) over C,
   +831 (+22.7%) over A** — and the only LCB arm whose child density GROWS monotonically across
   loops at constant width (the code analog of math-M5's growing density).
2. **Strip × feedback is superadditive on yield**: vs A, strip alone +81, feedback alone +328,
   both together **+831 > 409 (sum of parts)**. Mechanism plausibly: without 20k-token thinking
   traces, the 4 parent *solutions* and the feedback blocks dominate the prompt's salience.
3. **Reach attribution for lcbv6-004 resolved by the bracket**: A-strip ALSO solved 004 late
   (0/0/0/1/3 traces) → **strip=true is what unlocks 004; feedback amplifies it to full
   saturation** (C-strip trajectory **0 → 1 → 5 → 13 → 16/16**, 35 traces; vs C strip=false: 1
   marginal trace). lcbv6-120 was NOT solved here — it remains exclusive to C (feedback +
   strip=false), still the lone 0/80-BoN reach event. Union counts (90/91/91/92) sit in the ±1–2
   noise band; the per-trace trajectories above are the decisive statements.
4. **Erosion −6 (91→85), the mildest of any replace arm** (A −10, A-strip −9, C −10). V's elitism
   (−0) still owns the final-pop axis.
5. **Implied best data-generation config so far: strip=true + vfonly feedback**, optionally + V's
   elitist retention for final-pop preservation (the natural "V2" follow-up: C-strip prompts,
   uniform grouping, elitist-replace).
