# Feedback / Verification-Augmented SqueezeEvolve — Reconnaissance

**Read-only inspection only.** No files modified (except creating this report), no jobs run, no
vLLM, no model generation. Date 2026-06-10. Working dir `/mnt/cpfs/yangboxue/opsd/TTS/tts-sft`.
Every claim is `CODE-SUPPORTED` (from source/configs/outputs we read) unless marked otherwise.
Companion: `docs/SE_SFT_REPO_RECON.md` (SFT-pipeline recon); this doc focuses on the **feedback loop**.

---

## 1. Current repo state
- **Branch:** `main`
- **Latest commit:** `a3498b7b7d40927a1ccadf2d0cde67e59dedd0d1` — "add SFT presets and optional LLaMA-Factory backend" (2026-05-30).
- **git status:** tracked modified — `GPU_RUNBOOK.md`, `scripts/run_squeeze_evolve.py`, `src/tts_sft/answer_extraction.py`, `tests/test_answer_extraction.py`. Everything else (all SE configs, `data/filtered/`, all result dirs, new scripts, all `docs/*`) is **untracked** — i.e. the entire experiment campaign lives in the working tree, not committed.
- **Key files:**
  - SE wrapper: `scripts/run_squeeze_evolve.py` (modified).
  - SE→SFT: `scripts/convert_se_to_sft.py`; raw→SFT: `scripts/convert_raw_to_sft.py`; SFT trainer: `scripts/train_sft.py`; SFT formatting: `src/tts_sft/sft_formatting.py`.
  - Default SE config: `configs/squeeze_evolve_generation.yaml` (24 run-specific configs also exist).
  - Per-loop candidate flattener: `scripts/se_loop_candidates.py`; grouping: `scripts/group_se_loop_candidates.py`; scorer: `scripts/score_se_subset.py`; budget: `scripts/se_budget.py`.
  - Runbooks: `GPU_RUNBOOK.md`, `GPU_RUNBOOK_LLAMAFATORY.md`, `HANDOFF.md`, `README.md`, `claim-ledger.md`.
  - Results: `docs/NODE1_SE_NON_SATURATED_RESULTS.md`, `…_STRIP_RESULTS.md`, `docs/NODE2_BON_NON_SATURATED_RESULTS.md`, `docs/NODE1_LCBV6_CALIBRATION.md`, `docs/NODE34_HANDOFF.md`, `docs/NODE3/4_STATUS.md`, `docs/SE_SFT_REPO_RECON.md`.
  - SE engine (vendored, official, editable-installed): `external/squeeze-evolve/` (HEAD `ee5e6da` + 2 local patches — see §3/§8).
  - Result dirs: `outputs/node1_se_*` (15 SE runs), `outputs/node2_*` (BoN parallel/sequential + reachability + calibration). SE per-loop token metrics in `external/squeeze-evolve/outputs/<run>/metrics.json`.

---

## 2. Current SqueezeEvolve integration (`scripts/run_squeeze_evolve.py`)
Thin wrapper around the official `squeeze-evolve-client`. Flow:
1. Convert our seed JSONL → SE input (`_convert_seeds`, :87): per seed `{orig_prompt: question, question, gt: str(answer) | None}`. **For code (LCBV6) `answer` is absent → `gt=None`.**
2. Patch the YAML (`_patch_config`, :105): splice `--model/--base-url/--api-key` into every `models:` entry (+ `scoring_model` if present). Nothing else changed.
3. **Exact CLI invoked** (:338): `squeeze-evolve-client --config <patched.yaml> --input <converted.jsonl> --output <out>.raw.json [--n-problems N]`, run with `cwd=external/squeeze-evolve`, `PYTHONPATH=external/squeeze-evolve/src`.
4. Preserve per-loop checkpoints (`_preserve_loop_checkpoints`, :151): copy `<checkpoint_dir>/<run_name>_loop<t>.json` → `<output>.checkpoints/`.
5. Normalize raw JSON → our JSONL (`_normalize_orchestrator_output`, :198).

**Input schema → SE:** `{"orig_prompt": str, "question": str, "gt": str|null}` (one JSONL line/problem).

**Raw SE output schema** (`<out>.raw.json`, single JSON object) — verified on a real run:
`{"run_id": str, "metrics": [per-loop dict ×loops], "problems": [ {"orig_prompt","gt","candidates":[str…],"candidate_groups":[…],"routing_details":{…},"question","options"} … ] }`.
The raw JSON keeps only the **final-loop** population in `candidates` (≈`population`).

**Normalized JSONL (our wrapper output, 1 rec/problem)** (`_normalize_orchestrator_output`, :252):
`{"id","question","gt","final_response","candidates":[…],"source":"squeeze_evolve","model","metadata":{squeeze_evolve_run_id,n_candidates,run_name,checkpoint_dir,n_loop_checkpoints}}`.

- **`final_response` selection:** `candidates[0]` (:250) — *"With update:replace every final-population candidate is fully refined; index 0 is fine."* No scoring/ranking.
- **`candidates` storage:** the **final-loop population only** (the raw JSON's `problems[i].candidates`), as plain strings.
- **Multiple candidate-selection strategies?** The **wrapper** has none (always `candidates[0]`). The downstream `convert_se_to_sft.py` does: `--candidate-strategy {first,last,longest}` + `--candidate-index N` (`_extract_response`, :118). So selection strategy lives at SFT-conversion time, not in the wrapper.
- **`strip_think`:** set in the YAML (`routing.strip_think`). Default config = **false**; the formal runs used both false and true; node3/4 16k runs = false.
- **Where configured:** `configs/squeeze_evolve_generation.yaml` (default) + per-run configs; the wrapper never overrides it.

---

## 3. Current SE prompts / operators
Default config (`configs/squeeze_evolve_generation.yaml`) and all formal runs use:
- `routing.task: math` (LCBV6 runs use `task: code`)
- `routing.recombination: aime25-aggregate` (math) / `hmmt25-aggregate` / **`livecodebench-aggregate`** (code; a local plugin we added — see §8)
- `routing.evaluation: aime25-none` / `…-none` (i.e. **no in-loop evaluation**)
- `routing.fitness: diversity` (no scoring_model / prompt_logprobs)

**Where the prompt lives:** the operator is registered in `external/squeeze-evolve/benchmarks/aime25/register.py`:
```python
@recombination.register("aime25-aggregate")
def aime25_aggregate(query, candidates, **kwargs):
    return make_aggregate_prompt("math problem", "\\boxed{}")(query, candidates, **kwargs)
```
The template is built by `make_aggregate_prompt` in `external/squeeze-evolve/src/squeeze_evolve/common.py:128`. The **multi-candidate** branch (the one used, since k=4) produces verbatim:
```
You are given a {kind} and several candidate solutions. Some candidates may be incorrect or
contain errors. Aggregate the useful ideas and produce a single, high-quality solution. Reason
carefully; if candidates disagree, choose the correct path. If all are incorrect, then attempt a
different strategy. End with the final result in {answer_format}.

Problem:
{query}

Candidate solutions (may contain mistakes):
---- Solution 1 ----
{candidate_1}
---- Solution 2 ----
{candidate_2}
... (k candidates) ...
Now write a single improved solution. Provide clear reasoning and end with the final answer in {answer_format}.
```
For math `kind="math problem"`, `answer_format="\boxed{}"` → **the prompt explicitly asks for `\boxed{}`.** For code (`livecodebench-aggregate`) `kind="competitive programming problem"`, `answer_format="a single Python code block enclosed with ```"`, `is_code=True` (the code branch says "Return your final code in …").

**Critical for Feedback-SE:** the prompt embeds **candidate solutions ONLY** — each candidate is inserted verbatim (`(ans or '').strip()`, common.py:189). There is **no slot for per-candidate scores or feedback**. The current loop is **verifier-free / open-loop**: `fitness=diversity` + `evaluation=none` + `gt=None` (code) ⇒ no gold/test signal enters selection or recombination at any point. (`_evaluate` runs the evaluation operator only for *logging* metrics, and it's `…-none`.)

---

## 4. Completed BoN-vs-SE experiment settings
Constant across the formal arms: model `Qwen/Qwen3-4B-Thinking-2507`; temp 1.0, top_p 0.95, **top_k 20** (via extra_body/gen-config); verifier-free; grading offline. Subsets `data/filtered/{aime,hmmt,lcbv6}_non_saturated.jsonl` (18 / 21 / 126).

| arm | datasets | model gen | N / pop / groups / loops | strip | max_tok | solved | correct traces | total tok |
|---|---|---|---|---|---|---|---|---|
| **SE replace strip=F** | A/H/L | pop16,grp16,k4,loops5 (N_i=80) | replace | F | 32768 | 15 / 14 / 90 | 1006 / 657 / 4473 | 48.3M / 57.7M / 227.5M |
| **SE replace strip=T** | A/H/L | same | replace | T | 32768 | 15 / 16 / 85* | 1026 / 831 / 4398 | 33.4M / 41.1M / 140.1M |
| **BoN parallel** | A/H/L | N=80 | — | — | 32768 | 15 / 15 / 90 | 801 / 493 / 4070 | 38.9M / 47.5M / 147.2M |
| **BoN sequential** | A/H/L | N=16 | — | — | 163840 | 15 / 14 / 85 | 188 / 133 / 833 | 8.7M / 10.4M / 29.5M |
| **SE strip=T LCB, loop0-matched** | L | loops5 from F's loop0 | replace | T | 32768 | **91** | 4554 | ~140M |
| node3 SE 16k/loop10 | L | pop16,loops10 (N_i=160) | replace | F | 16384 | 86, final 71 | — | — |
| node4 SE 16k/loop10 | A/H | loops10 | replace | F | 16384 | 15 / 12 | — | — |

\* LCB strip=T "85" was loop-0 sampling variance; loop0-matched it is **91** (see `docs/NODE1_SE_NON_SATURATED_STRIP_RESULTS.md` + the loop0-matched ablation). co-solved density μ/80: AIME 53.4(BoN)/67.1(F)/68.4(T), HMMT 32.9/46.9/51.9, LCB 45.2/49.7/51.7.

**Files:** per-arm `outputs/node1_se_*_non_saturated/{se.jsonl,se.jsonl.raw.json,se.jsonl.checkpoints/,se.jsonl.loop_candidates.jsonl,genlog.jsonl,per_problem.jsonl,summary.json}`; BoN `outputs/node2_bon_{parallel,sequential}_*` (+ `node2_bon_lcbv6_graded/`); per-loop token metrics `external/squeeze-evolve/outputs/<run>/metrics.json`. Consolidated tables: `docs/NODE1_SE_NON_SATURATED_STRIP_RESULTS.md`, `docs/NODE2_BON_NON_SATURATED_RESULTS.md`. **Headline:** no reachability expansion vs BoN; SE's edge is *depth* (more correct traces), large on math, small on code; strip=true ≥ strip=false on both.

---

## 5. Evaluation / verifier code
**Math** (`src/tts_sft/answer_extraction.py`):
- `extract_boxed_answer` (:58), `extract_final_answer` (:72) — last `\boxed{}` (balanced) → "answer is/final answer" regex.
- `normalize_math_answer` (:103), `latex_canonical` (:154) + `_unwrap_boxed` (:143) — LaTeX-aware canonicalization (`\left/\right`, spacing, `\dfrac→\frac`, boxed).
- `is_exact_match` (:179) — normalized eq → numeric eq → latex-canonical eq. **No symbolic math_verify** (known undercount on radicals/fractions).
- `src/tts_sft/metrics.py:accuracy` (only metric); `scripts/eval_math.py` (greedy pass@1 eval); `scripts/score_se_subset.py` / `scripts/eval_reachability.py` (any-of-N solved + correct-trace counts).

**Code** (`scripts/lcb_exec_harness.py` + `scripts/eval_lcbv6_calibration.py`):
- `extract_code` — last ```` ```python ```` block.
- `lcb_exec_harness.py`: `run_stdin` (atcoder; feed stdin, line-wise compare) + `run_functional` (leetcode; parse newline-joined JSON args, `Solution().<fn>(*args)`, json-compare with float/list fallback), per-test SIGALRM timeout, run in a subprocess (isolation + overall timeout). Verdict JSON `{passed,error,n_passed,n_total,first_fail}`.
- `eval_lcbv6_calibration.py:grade_sample` orchestrates; `score_se_subset.py` grades SE candidates (math or code), emits per-gen log + per-loop/SE-all/SE-final + derived tokens.
- **Hidden (private) tests** are used for grading; `public_test_cases` exist in the dataset but are **not** currently used (relevant for §8/§9 — a non-leaking code verifier should use public tests).

---

## 6. Data formats (real examples; no fabricated model outputs)
- **Seed (math)** `data/seeds/aime25_seed_*.jsonl` / `data/filtered/aime_non_saturated.jsonl`: `{"id":"aime25-000001","question":"…","answer":"588"}`.
- **Seed (code)** `data/filtered/lcbv6_non_saturated.jsonl`: `{"id":"lcbv6-001","question_id","dataset":"LCBV6","platform","difficulty","contest_date","starter_code","testtype","fn_name","question":"<CODE_PROMPT>","problem","tests":"<json: inputs/outputs/testtype/fn_name/time_limit>"}` (no `answer`).
- **Raw SE output** `<out>.raw.json`: `{"run_id","metrics":[…],"problems":[{"orig_prompt","gt","candidates":[…],"candidate_groups","routing_details","question","options"}]}`.
- **Normalized SE** `se.jsonl`: `{"id","question","gt","final_response","candidates":[…],"source","model","metadata":{…}}`.
- **Per-loop candidates** `se.jsonl.loop_candidates.jsonl` (one row/candidate/loop): keys `id, question, answer, loop_index, candidate_id, group_id, parent_ids, parent_texts, model, prompt, full_response, thinking_trace, final_answer, fitness, score, routing_metadata, generation_params, loop_metrics, raw_candidate`. Real loop-1 row: `candidate_id="aime25-000001::loop1::cand0"`, `group_id=0`, `parent_ids=[14,1,0,15]`, `parent_texts=<list of 4 parent strings>`, `fitness=1.0`, `score=null`, `routing_metadata={"route":"model_0","thresholds":[],"percentiles":[]}`.
- **Converted SFT** (`build_sft_example`, `src/tts_sft/sft_formatting.py`): `{"id","messages":[{"role":"user","content":<math-prompt(question)>},{"role":"assistant","content":<response, incl. <think>>}],"source"}`. (No SFT data generated yet — `data/sft/` is empty.)
- **Eval output** `scripts/eval_math.py` per-example log: `{id, question, answer, prediction, correct}` (+ cumulative total/correct/accuracy). Eval seed example `data/eval/sample_eval.jsonl`: `{"id":"eval_000001","question":"…","answer":"42"}`.

---

## 7. Candidate-level information (can we attach feedback?)
| question | answer |
|---|---|
| Store every candidate? | **Yes** — every candidate of every loop is recoverable. The raw JSON keeps only the final population, but per-loop checkpoints (`<run>_loop<t>.json`) hold the full `ProblemState` (all candidates + groups + routing) for each loop; `se_loop_candidates.py` flattens them to one row/candidate. |
| Candidate IDs? | **Yes** — `candidate_id = "<pid>::loop<t>::cand<k>"` (k = within-checkpoint index; for accumulate the last `groups` are the new ones). |
| Intermediate loop candidates or only final? | **All loops** (loop 0…T), via checkpoints. The normalized `se.jsonl` alone is final-only. |
| Candidate groups? | **Yes** — `parent_ids` (indices into the prior loop) + `parent_texts` (the actual k parent strings) per loop-≥1 candidate; raw `candidate_groups` in checkpoints. |
| Routing details? | **Yes** — `routing_details` per problem (routes/thresholds/group members/candidate_confidences/group_fitnesses) + per-candidate `routing_metadata`. |
| Scores or only text? | `fitness` is stored (loop ≥1); `score` is **null** because all runs used `fitness=diversity` (no per-candidate confidence). Under `fitness=confidence` the score path would populate. So **text always; numeric score only if confidence fitness is on**. |
| Map feedback back to a candidate? | **Yes, post-hoc** — `candidate_id` + `parent_ids` + `group_id` uniquely place each candidate and its parents. **But** all of this is saved *after* the run; injecting feedback *into* the next loop requires an inline hook (see §8), not the saved files. |

---

## 8. Feasibility of Feedback-SE
Core constraint: the recombination operator signature is `fn(query, candidates, **operator_ctx)` where `candidates` is a **list of strings** and `operator_ctx = {task, temperature[, judge_model_cfg]}` (orchestrator.py `_operator_ctx`, :169). **It does NOT receive per-candidate scores/feedback, nor `gt`/tests.** The operator is a **synchronous prompt-builder** (no model calls inside `make_aggregate_prompt`). Two integration points exist: (i) a **custom recombination operator** (official `@recombination.register` extension), and (ii) the orchestrator's `_evolve_loop` (where scoring/selection happen and where feedback would have to be computed inline). SE *does* support an optional `judge_model` threaded into operator ctx, and `OpenAIBackend.judge_completion` (backend.py:353) is an async single-call judge path — but operators are called synchronously, so a judge call from inside an operator would need a sync bridge.

**A. Score-only Feedback-SE** (candidate → score → "candidate + score" in prompt)
- Source of score (non-leaking options): model **confidence** (SE's `fitness=confidence`, needs `prompt_logprobs>0`; works on **stock vLLM**, no fork) or self-consistency/agreement. Gold/test scores **leak** (math: reveals the answer; code: only safe with **public** tests, never the hidden eval tests).
- SE-native? **Partially.** Confidence scores are already computed in `_score_population`/`_evolve_loop` as `candidate_scores`, but they are **not passed to `_recomb`**. Minimal change: in `orchestrator._evolve_loop`, thread the per-candidate scores for each group into `_recomb`/the operator; add a **custom operator** `feedback-aggregate` that renders `---- Solution i (score=…) ----`.
- Modify: `external/squeeze-evolve/.../orchestrator.py:_recomb`/`_evolve_loop` (pass scores) + a new `benchmarks/feedback/register.py` operator + a config (`fitness: confidence`, `recombination: feedback-aggregate`, a model with `prompt_logprobs: 20`). Store: extend `se_loop_candidates`/checkpoints to keep the score already there (`candidate_confidences` exists in routing_details).

**B. Natural-language Feedback-SE** (candidate → critic feedback → "candidate + feedback" in prompt)
- Feedback source: a **critic LLM** (gold-free review) — works for math and code with no leakage; or for code, run **public tests** and turn pass/fail+error into NL feedback (non-leaking). The hidden-test executor (`lcb_exec_harness.py`) already produces structured verdicts → easy to convert to NL, but must be pointed at **public** tests for the in-loop critic.
- SE-native? **Needs an orchestrator pre-pass.** Because operators are sync prompt-builders, the cleanest design is: in `_evolve_loop`, before recombination, generate per-candidate feedback via a backend/critic call (async), attach it to the group, then a custom `feedback-aggregate` operator formats `---- Solution i ----\n…\n---- Critique i ----\n…`. Requires: orchestrator hook to compute+thread feedback (and, for a verifier critic, thread `gt`/tests — which the operator currently never sees), a custom operator, and a critic config.
- Custom recombination operator: **yes (required)** — `make_aggregate_prompt` has no feedback slot.

**C. Score + NL Feedback-SE** = A's score plumbing + B's feedback plumbing into one operator that renders candidate + score + critique. Same hooks as B plus the score field.

**Summary:** SE supports the *prompt* side cleanly (register a custom operator). It does **not** natively support feeding **per-candidate verdicts/feedback** or **gt/tests** into recombination — that requires a small `orchestrator._evolve_loop` change (compute feedback inline, thread it + gt into `_recomb`). Confidence-score-only (A) is the least invasive (scores already computed; just plumb them through). NL/verifier feedback (B/C) needs the inline feedback-generation pass.

---

## 9. Risks / open questions
- **Gold leakage (math):** any gold-answer verifier inside the loop reveals the target → recombination becomes "copy the candidate marked correct"; contaminates the very traces we'd self-distill. Math feedback must be **gold-free** (NL critic / confidence), not a gold verifier.
- **Eval leakage (code):** the grader uses **hidden/private** tests. An in-loop code verifier must use **public** tests only (`public_test_cases`, currently unused) — must confirm public ≠ private to avoid train-on-test.
- **No per-candidate feedback stored today:** we store text + fitness + (null) score; NL feedback isn't captured → must extend `loop_candidates`/checkpoints to log feedback for analysis.
- **Operator can't see gt/tests:** `operator_ctx` lacks `gt` → verifier/critic feedback needs an orchestrator change to thread it, or a separate pre-pass.
- **Token-cost explosion:** per-candidate feedback ≈ +1 model/critic call per candidate per loop → up to ~2× generation cost (loops5,pop16 ⇒ +80 critic calls/problem). For code, also subprocess test-execution cost per candidate per loop.
- **Candidate-selection ambiguity:** feedback on the whole population vs only the k selected per group; which candidates' feedback enters which recombination prompt.
- **Prompt schema mismatch:** `make_aggregate_prompt` is fixed (candidates-only) → must not edit it; add a parallel feedback operator.
- **Sync-operator limitation:** operators can't cleanly do async model calls → feedback must be precomputed in the orchestrator, not inside the operator.
- **Verifier reliability:** math exact-match undercounts (radicals/fractions); a math NL critic may be wrong (hallucinated "this is correct"); code public tests may be weak.

---

## 10. Recommended next implementation plan (propose only — do NOT implement yet)
**Goal:** test Feedback-SE on **5–10 toy math problems**, loops=2, smallest change, **gold-free**.
1. **Pick variant B (NL critic), gold-free**, single base model as its own critic — avoids leakage, avoids the fork, isolates "does feedback-conditioned recombination beat plain aggregation."
2. **Orchestrator hook (minimal):** in `external/squeeze-evolve/.../orchestrator.py:_evolve_loop`, after `select` and before building `tier_prompts`, add an optional feedback pass: for each group, call the (existing) backend with a fixed **critic prompt** per candidate ("review this solution for errors; do NOT reveal or assume the answer") → list of critiques aligned to the group. Gate behind a new `routing.feedback: none|critic` flag (default `none` ⇒ zero behavior change for all existing runs).
3. **Custom operator** `benchmarks/feedback/register.py` → `feedback-aggregate`: same body as `make_aggregate_prompt` multi-candidate branch but interleaving `---- Solution i ----` / `---- Critique i ----`. Receives the critiques via a new kwarg threaded from `_recomb`.
4. **Config** `configs/feedback_se_toy.yaml`: copy a loop2 math config, set `recombination: feedback-aggregate`, `feedback: critic`, `fitness: diversity` (keep), 5–10 problems, max_tokens modest.
5. **Logging:** extend `se_loop_candidates.py` to carry a `feedback` field (the critique that fed each candidate's recombination) so we can audit it.
6. **Eval:** reuse `score_se_subset.py` (math) to compare Feedback-SE vs plain SE (same loop-0, per the loop-0-matched methodology) on the toy set.
7. **Smoke** like the existing SE smokes (1–2 problems, dry-run command construction first), then 5–10.

Scope of change: ~1 small orchestrator hook (gated) + 1 new operator file + 1 config + 1 logging field. No change to the wrapper, the grader, or any existing config/run.

---

- **Ready to implement: NO** (recon only; needs the confirmations below before coding).
- **Minimal files to modify (when greenlit):**
  - `external/squeeze-evolve/src/squeeze_evolve/algorithm/orchestrator.py` (gated feedback pass in `_evolve_loop` + thread feedback/scores into `_recomb`)
  - `external/squeeze-evolve/benchmarks/feedback/register.py` (NEW custom `feedback-aggregate` operator)
  - `external/squeeze-evolve/src/squeeze_evolve/core/config.py` (NEW `routing.feedback` flag, default `none`)
  - `scripts/se_loop_candidates.py` (log a `feedback` field)
  - `configs/feedback_se_toy.yaml` (NEW)
  - (no change to `run_squeeze_evolve.py`, graders, or existing configs)
- **Exact unknowns needing Harman confirmation:**
  1. **Feedback type for round 1:** gold-free **NL critic** (recommended), **confidence score** (needs `fitness=confidence` + `prompt_logprobs`, stock vLLM ok), or a **real verifier** (math gold = leakage; code = public tests only)? 
  2. **Leakage policy:** is *any* gold/test signal allowed inside the loop, or must round 1 stay strictly gold-free (to keep self-distillation traces clean)? For code, confirm using **public** tests (not the hidden eval tests).
  3. **Critic model:** reuse the base `Qwen3-4B-Thinking` as its own critic, or a separate/stronger judge?
  4. **Feedback granularity:** critique all population candidates, or only the k selected per group?
  5. **Compute budget:** OK with ~2× generation cost (per-candidate critic calls)? token cap for critiques?
  6. **Patching the vendored SE clone** is acceptable (we already added `livecodebench` operator + the int() fix + the resume-continue patch) — confirm OK to add the gated feedback hook there.
