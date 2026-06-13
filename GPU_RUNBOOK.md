# GPU runbook (8×H100 collaborator)

Step-by-step to run the full pipeline end-to-end on a real GPU box.
Replace `data/seeds/math_seed.jsonl` and `data/eval/aime_or_hmmt.jsonl`
with whatever real seed/eval files you're using; the sample files in the
repo are only for smoke tests.

## 0. Why these steps exist (and what you can skip on CPU)

Most local development machines (Windows, macOS, CPU-only Linux) **cannot
run any of the generation / training / evaluation steps**. Those need a
loaded model on a GPU. On a CPU box you can only do:

```bash
python -m pytest                                              # 59 tests
python scripts/<any>.py --help                                # arg parsing
python scripts/run_squeeze_evolve.py ... --dry-run            # command construction
```

Everything below assumes you are on the H100 box.

## Step 1: Solution Reachability Diagnostic (run BEFORE the SFT pipeline below)

**Purpose.** Before any SFT, check whether evolutionary test-time scaling actually
reaches solutions ordinary sampling does not. On the SAME fixed math problems compare:

- **Arm A** — official SqueezeEvolve generation (`scripts/run_squeeze_evolve.py`).
- **Arm B** — *compute-matched* independent rollouts from the same base model
  (`scripts/run_independent_rollouts.py`): `N_i` independent samples per problem, where
  `N_i` is SqueezeEvolve's per-problem rollout budget.

Then `scripts/eval_reachability.py` (any-of-N, same exact-match grader) labels each
problem `both_solved | only_se_solved | only_independent_solved | neither_solved`.

**Why before SFT.** The hypothesis is that population-based search reaches solution space
independent sampling cannot at matched compute, making those traces better
self-distillation targets. If SqueezeEvolve reaches no extra solutions at matched budget,
the downstream SFT comparison isn't worth running. This is the cheap go/no-go.

### Prepare the seed dataset (safe data prep — NOT generation)

Both arms consume ONE fixed, answer-bearing seed set, built with the existing
`scripts/prepare_math_seed.py` (pure local transform — no model). Output schema is
`{id, question, answer}`.

**MATH500 — available locally, start here.** Source (note the real path — there is **no**
`opsd/` segment): `/mnt/cpfs/yangboxue/wujunyi/LightningRL/data/MATH500.json` — 500 records,
keys `question` / `ground_truth_answer`.

```bash
# Smoke subset (5 problems) — verified working; schema {id, question, answer}
python scripts/prepare_math_seed.py \
    --input  /mnt/cpfs/yangboxue/wujunyi/LightningRL/data/MATH500.json \
    --output data/seeds/math500_seed_smoke.jsonl \
    --question-field question --answer-field ground_truth_answer \
    --id-prefix math500- --require-answer --limit 5

# Full MATH500 (500 problems) — SAFE DATA PREP, NOT generation (drop --limit)
python scripts/prepare_math_seed.py \
    --input  /mnt/cpfs/yangboxue/wujunyi/LightningRL/data/MATH500.json \
    --output data/seeds/math500_seed.jsonl \
    --question-field question --answer-field ground_truth_answer \
    --id-prefix math500- --require-answer
```

**AIME-2025 / HMMT-2025 — placeholder; confirm dataset with Harman first.** SqueezeEvolve
bundles these as parquet at `external/squeeze-evolve/data/{aime25,hmmt25}/test.parquet`
(30 problems each). Fields are nested (question = `prompt[0]['content']`, answer =
`reward_model['ground_truth']`), so flatten first, then reuse `prepare_math_seed.py`.
⛔ Do NOT run until Harman confirms the dataset:

```bash
# TODO_HARMAN_CONFIRM dataset. Flatten parquet -> flat JSONL (no model); swap aime25 <-> hmmt25.
python - <<'PY'
import pandas as pd, json
ds = "aime25"   # or "hmmt25"
df = pd.read_parquet(f"external/squeeze-evolve/data/{ds}/test.parquet")
with open(f"data/seeds/_{ds}_flat.jsonl", "w") as f:
    for _, r in df.iterrows():
        f.write(json.dumps(
            {"question": r["prompt"][0]["content"], "answer": str(r["reward_model"]["ground_truth"])},
            ensure_ascii=False) + "\n")
PY
python scripts/prepare_math_seed.py \
    --input  data/seeds/_aime25_flat.jsonl \
    --output data/seeds/aime25_seed.jsonl \
    --id-prefix aime25- --require-answer
```

**Dataset choice (confirm with Harman):**
- **MATH500** — 500 problems, broad difficulty; good for smoke + plumbing, but likely
  **saturates** Qwen3-4B-Thinking-2507 (near-ceiling accuracy ⇒ little reachability gap).
- **AIME-2025 / HMMT-2025** — only 30 problems each (small sample) but much harder ⇒ better
  for **measuring reachability gaps** between SqueezeEvolve and independent sampling.
- Likely plan: smoke on a MATH500 subset, *measure* on AIME/HMMT (or a hard MATH500 slice).
  Final choice is Harman's.

### ⛔ Safety gate
DO NOT start full data generation until Harman confirms recommended SqueezeEvolve
hyperparameters. The full-run knobs in `configs/squeeze_evolve_generation.yaml`
(`routing.population`, `routing.loops`, `routing.k`, `routing.fitness`) are
**placeholders — `TODO_HARMAN_CONFIRM`**. Independently, the per-problem budget `N_i` is
currently **UNKNOWN**: `scripts/se_budget.py` cannot yet recover it from SqueezeEvolve
telemetry, so true compute-matching is blocked until one smoke run is inspected.

### Right now — exact next commands (safe; no GPU / model / API)
```bash
# 1. Prepare the MATH500 smoke seed (data prep, no model)
python scripts/prepare_math_seed.py \
    --input  /mnt/cpfs/yangboxue/wujunyi/LightningRL/data/MATH500.json \
    --output data/seeds/math500_seed_smoke.jsonl \
    --question-field question --answer-field ground_truth_answer \
    --id-prefix math500- --require-answer --limit 5

# 2. Run the test suite (expect: 87 passed)
python -m pytest -q

# 3. SqueezeEvolve command construction ONLY — NO generation (--dry-run skips the model)
python scripts/run_squeeze_evolve.py \
    --input  data/seeds/math500_seed_smoke.jsonl \
    --output /tmp/se_out.jsonl \
    --config configs/squeeze_evolve_generation.yaml \
    --squeeze-evolve-dir external/squeeze-evolve \
    --model Qwen/Qwen3-4B-Thinking-2507 --dry-run

# 4. STOP. Do not run real generation until Harman confirms hyperparameters.
```

Other safe checks (no model): `--help` on any script, and the offline reachability
evaluator on bundled fixtures:
```bash
python scripts/eval_reachability.py \
    --se-output          tests/fixtures/mock_se_outputs.jsonl \
    --independent-output tests/fixtures/mock_independent_outputs.jsonl \
    --output-jsonl       /tmp/reach_per_problem.jsonl \
    --summary-json       /tmp/reach_summary.json
# -> total=4 both=1 only_se=1 only_independent=1 neither=1
```

### Pre-generation checklist
Every box must be checked before launching ANY real generation:
- [ ] Official SqueezeEvolve installed — `pip install -e ".[dev]"` in `external/squeeze-evolve`; `which squeeze-evolve-client` prints a path.
- [ ] vLLM serving `Qwen/Qwen3-4B-Thinking-2507` (Step 3) and reachable.
- [ ] Seed JSONL prepared (`{id, question, answer}`) **and** dataset confirmed with Harman.
- [ ] Harman confirmed SqueezeEvolve hyperparameters (population / loops / k / fitness) — every `TODO_HARMAN_CONFIRM` replaced.
- [ ] Compute-match unit confirmed (#generations vs token budget).
- [ ] One tiny SqueezeEvolve smoke run completed and its raw `….raw.json` / `metrics.json` inspected to locate the per-problem rollout-budget field.
- [ ] `scripts/se_budget.py` updated if needed so `budget_status` flips UNKNOWN → FROM_RAW_METRICS.

### Full-run template — ⛔ DO NOT RUN BEFORE HARMAN CONFIRMS HYPERPARAMETERS
Needs the GPU box + running vLLM (Step 3) + SqueezeEvolve install (Step 2) + base model.
Replace every `TODO_HARMAN_CONFIRM`.
```bash
SEED=data/seeds/math500_seed.jsonl   # TODO_HARMAN_CONFIRM dataset (full MATH500, or AIME/HMMT seed)

# 1. [Arm A] SqueezeEvolve. First set in configs/squeeze_evolve_generation.yaml:
#      routing.population: TODO_HARMAN_CONFIRM
#      routing.loops:      TODO_HARMAN_CONFIRM
#      routing.k:          TODO_HARMAN_CONFIRM
#      routing.fitness:    TODO_HARMAN_CONFIRM   # diversity on stock vLLM unless confidence is wired up
python scripts/run_squeeze_evolve.py \
    --input "$SEED" --output data/generated/se_reach.jsonl \
    --config configs/squeeze_evolve_generation.yaml \
    --squeeze-evolve-dir external/squeeze-evolve \
    --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY

# 2. Recover per-problem budget N_i (ONLY trustworthy after se_budget.py is taught the
#    real telemetry field from a smoke run; until then budget_status stays UNKNOWN).
python scripts/se_budget.py \
    --se-output data/generated/se_reach.jsonl \
    --raw-json  data/generated/se_reach.jsonl.raw.json \
    --config    configs/squeeze_evolve_generation.yaml \
    --output    data/results/se_budget.jsonl
#    If budget_status is UNKNOWN, STOP — compute-matching is not yet valid.

# 3. [Arm B] compute-matched independent rollouts (N = TODO_HARMAN_CONFIRM, ideally per-problem N_i).
python scripts/run_independent_rollouts.py \
    --input "$SEED" --output data/generated/independent_reach.jsonl \
    --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY \
    --n-samples TODO_HARMAN_CONFIRM \
    --temperature 0.7 --top-p 0.95 --max-tokens 8192   # match SqueezeEvolve's sampling

# 4. Reachability comparison.
python scripts/eval_reachability.py \
    --se-output          data/generated/se_reach.jsonl \
    --independent-output data/generated/independent_reach.jsonl \
    --se-budget-jsonl    data/results/se_budget.jsonl \
    --output-jsonl       data/results/reachability_per_problem.jsonl \
    --summary-json       data/results/reachability_summary.json
```
Headline = `only_se_solved` vs `only_independent_solved`: a reproducible `only_se_solved`
set materially larger than `only_independent_solved` is the evidence that evolutionary
TTS reaches new solution space.

## 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`torch` in `requirements.txt` is unpinned — pip will pull a CUDA build
that matches the host. If you need a specific CUDA version, install
torch first via the official wheel index and then `pip install -r
requirements.txt`.

## 2. Clone and install Squeeze-Evolve

```bash
git clone --recurse-submodules \
    https://github.com/squeeze-evolve/squeeze-evolve.git external/squeeze-evolve
cd external/squeeze-evolve
pip install -e ".[dev]"
cd ../..
which squeeze-evolve-client     # must print a path
```

`external/squeeze-evolve/` is gitignored on purpose; every contributor
clones it themselves.

## 3. Start vLLM

The base model is `Qwen/Qwen3-4B-Thinking-2507`. One H100 is plenty.

```bash
vllm serve Qwen/Qwen3-4B-Thinking-2507 \
    --host 0.0.0.0 --port 8000 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.90
```

Keep this terminal open. Verify from a second terminal:

```bash
curl -s http://localhost:8000/v1/models | head -c 400
```

## 4. Generate raw self-SFT data

```bash
python scripts/run_raw_generation.py \
    --input  data/seeds/math_seed.jsonl \
    --output data/generated/raw_generations.jsonl \
    --model Qwen/Qwen3-4B-Thinking-2507 \
    --base-url http://localhost:8000/v1 \
    --api-key EMPTY \
    --temperature 0.6 --top-p 0.95 --max-tokens 8192
```

Resume-safe: re-running picks up where it left off (skips ids already in
the output). Add `--overwrite` to start fresh.

## 5. Generate SqueezeEvolve data

```bash
python scripts/run_squeeze_evolve.py \
    --input  data/seeds/math_seed.jsonl \
    --output data/generated/squeeze_evolve_outputs.jsonl \
    --config configs/squeeze_evolve_generation.yaml \
    --squeeze-evolve-dir external/squeeze-evolve \
    --model Qwen/Qwen3-4B-Thinking-2507 \
    --base-url http://localhost:8000/v1 \
    --api-key EMPTY
```

The wrapper writes both:
- `data/generated/squeeze_evolve_outputs.jsonl` — one normalized JSONL
  line per seed (the file we hand to the SFT converter).
- `data/generated/squeeze_evolve_outputs.jsonl.raw.json` — the raw
  orchestrator JSON (`{run_id, metrics, problems: [...]}`), kept for
  inspection and ablations.

Defaults in `configs/squeeze_evolve_generation.yaml`: `population=4`,
`loops=4`, `fitness=diversity`, `recombination=aime25-aggregate`,
`evaluation=aime25-none`, `strip_think=false`. Switch to `population=16,
loops=10` once you've confirmed the toy run works.

## 6. Convert to SFT chat format

```bash
python scripts/convert_raw_to_sft.py \
    --input  data/generated/raw_generations.jsonl \
    --output data/sft/raw_self_sft_train.jsonl

python scripts/convert_se_to_sft.py \
    --input  data/generated/squeeze_evolve_outputs.jsonl \
    --output data/sft/squeeze_evolve_sft_train.jsonl
```

Both produce `{id, messages: [user, assistant], source}` records.
`<think>...</think>` blocks are preserved verbatim — do not strip them.

## 7. Pick an SFT preset

Three configs live in `configs/`. Pass one via `--config`; CLI flags
override its keys.

| Preset file | Stage | Highlights |
|---|---|---|
| `sft_qwen3_4b_lora_smoke.yaml` | 1. Smoke | LoRA r=16/α=32, lr=5e-6, grad-accum 8, max-seq 8192. Pair with `--max-steps 20` for a one-minute liveness check. |
| `sft_qwen3_4b_lora_quick.yaml` | 2. Quick real | LoRA r=32/α=64, lr=2e-5, **effective batch 64**, max-seq 8192 (bump to 16384 if memory permits). |
| `sft_qwen3_4b_paper_aligned.yaml` | 3. Paper-aligned | Full fine-tune (LoRA toggle available), lr=2e-5, max_steps=4000, max-seq 32768, effective batch 64. |

All three share `lr_scheduler_type: cosine`, `warmup_ratio: 0.03`,
`weight_decay: 0.0`, `max_grad_norm: 0.2`, `adam_beta1: 0.9`,
`adam_beta2: 0.999`, `seed: 42`, `bf16: true`. Qwen3's built-in chat
template (with `<think>...</think>` support) is applied automatically
by the tokenizer — we never strip thinking blocks.

**Effective batch size = `per_device_train_batch_size × gradient_accumulation_steps × world_size`.**
The configs assume 1 GPU. Keep the product at 64 (quick / paper presets)
when you scale out:

| GPUs | `per_device_train_batch_size` | `gradient_accumulation_steps` |
|---:|---:|---:|
| 1 | 1 | 64 |
| 2 | 1 | 32 |
| 4 | 1 | 16 |
| 8 | 1 | 8 |

Override on the CLI, e.g. `--gradient-accumulation-steps 8` for 8 GPUs.

### One iron rule

**Raw self-SFT and SqueezeEvolve-SFT must use the exact same preset and
exact same CLI overrides.** The only allowed differences are
`--train-file` and `--output-dir`. If you change a hyperparameter for
one of them, you must rerun both — otherwise the comparison no longer
isolates the training data.

## 8. Train Raw-SFT and SqueezeEvolve-SFT (quick preset)

The "quick" preset is the recommended starting point for the headline
experiment. Single GPU:

```bash
# Raw self-SFT
python scripts/train_sft.py \
    --config configs/sft_qwen3_4b_lora_quick.yaml \
    --train-file data/sft/raw_self_sft_train.jsonl \
    --output-dir outputs/qwen3_4b_raw_sft

# SqueezeEvolve-SFT — same config, only data + output dir change
python scripts/train_sft.py \
    --config configs/sft_qwen3_4b_lora_quick.yaml \
    --train-file data/sft/squeeze_evolve_sft_train.jsonl \
    --output-dir outputs/qwen3_4b_se_sft
```

8×H100 (drop grad-accum to 8 so effective batch stays at 64):

```bash
accelerate launch --num_processes 8 scripts/train_sft.py \
    --config configs/sft_qwen3_4b_lora_quick.yaml \
    --train-file data/sft/raw_self_sft_train.jsonl \
    --output-dir outputs/qwen3_4b_raw_sft \
    --gradient-accumulation-steps 8

accelerate launch --num_processes 8 scripts/train_sft.py \
    --config configs/sft_qwen3_4b_lora_quick.yaml \
    --train-file data/sft/squeeze_evolve_sft_train.jsonl \
    --output-dir outputs/qwen3_4b_se_sft \
    --gradient-accumulation-steps 8
```

For the **smoke** preset, swap `--config` and add `--max-steps 20`. For
the **paper-aligned** preset, swap `--config`; full fine-tuning at
max-seq 32768 generally needs FSDP or DeepSpeed ZeRO-3 — see
`accelerate config` and Hugging Face's
[FSDP docs](https://huggingface.co/docs/accelerate/usage_guides/fsdp).
`training_metadata.json` is written next to every checkpoint on
completion.

## 9. Evaluate Base / Raw-SFT / SqueezeEvolve-SFT

The eval script loads the base model locally and optionally attaches a
PEFT adapter — no extra vLLM run needed.

```bash
# Base (no adapter)
python scripts/eval_math.py \
    --eval-file data/eval/aime_or_hmmt.jsonl \
    --model-name-or-path Qwen/Qwen3-4B-Thinking-2507 \
    --output data/results/base_eval.jsonl \
    --temperature 0.0 --max-tokens 8192

# Raw self-SFT
python scripts/eval_math.py \
    --eval-file data/eval/aime_or_hmmt.jsonl \
    --model-name-or-path Qwen/Qwen3-4B-Thinking-2507 \
    --adapter-path outputs/qwen3_4b_raw_sft \
    --output data/results/raw_sft_eval.jsonl \
    --temperature 0.0 --max-tokens 8192

# SqueezeEvolve-SFT
python scripts/eval_math.py \
    --eval-file data/eval/aime_or_hmmt.jsonl \
    --model-name-or-path Qwen/Qwen3-4B-Thinking-2507 \
    --adapter-path outputs/qwen3_4b_se_sft \
    --output data/results/se_sft_eval.jsonl \
    --temperature 0.0 --max-tokens 8192
```

Each run prints `total=<N> correct=<K> accuracy=<P>` at the end and
writes one JSONL record per eval example for offline inspection. If you
prefer to serve the merged model via vLLM instead of loading locally,
use `scripts/merge_lora.py` and pass `--use-vllm-server --base-url ...`
to `eval_math.py`.

## 10. The headline number

Compare the three accuracy values. The experiment's question is:

> Does SqueezeEvolve-SFT improve pass@1 math performance more than raw
> self-SFT, with everything else held equal?

Anything outside of these three numbers is exploratory.
