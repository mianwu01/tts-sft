# SE-SFT Repository Reconnaissance

**Purpose.** Repository reconnaissance for the **second** parallel experiment:
SqueezeEvolve data generation → SFT → held-out evaluation. This is **inspection/prep only**.

**Nothing was generated, trained, or evaluated to produce this document.** No SqueezeEvolve
run, no vLLM/API call, no SFT/RL, no eval. No existing experiment output was modified. The
Node1/Node2 reachability runs were not touched. (`CODE-SUPPORTED` throughout — every claim is
backed by source/docs we read; no `RESULT-DEPENDENT` numbers are asserted.)

Date: 2026-06-09. Working dir: `/mnt/cpfs/yangboxue/opsd/TTS/tts-sft`.

---

## 0. TL;DR

- **An end-to-end SFT pipeline already exists** (convert → train → merge → eval), in **two
  interchangeable backends**: in-repo TRL/PEFT (`scripts/train_sft.py`) and LLaMA-Factory
  (`configs/llamafactory/*`). Both consume the *same* `{id, messages[], source}` chat JSONL.
- **An evaluation pipeline already exists**: math exact-match pass@1 (`scripts/eval_math.py`),
  any-of-N reachability (`scripts/eval_reachability.py`), and LCBV6 code execution
  (`gen_lcbv6_calibration.py` + `lcb_exec_harness.py` + `eval_lcbv6_calibration.py`).
- **The blocking gap is TRAINING DATA, not code.** The repo contains **no dedicated training
  pool**. The only seed sets are (a) `math500_seed.jsonl` (500, MATH-500 — itself a public
  benchmark) and (b) the AIME25/HMMT25/LCBV6 seeds — **which are the held-out eval problems**.
  Using (b) as SE-generation seeds would be **direct train/test leakage**.
- **Safest next action:** decide and stage a *separate, non-overlapping* training seed pool
  (OpenThoughts / NuminaMath / MATH train — none present locally), then run a tiny 20–50 problem
  **smoke** of the full chain on that pool. **Do not** start full generation/training until
  Harman confirms (i) the training-data source and (ii) SE hyperparameters.

---

## 1. Repository map (relevant to SE-SFT)

### Data
| Path | Role |
|---|---|
| `data/seeds/*.jsonl` | Generation **seeds** (`{id, question, answer?}`). See §2. |
| `data/filtered/*.jsonl` | **HELD-OUT EVAL** subsets (AIME/HMMT/LCBV6, calibration-bucketed). See §6. |
| `data/eval/sample_eval.jsonl` | 8 toy problems (smoke eval / CI). |
| `data/generated/.gitkeep` | **Empty.** Destination for raw/SE generations. |
| `data/sft/.gitkeep` | **Empty.** Destination for chat-format SFT JSONL. |
| `data/results/.gitkeep` | **Empty.** Destination for eval logs. |

### Scripts (by stage)
| Stage | Script |
|---|---|
| Seed prep | `scripts/prepare_math_seed.py` (normalize arbitrary JSON→`{id,question,answer}`), `scripts/prepare_lcbv6_seed.py` (HF LCBV6→seed+tests) |
| SE generation | `scripts/run_squeeze_evolve.py` (wrapper around official client) |
| SE loop flattening | `scripts/se_loop_candidates.py` (checkpoints→per-candidate rows), `scripts/group_se_loop_candidates.py` (regroup per-problem) |
| SE budget | `scripts/se_budget.py` (recover total rollouts from raw.json metrics) |
| SE offline scoring | `scripts/score_se_subset.py` (grade per-loop candidates, math+code) |
| Raw generation | `scripts/run_raw_generation.py` (1/seed), `scripts/run_independent_rollouts{,_dp}.py` (N/seed) |
| **SFT data build** | `scripts/convert_se_to_sft.py`, `scripts/convert_raw_to_sft.py`, `scripts/export_llamafactory_data.py` |
| **SFT training** | `scripts/train_sft.py` (TRL/PEFT) **or** `llamafactory-cli train` (LLaMA-Factory) |
| **Checkpoint merge** | `scripts/merge_lora.py` |
| **Eval (math)** | `scripts/eval_math.py` (pass@1 exact-match) |
| **Eval (reachability/pass@k)** | `scripts/eval_reachability.py` (any-of-N) |
| **Eval (code/LCBV6)** | `scripts/gen_lcbv6_calibration.py` + `scripts/lcb_exec_harness.py` + `scripts/eval_lcbv6_calibration.py` |

### Library (`src/tts_sft/`)
`answer_extraction.py` (boxed/answer extraction + `is_exact_match`), `metrics.py` (`accuracy()`
only — no pass@k helper), `sft_formatting.py` (`build_sft_example`, chat-template), `prompts.py`
(`DEFAULT_MATH_PROMPT`), `openai_client.py` (vLLM/OpenAI chat), `model_loading.py`.

### Configs
- SE: `configs/squeeze_evolve_generation.yaml` (template) + many run-specific
  `configs/squeeze_evolve_*.yaml`.
- SFT (TRL): `sft_qwen3_4b_lora_smoke.yaml`, `..._quick.yaml`, `..._paper_aligned.yaml`,
  `sft_raw_lora.yaml`, `sft_squeeze_lora.yaml`, `model_qwen3_4b_thinking.yaml`.
- SFT (LLaMA-Factory): `configs/llamafactory/{qwen3_4b_raw_sft_lora,qwen3_4b_se_sft_lora,
  qwen3_4b_sft_smoke}.yaml` + `dataset_info_example.json`.
- Eval: `configs/eval.yaml`.

### Docs / runbooks
`GPU_RUNBOOK.md` (TRL backend, full Step 1–9 pipeline), `GPU_RUNBOOK_LLAMAFATORY.md`
(LLaMA-Factory backend), plus `docs/NODE*` status/results (the *first* experiment).

---

## 2. Available training-data sources

> **Schema across math seeds:** `{"id": str, "question": str, "answer": str}` (gold present
> except toy/smoke files). LCBV6 seed carries the code prompt + a hidden `tests` JSON.

| File | N | Gold | Source / benchmark | Train-suitable? | Leakage vs held-out eval? |
|---|---|---|---|---|---|
| `data/seeds/math500_seed.jsonl` | 500 | ✅ | **MATH-500** (Hendrycks MATH test-500 subset) | Usable, but small + itself a public benchmark | No overlap with AIME/HMMT/LCBV6 ✅ — but MATH-500 is conventionally an *eval* set; using it as train is methodologically weak |
| `data/seeds/aime25_seed.jsonl` | 30 | ✅ | AIME 2025 | ❌ **DO NOT TRAIN** | **= `data/filtered/aime_full.jsonl` (held-out eval)** |
| `data/seeds/hmmt25_seed.jsonl` | 30 | ✅ | HMMT Feb 2025 | ❌ **DO NOT TRAIN** | **= `data/filtered/hmmt_full.jsonl` (held-out eval)** |
| `data/seeds/lcbv6_seed.jsonl` | 131 | ✅ (hidden tests) | LiveCodeBench v6 (HF `code_generation_lite` refs/pr/6) | ❌ **DO NOT TRAIN** | **= `data/filtered/lcbv6_full.jsonl` (held-out eval)** |
| `data/seeds/sample_math_seed.jsonl` | 8 | ❌ | Toy | smoke only | n/a |
| `data/seeds/math500_seed_smoke.jsonl` | 5 | ❌ | MATH-500 subset | smoke only | no |
| all other `data/seeds/*` (hard11, reachability*, *pilot5, *hardtail7, *rest25, budget_check) | ≤30 | ✅ | **Subsets of AIME25/HMMT25** | ❌ **DO NOT TRAIN** | derived from held-out eval |

**Bundled raw datasets** (read-only, in the SE clone): `external/squeeze-evolve/data/{aime25,
hmmt25,gpqa_diamond}/test.parquet`. AIME/HMMT here are the *sources* of the held-out seeds →
**also off-limits as training data**. GPQA is unused by this project.

**No training pool exists locally.** No NuminaMath / OpenThoughts / MATH-train / OlympiadBench
present. `docs/NODE2_STATUS.md:206` already records the intended boundary: *"training data should
come from OpenThoughts-style unlabeled seed questions, with AIME/HMMT held out strictly for
evaluation."* A suitable pool must be **fetched/prepared** (requires Harman's go-ahead; nothing
downloaded here).

---

## 3. SqueezeEvolve generation machinery

**Wrapper:** `scripts/run_squeeze_evolve.py`. Invokes the official `squeeze-evolve-client`
(installed from `external/squeeze-evolve/`, entrypoint `src/squeeze_evolve/api/cli.py:client()`)
with `cwd=external/squeeze-evolve`.

**Required input schema** (`run_squeeze_evolve.py:87-102`): seed JSONL with `question` (REQUIRED,
non-empty), `id` (recommended), `answer` (optional). Internally converted to the orchestrator's
`{orig_prompt, gt, question}`.

**Outputs** (per run):
- **Normalized JSONL** (`run_squeeze_evolve.py:197-271`): one record/problem —
  `{id, question, gt, final_response (=candidates[0]), candidates[<final pop>], source,
  model, metadata{run_id, n_candidates, run_name, checkpoint_dir, n_loop_checkpoints}}`.
  ⚠️ This file holds **only the final loop's** population.
- **`<out>.raw.json`** (`:321`): full orchestrator object — `metrics[]` (per-loop
  `model_*_count`, `lite_count`, `*_input_tokens`, `*_output_tokens`), and `problems[]`
  (final `candidates`, `candidate_groups`, `routing_details`). `update: replace` ⇒ only final
  loop retained here.
- **`<out>.checkpoints/<run_name>_loop<t>.json`** (`:151-195`): full `ProblemState` snapshot per
  loop — the **only** source of per-loop history.

**Per-loop candidate flattening:** `scripts/se_loop_candidates.py:131-204` reads checkpoints and
emits **one row per candidate per loop**, preserving exactly what SFT needs:
`full_response` (verbatim), `thinking_trace` (extracted `<think>` block when `strip_think=false`),
`final_answer` (extracted), `loop_index`, `candidate_id`, `group_id`, `parent_ids`,
`parent_texts`, `fitness`, `routing_metadata`, `loop_metrics` (tokens). ⇒ Full reasoning trace
**and** a per-candidate correctness signal are available for filtering.

**Budget recovery:** `scripts/se_budget.py:57-81` sums `model_*_count + lite_count` over all
loops in `raw.json["metrics"]` → `estimated_total_generations` per problem (honest: never
fabricated from final pop size).

**Offline scoring:** `scripts/score_se_subset.py` grades per-loop candidates (math exact-match /
code execution), emitting per-generation, per-problem, and per-loop-token summaries.

**Config keys** (from `squeeze_evolve_generation.yaml` and the loop5/loop10 run configs):
`run_name`; `routing.{k, population, groups, loops, fitness=diversity, selection=uniform,
selection_temperature, update=replace, lite_fraction=0, recombination, evaluation, task=math,
generation_batch_size, strip_think, seed}`; `models[0].{name, base_url, api_key, endpoint=chat,
max_tokens, temperature, top_p, max_concurrency, extra_body.top_k}`; `retry`, `resume`,
`checkpoint_dir`, `metrics_path`. `fitness: diversity` avoids needing logprobs/scoring-model on
stock vLLM. `strip_think: false` ⇒ `<think>` preserved in `full_response` + extracted to
`thinking_trace`; `true` ⇒ stripped and `thinking_trace` null.

**Run-on-a-train-seed command template** (do NOT run yet — see §C):
```bash
python scripts/run_squeeze_evolve.py \
  --input  <TRAIN_SEED>.jsonl \
  --output outputs/sft_datagen/<run>/se.jsonl \
  --config <SE_CONFIG>.yaml \
  --squeeze-evolve-dir external/squeeze-evolve \
  --model "Qwen/Qwen3-4B-Thinking-2507" \
  --base-url "http://localhost:8000/v1" --api-key "EMPTY"
# optional per-loop history for richer SFT-target selection:
python scripts/se_loop_candidates.py \
  --checkpoint-dir outputs/sft_datagen/<run>/se.jsonl.checkpoints \
  --se-output      outputs/sft_datagen/<run>/se.jsonl \
  --config <SE_CONFIG>.yaml \
  --output         outputs/sft_datagen/<run>/se.jsonl.loop_candidates.jsonl
```

---

## 4. SFT / training pipeline (EXISTS, end-to-end)

**SFT-data construction:**
- `scripts/convert_se_to_sft.py` — SE normalized JSONL (or raw orchestrator JSON) →
  `{id, messages:[{user},{assistant}], source}`. Candidate selection via
  `--candidate-strategy {first|last|longest}` or `--candidate-index N` (default `first` =
  `candidates[0]`). Response-key fallbacks incl. `final_response`. **No correctness filter built
  in** (see §D gap). `<think>` kept verbatim. Skips empty/short (`--min-response-chars`).
- `scripts/convert_raw_to_sft.py` — raw `{id,question,response}` → same chat schema.
- Both delegate to `src/tts_sft/sft_formatting.py:build_sft_example`; user message built from
  `DEFAULT_MATH_PROMPT` (`src/tts_sft/prompts.py`); assistant turn verbatim.
- `scripts/export_llamafactory_data.py` — chat JSONL → ShareGPT JSON array
  (`conversations:[{from:human},{from:gpt}]`) for LLaMA-Factory; requires exactly 1 user + 1
  assistant turn.

**Training — two backends, identical input, same hyperparameters ("iron rule": Raw-SFT vs
SE-SFT differ only in `train_file`/`dataset` + `output_dir`):**
- **TRL/PEFT** `scripts/train_sft.py` — `trl.SFTTrainer` + optional `peft.LoraConfig`. Required:
  `--model-name-or-path`, `--train-file`, `--output-dir`. Defaults: LoRA r=16/α=32, lr 5e-6,
  bf16, max_seq 8192, per-device bs 1, grad-accum 16, cosine, gradient-checkpointing. Loads with
  `trust_remote_code=True` (Qwen3 ✅, `<think>` preserved via tokenizer chat template). Presets:
  `_smoke` (eff. batch 8, `--max-steps 20`), `_quick` (eff. batch 64, lr 2e-5, r=32/α=64),
  `_paper_aligned` (full-FT option, max_seq 32768, max_steps 4000 — needs FSDP/ZeRO-3).
- **LLaMA-Factory** `configs/llamafactory/*` — `template: qwen3`, `finetuning_type: lora`,
  `lora_target: all`, datasets registered via `dataset_info_example.json`. Run with
  `llamafactory-cli train <cfg>`.

**Merge:** `scripts/merge_lora.py --base-model … --adapter-path … --output-dir …`
(`merge_and_unload`) → vanilla weights for vLLM serving.

Both `GPU_RUNBOOK.md` and `GPU_RUNBOOK_LLAMAFATORY.md` give verbatim Step-by-step command
templates incl. 8-GPU `accelerate launch … --gradient-accumulation-steps 8`.

**Qwen3 + thinking traces:** supported and preserved end-to-end (no stripping anywhere in the
SFT path). Can train directly from generated SE/raw JSONL (identical `messages` schema).

---

## 5. Evaluation pipeline (EXISTS)

| Eval | Script | Metric | pass@1 | pass@k | Token log |
|---|---|---|---|---|---|
| Math (AIME/HMMT/MATH) | `scripts/eval_math.py` | exact-match accuracy | ✅ (temp 0) | ❌ | ❌ |
| Reachability / any-of-N | `scripts/eval_reachability.py` | both/only-SE/only-ind/neither + any-of-N rate | ✅ | ✅ | ❌ |
| Code (LCBV6) | `gen_lcbv6_calibration.py` → `eval_lcbv6_calibration.py` (via `lcb_exec_harness.py`) | tests-pass rate, buckets | ✅ | ✅ (`correct/n_samples`) | ✅ |

- **`eval_math.py`** evaluates an SFT checkpoint via **either** local HF + `--adapter-path`
  **or** `--use-vllm-server --base-url` (serve merged model). Exact-match through
  `answer_extraction.is_exact_match` (string-norm → numeric → LaTeX-canonical; **no symbolic
  equivalence**). pass@1 only; for pass@k use the rollouts→reachability path.
- **LCBV6 executor can grade arbitrary SFT outputs**: extracts the last Python block from each
  generated sample and runs it against the hidden `tests` (stdin or functional mode), in an
  isolated subprocess with a time limit. Needs the `tests` from `data/seeds/lcbv6_seed.jsonl`.
- `metrics.py` exposes only `accuracy()`; pass@k is computed ad-hoc inside `eval_reachability.py`.

**Eval command templates (held-out only):**
```bash
# Math pass@1 (LoRA adapter)
python scripts/eval_math.py --eval-file data/filtered/aime_non_saturated.jsonl \
  --model-name-or-path Qwen/Qwen3-4B-Thinking-2507 --adapter-path <CKPT> \
  --output data/results/se_sft_aime.jsonl --temperature 0.0 --max-tokens 8192
# (repeat for data/filtered/hmmt_non_saturated.jsonl)

# Code (LCBV6) pass@1
python scripts/gen_lcbv6_calibration.py --input data/filtered/lcbv6_non_saturated.jsonl \
  --output data/results/se_sft_lcbv6_N1.jsonl --model <served-name> \
  --base-urls http://localhost:8000/v1 --n-samples 1 --temperature 0.0 --max-tokens 32768
python scripts/eval_lcbv6_calibration.py --gen data/results/se_sft_lcbv6_N1.jsonl \
  --seed data/seeds/lcbv6_seed.jsonl \
  --gen-log data/results/se_sft_lcbv6_genlog.jsonl \
  --per-problem data/results/se_sft_lcbv6_perproblem.jsonl \
  --summary-json data/results/se_sft_lcbv6_summary.json
```

---

## 6. Leakage risks — held-out eval files

**Every file in `data/filtered/` is HELD-OUT EVAL. Never train on these or on the seeds they
derive from.**

| Benchmark | full | non_saturated | informative | hard_zero_clean | nonsat_extra |
|---|---|---|---|---|---|
| AIME (=aime25 seeds) | 30 | 18 | 15 | 0 | 3 |
| HMMT (=hmmt25 seeds) | 30 | 21 | 12 | 3 | 9 |
| LCBV6 (=lcbv6 seeds) | 131 | 126 | 84 | 42 | 42 |

**Off-limits as training data:** all `data/filtered/*`; `data/seeds/{aime25*,hmmt25*,lcbv6*,
hard11,length_probe*,reachability*,budget_check_one}`; and `external/squeeze-evolve/data/{aime25,
hmmt25}/test.parquet` (the upstream source of those seeds).

**How to avoid leakage:**
1. Generate SE/raw data **only** from a training pool that is provably disjoint from
   AIME25/HMMT25/LCBV6 (different competitions/years and verified non-overlapping).
2. Keep `data/filtered/*` strictly for evaluation; never feed eval gold answers/tests back into
   generation or SFT.
3. After choosing a training pool, run an ID/text-overlap check against `data/filtered/*` before
   any generation.

**Flag:** `math500_seed.jsonl` does **not** overlap AIME/HMMT/LCBV6, but **MATH-500 is itself a
public benchmark**; using it as SFT training data is defensible only as a *smoke* pool, not as
the headline training set. Confirm with Harman.

---

## 7. Proposed SE-SFT experiment plan (grounded in actual repo support)

> Scripts referenced below **exist** unless explicitly marked **MISSING**. Gate: do not run full
> generation/training until Harman confirms the training-data source and SE hyperparameters.

**A. Smoke seed pool (20–50, to create)**
- Path: `data/seeds/sft_smoke_seed.jsonl`.
- Source: simplest safe option = first 20–50 lines of `data/seeds/math500_seed.jsonl` (has gold,
  no AIME/HMMT/LCBV6 overlap). Schema `{id, question, answer}`.
- Use only to validate the chain end-to-end at tiny cost.

**B. Full train seed pool (to decide + fetch — currently MISSING)**
- Candidate size: 1k–5k (or whatever the chosen pool provides).
- Source options (none present locally; require download approval): NuminaMath-CoT,
  OpenThoughts, MATH **train** split, OlympiadBench. Prefer a pool with gold answers (enables
  correct-only filtering, §D).
- Leakage check: run text/ID overlap vs `data/filtered/*` before generating.
- **MATH-500 (`math500_seed.jsonl`) is the only ready, non-AIME/HMMT/LCBV6 pool**, but it is a
  benchmark set — acceptable as a fallback/pilot, flagged for Harman.

**C. SE data-generation command (template; matches the running Node1 recipe — confirm before
launching)** — loops=5, population=16, max_tokens=32768, temp=1.0, top_p=0.95, top_k=20,
`strip_think=false`, `fitness=diversity`, output under `outputs/sft_datagen/`. Reuse
`configs/squeeze_evolve_loop5_32k_temp1_aime_non_saturated.yaml` as the structural template but
**point it at the training seed pool and a new output/checkpoint dir** (copy to a new
`configs/squeeze_evolve_sft_datagen.yaml`; do not edit the in-flight Node1 config). Command as in
§3. (Population=16 vs the template default 4 → confirm with Harman per CLAUDE.md placeholder rule.)

**D. Candidate filtering strategy**
- **SE-final-only** (default): `convert_se_to_sft.py` already takes `candidates[0]`/final
  population — zero new code.
- **SE-all-candidates / loop-curriculum**: available via `se_loop_candidates.py` (per-loop rows
  with `loop_index`, `parent_ids`) — richer, but needs a small flatten→chat adapter.
- **Correct-only** (recommended if gold present): score with `score_se_subset.py` (math
  exact-match / code exec), keep only `final_answer == gold`. **MISSING:** a thin joiner that
  filters `convert_se_to_sft` inputs by the score output (`final_answer`/`pass_tests`). ~small
  script.
- **Malformed/no-answer removal**: `convert_*_to_sft.py` already drops empty/short responses;
  add a "has extractable `\boxed{}`/code block" filter if correct-only is not used.

**E. SFT dataset construction** — `convert_se_to_sft.py` (SE) and `convert_raw_to_sft.py`
(baseline), then optionally `export_llamafactory_data.py`. **Exists.** Only the correct-only
*joiner* in §D is missing.

**F. Training command** — `scripts/train_sft.py` with `configs/sft_qwen3_4b_lora_quick.yaml`
(or LLaMA-Factory `configs/llamafactory/qwen3_4b_se_sft_lora.yaml`). **Exists.** Mirror the iron
rule: an SE-SFT arm and a Raw-SFT arm (and base) differing only in data.
```bash
python scripts/train_sft.py --config configs/sft_qwen3_4b_lora_quick.yaml \
  --train-file data/sft/squeeze_evolve_sft_train.jsonl --output-dir outputs/qwen3_4b_se_sft
```

**G. Evaluation command** — held-out AIME/HMMT/LCBV6 only, via §5 templates. Compare
base vs Raw-SFT vs SE-SFT pass@1 (math) and tests-pass rate (LCBV6).

---

## 8. What exists / what's missing

**Exists (no new code needed):** SE generation + loop flattening + budget + offline scoring;
raw & N-sample generation; SE→SFT and raw→SFT converters; LLaMA-Factory export; TRL & LLaMA-Factory
training; LoRA merge; math pass@1 eval; reachability/any-of-N; LCBV6 code execution eval; Qwen3 +
thinking-trace preservation throughout; two documented end-to-end runbooks.

**Missing / to add:**
1. **A non-leaking training seed pool** (the real blocker) — must be fetched/prepared; not in repo.
2. **Correct-only filter joiner** (§D) — small script linking `score_se_subset.py` output to the
   SFT converter, if we want correctness-filtered SE targets.
3. **(Optional) loop-curriculum SFT adapter** — flatten `se_loop_candidates.py` rows into chat
   examples if training on all-loops rather than final-only.
4. **A dedicated SE-datagen config** pointed at the training pool + new output dir (copy, don't
   edit the in-flight Node1 config).
5. **SE-hyperparameter confirmation** (population/loops/etc.) per CLAUDE.md placeholder rule.

---

## 9. Statement of non-execution

No SqueezeEvolve generation, no model/API/vLLM generation, no SFT/RL training, and no evaluation
were run in producing this document. No existing experiment outputs were modified. The Node1/Node2
reachability runs were not interrupted. AIME/HMMT/LCBV6 held-out data was **not** used as training
data. This file is the only artifact created.
