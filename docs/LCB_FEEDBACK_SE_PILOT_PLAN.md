# In-loop LCB Feedback-SE Multi-loop Pilot — PLAN ONLY (do not launch)

**Status: design for approval. No multi-loop generation has been run.** This plan wires the confirmed
winning recombination config (`R2c_old_visible_failed_only`, see
`docs/LCB_R2C_OLD_VISIBLE_FAILED_ONLY_CONFIRM.md`) into the actual SqueezeEvolve loop, to test whether the
single-step visible-failed gain (**+14/399, p≈0.004**) **compounds across loops** (loop0→…→5) vs the
untouched strip=false control. Hard gates: official SqueezeEvolve only; **notify Harman + confirm
hyperparameters before launch**; no SFT/RL; baseline loop/orchestrator defaults untouched (new operator is
additive); colleague tree read-only.

## Scope & safety (explicit)
- **Plan-only — nothing has been launched.** No multi-loop generation has been run; this document is for approval.
- **Public/sample tests are used ONLY to generate the visible feedback** shown in the recombination prompt.
- **Hidden tests are NEVER used in-loop.** They are used only for **final post-hoc grading** of the produced candidates.
- **Frozen feedback config:** `stay-close + CHECK-bearing V2-concise feedback only for visible-failed candidates + NO block on all_pass candidates` (+ top-level "feedback shown only for failed candidates; no-block ≠ correct" note).
- **V3, V4, and SFT are NOT included.**
- **The original baseline and the original `livecodebench-aggregate` operator remain untouched** — the feedback operator is a separate, additive registration selected only for arm C.

## Why in-loop (not just one-step)
The offline R2c probes only measure loop0→loop1. The research question is whether feedback lets the
*population* reach solutions plain SE/BoN does not **under matched compute**, accumulated over loops. That
can only show up in-loop, where loop-t feedback shapes loop-(t+1) parents. The pilot is the smallest run
that can detect compounding.

## First pilot: C-only (viability / compounding test)
**Decision (2026-06-11): the FIRST multi-loop pilot runs only `C_feedback_vfonly`.** This is **not** an
attribution-clean ablation — we already have the one-step paired confirmation of C's gain over R0_stayclose
(`docs/LCB_R2C_OLD_VISIBLE_FAILED_ONLY_CONFIRM.md`: +14/399 visible-failed, p≈0.004). The question here is
narrower: **does the frozen C config still work once wired into the actual multi-loop SE process, and does
the visible-failed gain compound across loops (loop0→…→5)?** A and B are **deferred** to a later
attribution-clean follow-up on the same pinned setup.

### Arms
- **`C_feedback_vfonly`** (THIS pilot) — stay-close + top-level failed-only note + **CHECK-bearing V2-concise feedback only for visible-failed candidates, no block for all_pass** (the frozen config).

### Deferred follow-up (documented for later — do NOT run now)
- **`A_original_strip_false`** — untouched original `livecodebench-aggregate` (no stay-close, no feedback).
- **`B_stayclose_only`** — stay-close prompt, no feedback. **Attribution control.**
- Rationale retained: A-vs-C alone **confounds stay-close with feedback** (stay-close was +4–5pp at loop1),
  so the clean attribution run must include B. Run A and B on the **same pinned loop-0** as this C pilot when
  we do the attribution study, so all three are paired.

**Framing:** this C-only run is a **viability/compounding pilot, not an attribution-clean ablation.** Any
comparison of this pilot to existing original-strip=false / stayclose-only outputs is **non-paired reference
only** unless subset + seeds + hyperparameters are actually matched (they are not for the old strip=false
full run) — such comparisons will be **labelled non-paired reference**.

## Proposed operator: `livecodebench-feedback-aggregate` (additive; original operator untouched)
A new recombination operator registered alongside `livecodebench-aggregate`. Selected only for arm C via
config (`recombination: livecodebench-feedback-aggregate`); arms A/B use the existing operators. Behaviour
per recombination call (one group of k parents):

1. **Inputs:** the problem text (`query`) + the k=4 parent candidate texts (full strip=false, verbatim) —
   exactly what the original operator receives. No change to grouping/selection/update.
2. **Public-test lookup (non-leaky):** a side table `problem_id → public_tests` loaded once at startup from
   `data/filtered/lcbv6_public_tests.jsonl` (keyed by the seed id / question text). **Hidden tests are never
   read by the operator.**
3. **Per-candidate visible execution:** `extract_code` each parent; run it against the **public/sample**
   tests via `scripts/lcb_public_probe_harness.py` (subprocess-isolated, per-test SIGALRM timeout). Get the
   category (`wrong_answer / runtime_error / compile_error / timeout / all_pass`) + first-fail detail.
4. **Feedback assembly (frozen vfonly format):**
   - visible-failed candidate → CHECK-bearing V2-concise block (`STATUS/OBSERVED/DETAIL/CHECK`), DETAIL =
     failing input/expected/actual (wrong_answer, truncated) or error message (compile/runtime) or none (timeout).
   - **all_pass candidate → NO feedback block** (candidate shown alone).
   - top-level once: the "feedback only for failed candidates; no-block ≠ correct" note + Harman stay-close paragraph.
   - prompt tail: "Return only one complete Python code block …".
5. **Return** the assembled prompt string (same contract as the original operator). The model generates the
   loop-(t+1) child exactly as today.

**Constraints baked in (per request):** public/sample execution only for feedback · hidden tests only for
final grading · no V3 · no V4 · no SFT · no all_pass block · same k=4 grouping as the original SE run · same
strip=false candidate text (arms A/B/C identical here) · update=replace (paper default, unchanged) ·
fitness=diversity (single-model, no vLLM fork).

**Determinism / clean pairing:** vLLM is nondeterministic at fixed seed, so loop-0 sampling varies. To pair
A/B/C per `(problem, group)` across loops, **pin loop-0**: generate loop-0 once and have all three arms
resume-continue from the identical loop-0 population (the resume-continue patch already used in the
loop-0-matched strip ablation). Then arms diverge only at recombination. This makes per-loop flip analysis valid.

## Metrics logged at EVERY loop (t = 0..L)
- **code-valid rate** (fraction of loop-t candidates with an extractable code block) — watch it stays ~100%.
- **density / correct traces** — per-loop count of candidates passing hidden grading (offline grader, hidden tests, post-hoc only).
- **reach** — per-loop any-of-N solved problems (the population frontier).
- **visible-failed vs visible-passed breakdown** — per loop, split candidates/groups by whether their parents had a visible public failure (the mechanism axis).
- **flip analysis** — where loop-0 is pinned, per-`(problem,group)` C-vs-B and B-vs-A wins/losses/ties at each loop.
- **token overhead** — prompt/completion tokens per arm per loop; C's extra = feedback blocks + public-exec wall-time.
- **final-population vs any-of-N** — replace-erosion check (prior runs showed final-pop < any-of-N under update=replace).

## Proposed scope (pilot, to bound cost)
- **Subset:** the same family as the confirmation — **~40 mixed-correctness `lcbv6_non_saturated` problems**
  (superset of the 30/70 already used), so loop0 has both correct and incorrect parents (where feedback can act).
- **Loops:** L = 5 (matches the formal strip=false run; enough to see compounding without the 16k/loop10 cost).
- **Arms:** A, B, C (keep B).
- **Pairing:** shared pinned loop-0 across arms.

## Exact proposed hyperparameters (to confirm with Harman)
| field | value |
|---|---|
| model | `Qwen/Qwen3-4B-Thinking-2507` (local vLLM, TP8 @ 262144) |
| subset | `data/filtered/lcbv6_non_saturated.jsonl`, ~40 mixed-correctness problems (pilot) |
| population | 16 candidates / problem / loop |
| k (group size) | 4 |
| groups | 16 recombinations / problem / loop |
| loops (L) | 5 |
| update | `replace` (paper default for LiveCodeBench) |
| fitness | `diversity` (single model, no vLLM fork) |
| strip_think | `false` (all arms; candidate text identical to baseline) |
| decoding | temperature 1.0, top_p 0.95, top_k 20, max_tokens 32768 |
| loop-0 | pinned/shared across A/B/C (resume-continue) for paired analysis |
| feedback (arm C only) | public/sample tests via `lcb_public_probe_harness.py`; vfonly format; no all_pass block |
| grading | hidden tests, offline, **post-hoc only** |
| arms | A_original_strip_false, B_stayclose_only, C_feedback_vfonly |

**Rough cost:** ≈ 40 problems × 16 groups × 5 loops × 3 arms ≈ **9,600 recombination calls** (+ loop-0
generation, shared). Recombination outputs are short; dominant cost is k=4 full-candidate prefill (as in the
confirm runs). Plus per-group public execution for arm C (cheap, CPU). Feasible on the 8×A100 box; ~comparable
to the confirmation runs scaled by loops. Exact wall-clock depends on the confirmed population/groups.

## Decision criteria (pre-registered)
- **Primary:** does C's per-loop **visible-failed** density gain over B **grow or hold across loops** (compounding), with **code-valid ≈100%**? If yes → feedback adds in-loop value beyond stay-close → candidate for a full run.
- **Attribution:** B−A isolates stay-close; C−B isolates feedback. Report both at every loop.
- **Null/negative:** if C−B washes out by loop 2–3 or code-valid drops, **do not** scale; the offline one-step gain did not compound.

---

## Message for Harman (approval before launch)

> **Re: LCB in-loop Feedback-SE pilot — requesting hyperparameter sign-off before generation.**
>
> Offline probes converged on a clean, deployable result: adding **deterministic public/sample-test
> execution feedback** to the SE recombination prompt — CHECK-bearing feedback **only on candidates that
> visibly failed public tests, and no block on candidates that passed** — improves loop0→loop1 LCB synthesis
> by **+14/399 on visible-failed groups (p≈0.004)**, overall **+11/560 (p≈0.04)**, with **code-valid 100%**
> and ~+0.4% tokens. It beats both the no-feedback stay-close arm and a shorter "refined" variant. Feedback
> uses public tests only; hidden tests are used only for post-hoc grading. No V3/V4, no SFT, official SE.
>
> I'd like to run a **small multi-loop pilot** (L=5) to see whether this gain **compounds across loops**,
> with three arms on a shared pinned loop-0: **A** untouched original aggregate, **B** stay-close no-feedback
> (attribution control), **C** stay-close + visible-failed-only feedback. Proposed config: Qwen3-4B-Thinking,
> ~40 mixed `lcbv6_non_saturated` problems, population 16 / k 4 / groups 16 / loops 5, update=replace,
> fitness=diversity, strip=false, temp 1.0 / top_p 0.95 / top_k 20 / max_tokens 32768 (full table in
> `docs/LCB_FEEDBACK_SE_PILOT_PLAN.md`). The new `livecodebench-feedback-aggregate` operator is additive —
> the original operator and loop defaults are untouched.
>
> **Please confirm (or adjust): population / k / groups / loops, the problem subset/size, and update=replace.**
> I won't start generation until you sign off.

---

## Implementation status (operator built + validated; pilot NOT launched)
- **Operator:** `external/squeeze-evolve/benchmarks/livecodebench/_feedback_aggregate.py`, registered as
  `livecodebench-feedback-aggregate` in that dir's `register.py` (**additive**; original
  `livecodebench-aggregate` untouched). Loop-0 (empty candidates) returns the query verbatim; loop≥1 runs
  each parent's extracted code against PUBLIC tests (cached + 4-way parallel), emits a CHECK-bearing
  V2-concise block for visible-failed parents, **no block for all_pass**, with the top-level failed-only
  note + stay-close. Fully guarded (any error → no-feedback stay-close fallback; the loop never breaks).
- **Validated:** (1) unit test — lookup hits, correct per-category blocks, all_pass omitted, loop-0 = query;
  (2) full SE smoke (`configs/squeeze_evolve_feedback_vfonly_smoke.yaml`, 2 problems × pop4 × loops2)
  completed cleanly with the operator firing in loop 1 and 2 checkpoints written.
- **Config:** `configs/squeeze_evolve_feedback_vfonly_pilot_node1.yaml` (clone of the formal LCBV6 config,
  only `recombination: livecodebench-feedback-aggregate` changed). **Seed:** `data/filtered/lcbv6_non_saturated_pilot40.jsonl` (40 mixed problems).
- **Loop-0:** this C-only pilot runs its **own fresh loop-0** (loop-0 *pinning* is for cross-arm pairing → deferred to the A/B/C attribution follow-up). Any comparison to the old strip=false run is **non-paired reference**.

### Exact launch command (AWAITING CONFIRMATION — do not run until approved)
```bash
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache PYTHONINTMAXSTRDIGITS=0
export LCB_FB_SEED=$PWD/data/filtered/lcbv6_non_saturated_pilot40.jsonl
export LCB_FB_PUBLIC=$PWD/data/filtered/lcbv6_public_tests.jsonl
export LCB_FB_HARNESS=$PWD/scripts/lcb_public_probe_harness.py
python scripts/run_squeeze_evolve.py \
  --input data/filtered/lcbv6_non_saturated_pilot40.jsonl \
  --output outputs/node1_lcb_feedback_se_vfonly_pilot/se.jsonl \
  --config configs/squeeze_evolve_feedback_vfonly_pilot_node1.yaml \
  --squeeze-evolve-dir external/squeeze-evolve \
  --n-problems 40
```
**Output directory:** `outputs/node1_lcb_feedback_se_vfonly_pilot/` (→ `se.jsonl`, `se.jsonl.raw.json`,
`se.jsonl.checkpoints/` per-loop, `metrics.json`). Post-hoc grading (`scripts/score_se_subset.py` +
`se_loop_candidates.py`) uses hidden tests OFFLINE only. **Rough ETA ~6–10 h** (40×16 groups × 5 loops at
max_tokens 32768; +cheap cached public-exec). Smoke leftovers are in `outputs/node1_lcb_feedback_se_vfonly_smoke/`.

---

## `data/filtered/lcbv6_public_tests.jsonl` — schema & contents (public/sample tests ONLY)

This file holds the **public/sample** tests used to generate visible feedback. **It contains NO hidden /
private tests.** It was built solely from the dataset's `public_test_cases` field
(`livecodebench/code_generation_lite @ refs/pr/6`); the hidden/private tests live separately in the seed
files' `tests` field and are **never** included here.

One JSON object per line, 131 records:
| field | meaning |
|---|---|
| `id` | LCBV6 problem id (`lcbv6-NNN`), aligned to the seed files |
| `question_id` | original dataset question id |
| `n_public` | number of public/sample tests (range **1–5**, median 3) |
| `public_tests` | JSON string `{inputs[], outputs[], testtype, fn_name, time_limit}` — the public/sample cases |

**Audit (confirming public-only):** max `n_public` across the file = **5** (vs ~40 hidden tests per problem
in the seed `tests`), so no record is the full hidden set; the file contains no `private`/`hidden` markers;
public inputs are a *separate* set from the hidden inputs (not copied). Public/sample tests are the examples
shown in the problem statements and are not secret.

**Artifacts referenced:** `scripts/probe_lcb_r2c_vfonly.py` (the validated prompt/feedback logic to port
into the operator), `scripts/lcb_public_probe_harness.py` (public executor), `data/filtered/lcbv6_public_tests.jsonl`
(public tests), `docs/LCB_R2C_OLD_VISIBLE_FAILED_ONLY_CONFIRM.md` (the result this is built on). Plan only —
nothing launched.
