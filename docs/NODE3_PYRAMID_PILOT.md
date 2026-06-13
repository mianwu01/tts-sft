# Node3 — Pyramid / Funnel Feedback-SE pilot (LCB, vfonly) — SMOKE PASSED; FULL RUN LAUNCHED

**Status: smoke PASSED (2026-06-11 ~06:05); full 126-problem run LAUNCHED same day on user
pre-approval ("no need to wait for my approval").** Node3 variant of the
LCB feedback-SE pilot testing **decreasing recombination width across loops** (Harman's
inverted-pyramid suggestion) against the conceptual alternative of Node1's constant width.
**Node1's in-flight constant-width pilot, its output directories, the original baseline operator, and
the hidden-test usage rules are untouched.** All Node3 artifacts live in separate
`*node3*pyramid*`-named directories.

## Main question
> Does the feedback_vfonly gain compound **more efficiently** under a decreasing-width funnel
> schedule (16→8→4→2 groups across loops) than under constant-width (16×4) `update=replace`?

"More efficiently" because the funnel uses **30 recombination calls/problem vs 64** (~47%): the
comparison is gain *per compute*, plus whether concentrating later loops on fewer, feedback-repaired
children avoids the replace-erosion seen in prior runs.

## 1. Is a per-loop `groups`/`population` schedule code-supported?

**No — wrapper-supported.** Evidence (`CODE-SUPPORTED`):
- `RoutingConfig.groups` is a single `Optional[int]` (`external/squeeze-evolve/src/squeeze_evolve/core/config.py:25`);
  `_evolve_loop` reads the constant `rc.groups` every loop (`orchestrator.py:336`). No schedule field exists.
- **But** the local resume-continue patch (`orchestrator.py:436-449`) loads the latest
  `<run>_loop<t>.json` checkpoint and continues from loop `t+1` up to `cfg.routing.loops`. So invoking
  the official client once per stage with `loops = t+1`, `groups = schedule[t]`, `resume: true` runs
  **exactly loop t** at that width, against the populations already in the checkpoints.
- With `update: replace` (`operators.py:154`) the post-loop population **equals that loop's `groups`**,
  so the schedule IS the population funnel: 16 → 16 → 8 → 4 → 2.
- Constraints found and enforced by the driver (`scripts/run_se_pyramid_stages.py`):
  - `selection.uniform` = `random.sample(range(pop), k)` **without replacement** (`operators.py:59`) →
    every loop must start from population ≥ k=4. The 16→8→4→2 schedule satisfies this (entering pops
    16, 16, 8, 4). A `…→1` tail from pop 2 would crash — that's why the smoke is **4→2**, not 4→2→1.
  - `load_latest_checkpoint` picks `sorted(files)[-1]` **lexicographically** (`utils.py:25-30`,
    `storage.py:87-93`) → total loops must stay ≤ 9 (single-digit loop indices). Ours is 5.
- **The feedback operator (`livecodebench-feedback-aggregate`) is selected purely by config + env and is
  byte-identical to Node1's — its semantics are NOT changed.** The driver only sequences stock client
  invocations and verifies checkpoints between stages.
- One deliberate deviation, documented: the orchestrator reseeds `random`/`np.random` at each `run()`
  start, so a staged run reseeds per stage. Reusing the same seed each stage would replay identical
  selection-index patterns across loops, so the driver sets `routing.seed = 1234 + loop_index` per
  stage (recorded in `pyramid_run_report.json`). Model-side sampling params are unchanged from Node1
  (temp 1.0 / top_p 0.95 / top_k 20 / max_tokens 32768; vLLM batching is nondeterministic regardless).

## 2. Frozen feedback config (identical to Node1's pilot)
- Loop-0 **REUSED verbatim** from the strip=false rerun #1 loop-0 checkpoint
  (`outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated`, read-only source) via
  `scripts/build_pinned_loop0.py` — **the same anchor Node1 pinned**; NO fresh loop-0 generation.
- CHECK-bearing V2-concise feedback **only** for visible public/sample-test failures; **NO block** for
  all_pass / visible-passed parents; top-level "no feedback block ≠ correct" note; stay-close prompt.
- Public/sample tests ONLY in-loop (`LCB_FB_PUBLIC=data/filtered/lcbv6_public_tests.jsonl`); hidden
  tests ONLY for final post-hoc grading (`score_se_subset.py`, offline). No V3/V4. No SFT.
- update=replace, fitness=diversity, strip_think=false, k=4, pop 16 (loop-0), Qwen3-4B-Thinking-2507
  on local vLLM TP8 @ max_model_len 262144 (this box's own server; Node1's box unaffected).

## 3. Exact schedule (full pilot — pending approval)

| loop | groups (recomb calls/problem) | population after loop |
|---|---|---|
| 0 | — (pinned, reused) | 16 |
| 1 | 16 | 16 |
| 2 | 8 | 8 |
| 3 | 4 | 4 |
| 4 | 2 | 2 |

30 recombination calls/problem total (Node1 constant-width: 64). All 126 non_saturated problems →
**3,780 recombination calls** (Node1: 8,064). Estimated wall ≈ roughly half of Node1's loops 1–4
(~8–12 h at the same serving setup), dominated by loop 1 (=Node1's loop-1 width).

## 4. Exact command (full pilot — DO NOT RUN until approved)
```bash
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
bash scripts/run_feedback_vfonly_pyramid_node3.sh   # logs: nohup/redirect of caller's choice
```
which internally: pins loop-0 for all 126 → writes `run_manifest.json` → runs
`scripts/run_se_pyramid_stages.py --schedule 16,8,4,2 --base-config
configs/squeeze_evolve_feedback_vfonly_pyramid_node3.yaml …` (one stock
`scripts/run_squeeze_evolve.py` invocation per stage) → builds `se.jsonl.loop_candidates.jsonl` →
runs `scripts/build_node3_pyramid_posthoc.py` (parent_groups / feedback_records / prompt samples /
validation). It removes/writes **only** `outputs/node3_lcb_feedback_se_vfonly_pyramid_pilot/` and
`external/squeeze-evolve/outputs/node3_lcb_feedback_se_vfonly_pyramid_pilot/`.

## 5. Output directories & artifacts
- **tts-sft side:** `outputs/node3_lcb_feedback_se_vfonly_pyramid_pilot/` —
  `run_manifest.json`, `pinned_subset.jsonl`, `loop0_population.jsonl`, `loop0_source_manifest.json`,
  `pyramid_run_report.json` (per-stage verification + audit-line spans),
  `stage_configs/stage_loop<t>.yaml`, `stage_raw/loop<t>.{raw.json,se.jsonl}`,
  `se.jsonl` + `se.jsonl.raw.json` (final), `se.jsonl.checkpoints/` (per-loop),
  `se.jsonl.loop_candidates.jsonl`, `feedback_operator_audit.jsonl` (live, 1 line/recomb call),
  `parent_groups.jsonl`, `feedback_records.jsonl`, `prompt_samples/`, `validation_summary.json`,
  and post-hoc grading records (`genlog/per_problem/summary` from `score_se_subset.py`).
- **engine side:** `external/squeeze-evolve/outputs/node3_lcb_feedback_se_vfonly_pyramid_pilot/{checkpoints,metrics.json}`.
- Smoke twin: same layout under `…_pyramid_smoke` dirs.

## 6. Comparison framing vs Node1 — same-loop0, NON-PAIRED funnel reference (pre-registered)

**Framing rule (fixed before results): Node3 is a *same pinned-loop0 anchor, non-paired
compute-efficiency reference* against Node1's constant-width run — NOT a strict paired comparison.**
After the shared pinned loop-0, selection RNG and vLLM sampling differ, so per-`(problem, group)`
pairing does not exist and **no paired significance (McNemar-style) will be claimed** against Node1.
All Node1 columns in the readout are labelled *non-paired reference*.

### Cumulative recombination calls per problem (the compute axis)

| after loop | Node1 constant-width (16/loop) | Node3 pyramid (16→8→4→2) |
|---|---|---|
| loop1 | 16 | 16 |
| loop2 | 32 | 24 |
| loop3 | 48 | 28 |
| loop4 | 64 | 30 |

### Key comparisons (compute-normalized)
1. **Node3 loop1 vs Node1 loop1** — same 16 calls/problem from the identical pinned loop-0
   population (width-matched start; non-paired in RNG).
2. **Node3 final (after loop4, 30 calls) vs Node1 after loop2 (32 calls)** — ≈ compute-matched:
   does the funnel's depth (4 loops) beat constant width's 2 loops at the same budget?
3. **Node3 final (30 calls) vs Node1 final (64 calls)** — quality-vs-cost tradeoff: how much of
   Node1's full-budget outcome does the funnel retain at ~47% of the recombination compute?

### Final readout — metrics to report (per loop t = 0..4, both runs where applicable)
- per-loop **reach / any-of-N** solved problems (cumulative any-loop too);
- per-loop **density / correct traces** (and correct traces *per recombination call*);
- **final-pop correctness** (the funnel's final pop is 2/problem vs Node1's 16 — report both raw and per-candidate rate);
- **final-pop vs any-of-N replace-erosion**;
- **code-valid rate** per loop;
- **visible-failed vs visible-passed split** (groups with ≥1 visible-failed parent vs none);
- **parent public-category distribution** per loop (wrong_answer / runtime_error / compile_error / timeout / all_pass / no_code);
- **feedback block count + all_pass omission count** per loop (from the audit);
- **fallback count** (must stay 0) and lookup-miss count (must stay 0);
- **token cost** (per-loop prompt/completion from engine metrics.json) and recombination calls;
- **qualitative examples:** (a) funnel preserves a strong repair (visible-failed parent → repaired
  child that survives narrowing into later loops); (b) funnel loses diversity / collapses too early
  (correct lineage present at loop t but absent from the narrowed loop t+1 population).

### Run-health watch items (monitored live)
checkpoint appearance per stage (driver-verified populations) · 0 operator fallbacks · 0 public-test
lookup misses · all_pass blocks omitted (audit + posthoc reconstruction cross-check) · hidden tests
used ONLY post-hoc (engine env has no hidden-test path; grading runs offline after completion).

## 7. SMOKE TEST (2 problems, schedule 4→2) — PASSED (2026-06-11 06:01–06:05)

Problems `lcbv6-037` + `lcbv6-039` (chosen for mixed public-test outcomes covering wrong_answer /
runtime_error / compile_error / all_pass). Schedule **4→2** rather than 4→2→1 because k=4 selection
from a 2-candidate population would crash `selection.uniform` (k is frozen at 4). Full results:
`outputs/node3_lcb_feedback_se_vfonly_pyramid_smoke/{validation_summary.json,summary.json}`.

| check | result |
|---|---|
| no fresh loop-0 generation | ✅ pinned loop-0 == #1 checkpoint subset byte-for-byte; engine metrics.json has loops **[1, 2] only** |
| feedback operator fires from loop 1 | ✅ 8 audit lines in loop 1 (then 4 in loop 2); 0 fallbacks, 0 lookup misses |
| all_pass blocks omitted | ✅ all 24 all_pass parents had NO block (incl. one all-all_pass group → 0 blocks) |
| visible-failed blocks inserted | ✅ all 24 failed parents (14 wrong_answer / 9 runtime_error / 1 compile_error) got CHECK-bearing blocks |
| checkpoints + metadata | ✅ loop0/1/2 checkpoints; all 8 required metadata files present |
| population funnel | ✅ 16 → 4 → 2 per problem (driver-verified per stage) |
| parent-group integrity | ✅ stored parent texts == loop t-1 candidates at recorded indices, 12/12 groups |
| audit ↔ deterministic reconstruction | ✅ 0 category mismatches, 0 block-count mismatches across all 12 groups |
| children sane | ✅ 12/12 code-valid; `</think>` structure identical to node1's formal run; cap-hit 0 |
| hidden-test grading (offline, post-hoc) | ✅ pipeline runs: loop0 5/32 correct cands, loop1 1/8, loop2 0/4 (tiny-n smoke — machinery check only) |
| wall clock | ~1 min/stage at 8-way concurrency |

## 8. Full-run launch record
- **Approval:** user message 2026-06-11: *"please directly start the formal experiment — on the full
  126 LCB problems, reusing the good loop-0 data just like Node1. No need to wait for my approval."*
- **Command:** `bash scripts/run_feedback_vfonly_pyramid_node3.sh > /tmp/node3_pyramid_pilot.log 2>&1 &`
- **Schedule:** loops 1–4 = 16/8/4/2 groups; 3,780 recombination calls total (126 problems).
- **Serving:** this box's own vLLM TP8 @ 262144 (`/tmp/node3_vllm.log`); Node1's box untouched.
- **Completed 2026-06-11 09:17** (launch 06:06; generation wall ≈ 3.1 h). All stages driver-verified;
  post-hoc `VALIDATION PASS` (loop-0 pin byte-identical, engine metrics loops [1,2,3,4] only,
  all_pass omitted, visible-failed inserted, 0 fallbacks, 0 lookup misses, parent-group integrity
  3,780/3,780, audit == reconstruction with 0 mismatches across 15,120 parent slots).

---

## 9. RESULTS (hidden-test grading, offline post-hoc; graded 2026-06-11)

**Node1 columns below are a NON-PAIRED reference** (same pinned loop-0 anchor; selection RNG and
sampling diverge after loop 0 — no paired significance is claimed; see §6). Node1 loops 0–2 were
graded node3-side from read-only checkpoint copies (`outputs/node3_ref_node1_grading/`, provenance in
its README) while Node1's run was still in flight; Node1 loops 3–4 are **pending** its completion.
Loop-0 sanity check: both runs grade the identical pinned population to **813/2016 correct, 90/126
solved** — same candidates, same grader, exact match.

### Node3 pyramid — per loop

| loop | groups | cum calls/prob | solved-in-loop (any-of-pop) | cum any-loop | correct cands | per-cand rate | code-extract | parents visible-failed | blocks / all_pass omitted |
|---|---|---|---|---|---|---|---|---|---|
| 0 (pinned) | — | 0 | 90/126 (any-of-16) | 90 | 813/2016 | 0.403 | 0.999 | — | — |
| 1 | 16 | 16 | 87/126 (any-of-16) | 90 | 1001/2016 | **0.497** | 1.000 | 27.1% | 2177 / 5878 |
| 2 | 8 | 24 | 79/126 (any-of-8) | 90 | 450/1008 | 0.446 | 0.948 | 20.8% | 838 / 3193 |
| 3 | 4 | 28 | 70/126 (any-of-4) | 90 | 249/504 | 0.494 | 0.994 | 26.7% | 538 / 1477 |
| 4 | 2 | 30 | **66/126 (any-of-2)** | **90** | 125/252 | 0.496 | 0.988 | 19.4% | 196 / 812 |

Tokens (engine metrics, loops 1–4): prompt 131.7M + completion 8.2M ≈ **139.9M**; wall 6788/2542/937/457 s.
Loop-1 prompt cost dominates (115M — k=4 full 32k strip=false loop-0 parents); later funnel loops are cheap.

### Node1 constant-width — non-paired reference (loops 0–2 graded; 3–4 pending)

| loop | groups | cum calls/prob | solved-in-loop (any-of-16) | cum any-loop | correct cands | per-cand rate | code-extract |
|---|---|---|---|---|---|---|---|
| 0 (same pin) | — | 0 | 90/126 | 90 | 813/2016 | 0.403 | 0.999 |
| 1 | 16 | 16 | 86/126 | 91 | 999/2016 | 0.496 | 1.000 |
| 2 | 16 | 32 | 85/126 | 91 | 936/2016 | 0.464 | 0.958 |
| 3 | 16 | 48 | 85/126 | 92 | 1026/2016 | 0.509 | 0.991 |
| 4 | 16 | 64 | 82/126 | **92** | 1036/2016 | **0.514** | 0.972 |

Node1 tokens loops 1–2: ≈137.6M; loops 1–4 total: prompt 179.5M + completion 19.6M ≈ **199.1M**.
Node1 final-pop (loop4, any-of-16) = 82/126; cumulative any-loop 92; erosion 92→82 = **−10**
(matches the formal non-feedback run's −10 at pop 16). Node1 loops 1–4 traces/call:
3,997/8,064 = **0.496**.

### The three key comparisons (compute-normalized)

1. **Loop1 vs loop1 @16 calls (width-matched start):** node3 1001/2016 correct (0.497), 87 solved;
   node1 999/2016 (0.496), 86 solved. **Tied** — an excellent cross-box/RNG sanity check: identical
   anchor + identical stage width → statistically indistinguishable outcomes. The vfonly feedback
   density gain over the pinned loop-0 (0.403 → ~0.50, ≈ +23% relative) replicates on both boxes.
2. **Node3 full funnel (30 calls/prob, 4 feedback rounds) vs Node1 through loop2 (32 calls/prob, 2
   rounds) — ≈compute-matched:** correct traces per recombination call **0.483 vs 0.480** (1,825/3,780
   vs 1,935/4,032) and total tokens **139.9M vs 137.6M** — a wash on trace-yield efficiency. Cumulative
   reach 90 vs 91. BUT the live-population state differs sharply: node3 ends holding **2** candidates/
   problem (any-of-2 = 66/126) while node1 holds **16** (any-of-16 = 85/126). At matched compute, the
   funnel's extra depth buys no extra correct-trace yield and costs −19 live-pop solved problems.
3. **Node3 final (30 calls) vs Node1 final (64 calls) — quality vs cost:** node1's full budget buys
   proportionally more traces (3,997 vs 1,825 correct ≈ 2.19× for 2.13× the calls; per-call 0.496 vs
   0.483) at 199.1M vs 139.9M tokens (funnel = **70% of token cost**, not 47%, because the loop-1
   prompt bill dominates both runs). Coverage: node1 final-pop **82/126 any-of-16** vs node3 **66/126
   any-of-2**; cumulative reach **92 vs 90**; erosion **−10 vs −24**. Notably, constant width shows
   *mild late-loop density compounding* (per-cand 0.496 → 0.464 → 0.509 → **0.514**) that the funnel
   cannot express with its 2-candidate tail. So the full constant-width budget dominates on every
   coverage metric; the funnel's advantage is purely cost (53% fewer calls, 30% fewer tokens, ~3× less
   wall-clock) at a near-equal per-call yield.

### Other pre-registered metrics
- **Reach:** cumulative any-loop **flat at 90/126** for node3 (no problem outside the loop-0 solved
  set was ever reached); node1 reached **+1** (91) at its loop 1. Consistent with the project-wide
  finding: feedback/evolution buys density, not reach.
- **Final-pop correctness:** 125/252 = 49.6% per-candidate — the funnel's final 2-candidate population
  is as *clean* per candidate as any loop, and strictly cleaner than loop-0 (40.3%).
- **Replace-erosion (final-pop vs any-loop):** 90 → 66 = **−24** at pop 2 (vs −10 at pop 16 in the
  formal non-feedback strip=false run). Narrowing amplifies erosion mechanically: any-of-2 vs any-of-16.
- **Visible-failed vs visible-passed groups (child correct):** loop1–4: 25.1/13.1/30.0/16.7% (vf) vs
  73.1/62.1/68.5/64.4% (vp). This split conditions on problem difficulty (vf parents ≡ harder
  problems), so it is a mechanism descriptor, **not** a treatment effect.
- **Parent category trend (public tests):** wrong_answer share falls monotonically 21.9% → 18.8% →
  16.8% → ~17% but `no_code`/compile spikes at loop-3 parents (5.1% no_code = truncated loop-2
  children) — the same truncation dip appears in node1's loop-2 children (extract 0.958), so it is
  feedback/recombination-generic, not funnel-specific.
- **Run health:** 0 fallbacks, 0 lookup misses across all 3,780 calls; hidden tests post-hoc only.

### Qualitative examples
- **Funnel preserves a strong repair:** `lcbv6-102` — loop-0 had **1/16** correct; the lineage survived
  every narrowing (1/16 → 1/8 → 4/4 → 1/2): a weakly-solved problem whose repaired solution ends as
  50% of the final population. Similar: `lcbv6-040` (2/16 → 2/2 = 100% final pop), `lcbv6-109` (2/16 → 2/2).
- **Funnel loses diversity / collapses:** **24 problems** had a correct candidate at some loop but
  **none** in the final pop-2. Worst case `lcbv6-053`: 13/16 correct at loop 0 and 14/16 at loop 1,
  then 3/8 → 1/4 → **0/2** — replace+narrowing walked a nearly-solved problem out of the population.
  Also `lcbv6-127` (6/16 → 6/16 → 0/8 — already gone by loop 2), `lcbv6-037`, `lcbv6-101`.

### Bottom line (this pilot, non-paired)
The funnel matches constant width on **per-call and per-token correct-trace efficiency** at the
compute-matched point (comparison 2) and finishes in ~3.1 h of generation (vs Node1's projected
16–25 h full run), but it **does not compound** the vfonly gain beyond loop 1 (per-candidate rate
plateaus at ~0.45–0.50) and it **pays in coverage**: −24 final-pop erosion and zero reach expansion.
If the SFT-data goal is a *small, clean* final set, the funnel delivers ~50%-precision pairs at half
the recombination budget; if the goal is *coverage of solved problems* (any-of-N traces for
distillation), constant width retains far more — and at full budget (comparison 3) constant width
additionally shows mild late-loop density compounding (→0.514) that the funnel's narrow tail cannot
express. **Verdict on the main question: the vfonly gain does NOT compound more efficiently under
the funnel** — per-call yield is the same, and the funnel sacrifices coverage, reach (+0 vs +2), and
the late-loop density climb. Its only win is cost/wall-clock.
