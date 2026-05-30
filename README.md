# tts-sft

End-to-end pipeline for one focused experiment:

> **Does fine-tuning on test-time-scaled (SqueezeEvolve) generations beat
> fine-tuning on raw self-generations, measured by pass@1 on math?**

The pipeline has three stages: **data generation → SFT → evaluation**, and
the same base model (`Qwen/Qwen3-4B-Thinking-2507` by default) is reused
throughout so the comparison is apples-to-apples.

## 1. What this repo does

- Generates training data two ways from a shared seed of math problems:
  - **Raw self-generation** — one ordinary sample from the base model.
  - **SqueezeEvolve** — test-time scaling via the official SqueezeEvolve
    framework (cloned into `external/squeeze-evolve/`).
- Converts both to chat-format SFT JSONL, preserving the full reasoning
  trace including `<think>...</think>` segments.
- Runs LoRA SFT (HF Transformers + TRL + PEFT) on each dataset.
- Evaluates the base model and both SFT'd models on a held-out math set
  with exact-match on the final boxed answer.

## 2. What this repo does NOT do

- No reinforcement learning, no GRPO, no PPO, no verl.
- No Fast-Slow Training / FST.
- No LLaMA-Factory.
- No reimplementation of SqueezeEvolve — only a thin wrapper around the
  official repo.
- No symbolic answer equivalence — exact match after shallow
  normalization is the only scoring rule in v1.

## 3. Install

```bash
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Optional sanity check:

```bash
make test
```

## 4. Clone SqueezeEvolve

```bash
git clone --recurse-submodules \
    https://github.com/squeeze-evolve/squeeze-evolve.git external/squeeze-evolve
cd external/squeeze-evolve
pip install -e ".[dev]"
cd ../..
```

This installs the `squeeze-evolve-client` console script that our wrapper
calls. `external/squeeze-evolve/` is gitignored; only the pointer README
stays in this repo. See `external/README.md` for the full wrapper /
operator / output-schema notes.

## 5. Start local vLLM

```bash
vllm serve Qwen/Qwen3-4B-Thinking-2507 \
    --host 0.0.0.0 \
    --port 8000 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.90
```

All scripts that need generation hit `http://localhost:8000/v1` by default.

## 6. Generate raw self-SFT data

```bash
python scripts/run_raw_generation.py \
    --input data/seeds/math_seed.jsonl \
    --output data/generated/raw_generations.jsonl \
    --model Qwen/Qwen3-4B-Thinking-2507 \
    --base-url http://localhost:8000/v1 \
    --api-key EMPTY \
    --max-tokens 8192
```

Already-generated `id`s are skipped automatically; pass `--overwrite` to
start fresh.

## 7. Generate SqueezeEvolve data

```bash
python scripts/run_squeeze_evolve.py \
    --input data/seeds/math_seed.jsonl \
    --output data/generated/squeeze_evolve_outputs.jsonl \
    --config configs/squeeze_evolve_generation.yaml \
    --squeeze-evolve-dir external/squeeze-evolve \
    --model Qwen/Qwen3-4B-Thinking-2507 \
    --base-url http://localhost:8000/v1 \
    --api-key EMPTY
```

Under the hood the wrapper:

1. Converts the seed JSONL to the `{orig_prompt, gt, question}` schema
   the orchestrator expects.
2. Patches `--model`/`--base-url`/`--api-key` into every entry of
   `models:` in the YAML config (writing a temp copy).
3. Invokes the **official** `squeeze-evolve-client --config <patched>
   --input <converted> --output <raw>.json` with `cwd` set to
   `external/squeeze-evolve/` so the benchmark operator registries
   auto-discover.
4. Reads the resulting JSON and writes one JSONL line per seed with
   `id`, `question`, `gt`, `final_response` (first candidate of the
   evolved population), and the full `candidates` list.

If `squeeze-evolve-client` is missing on PATH or returns non-zero, the
wrapper exits with manual run instructions. It never fabricates output.

## 8. Convert to SFT format

```bash
python scripts/convert_raw_to_sft.py \
    --input data/generated/raw_generations.jsonl \
    --output data/sft/raw_self_sft_train.jsonl

python scripts/convert_se_to_sft.py \
    --input data/generated/squeeze_evolve_outputs.jsonl \
    --output data/sft/squeeze_evolve_sft_train.jsonl
```

The SqueezeEvolve converter tries several common response keys; pass
`--response-key final_response` (or any dotted path) when the schema is
known.

## 9. Choose an SFT preset

Three preset configs live in `configs/`. Each is loaded via
`--config <yaml>`; any CLI flag you also pass overrides the YAML.

| Preset | Purpose | LoRA | LR | Effective BS | Notes |
|---|---|---|---|---|---|
| `sft_qwen3_4b_lora_smoke.yaml` | verify training runs | r=16, α=32 | 5e-6 | 8 | combine with `--max-steps 20` for a 1-minute smoke test |
| `sft_qwen3_4b_lora_quick.yaml` | first real Raw vs SE comparison | r=32, α=64 | 2e-5 | 64 | the recommended preset for the headline experiment |
| `sft_qwen3_4b_paper_aligned.yaml` | full fine-tune (Percy SVD recipe) | full FT (toggle to LoRA) | 2e-5 | 64 | `max_steps: 4000`, `max_seq_length: 32768` |

Common to all three: `lr_scheduler_type: cosine`, `warmup_ratio: 0.03`,
`weight_decay: 0.0`, `max_grad_norm: 0.2`, `adam_beta1: 0.9`,
`adam_beta2: 0.999`, `seed: 42`, `bf16: true`, Qwen3's built-in chat
template.

> **Identical hyperparameters across runs.** Raw-self-SFT and
> SqueezeEvolve-SFT **must** use the same preset — anything other than
> the training data changing invalidates the comparison. Don't write two
> separate config files for them; pass one preset and override
> `--train-file` / `--output-dir` on the CLI.

## 10. Train both models with the quick preset

```bash
# Raw self-SFT
python scripts/train_sft.py \
    --config configs/sft_qwen3_4b_lora_quick.yaml \
    --train-file data/sft/raw_self_sft_train.jsonl \
    --output-dir outputs/qwen3_4b_raw_sft

# SqueezeEvolve-SFT (same preset, only data + output dir change)
python scripts/train_sft.py \
    --config configs/sft_qwen3_4b_lora_quick.yaml \
    --train-file data/sft/squeeze_evolve_sft_train.jsonl \
    --output-dir outputs/qwen3_4b_se_sft
```

For the smoke test, swap the config and add `--max-steps 20`. For the
paper-aligned run, swap the config; full FT will need FSDP / DeepSpeed
ZeRO-3 on 8×H100 — see `GPU_RUNBOOK.md`.

### Optional mature SFT backend: LLaMA-Factory

If you'd rather train with [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory)
than our in-repo trainer, the data export script and ready-to-use
recipes live under `scripts/export_llamafactory_data.py` and
`configs/llamafactory/`. Quick summary:

- `scripts/train_sft.py` stays the **default** transparent backend; it
  is not removed.
- LLaMA-Factory is offered as an **optional, mature alternative** —
  collaborators who already use it get its mature checkpoint /
  logging / chat-template handling for free.
- Both backends consume the **same generated SFT data**. The exporter
  converts our chat-format JSONL into LLaMA-Factory's ShareGPT JSON
  (preserving `<think>...</think>` and `\boxed{...}` verbatim).
- For a fair comparison, **Raw-SFT and SqueezeEvolve-SFT must use
  exactly the same SFT hyperparameters** — the iron rule applies to
  whichever backend you pick. The two LLaMA-Factory recipes
  (`qwen3_4b_raw_sft_lora.yaml` and `qwen3_4b_se_sft_lora.yaml`)
  differ only in `dataset` and `output_dir`, and they match the
  hyperparameters in `configs/sft_qwen3_4b_lora_quick.yaml` knob for
  knob.

Full step-by-step is in `GPU_RUNBOOK_LLAMAFATORY.md` at the repo root.

## 11. Evaluate Base / Raw-SFT / SqueezeEvolve-SFT

```bash
# Base
python scripts/eval_math.py \
    --eval-file data/eva
    l/aime_or_hmmt.jsonl \
    --model-name-or-path Qwen/Qwen3-4B-Thinking-2507 \
    --output data/results/base_eval.jsonl

# Raw self-SFT
python scripts/eval_math.py \
    --eval-file data/eval/aime_or_hmmt.jsonl \
    --model-name-or-path Qwen/Qwen3-4B-Thinking-2507 \
    --adapter-path outputs/qwen3_4b_raw_sft \
    --output data/results/raw_sft_eval.jsonl

# SqueezeEvolve-SFT
python scripts/eval_math.py \
    --eval-file data/eval/aime_or_hmmt.jsonl \
    --model-name-or-path Qwen/Qwen3-4B-Thinking-2507 \
    --adapter-path outputs/qwen3_4b_se_sft \
    --output data/results/se_sft_eval.jsonl
```

`--use-vllm-server --base-url http://localhost:8000/v1` switches to the
server backend (no PEFT adapter loading — serve the merged model instead;
see `scripts/merge_lora.py`).

Each run prints `total=<N> correct=<K> accuracy=<P>` and writes one JSONL
record per example.

## Repository layout

```
tts-sft/
├── configs/                 YAML defaults for each pipeline stage
├── data/
│   ├── seeds/               math seed questions
│   ├── eval/                held-out eval set with gold answers
│   ├── generated/           outputs of raw + SqueezeEvolve runs
│   ├── sft/                 chat-format training files
│   └── results/             per-example eval logs
├── scripts/                 one CLI per pipeline step
├── src/tts_sft/             reusable library code
├── tests/                   pytest tests
└── external/                pointer to external clones (gitignored)
```

## Make targets

```
make install
make test
make raw-generate     make convert-raw     make train-raw     make eval-raw
make squeeze-generate make convert-squeeze make train-squeeze make eval-squeeze
make eval-base
```

Override defaults via env: `make raw-generate SEED=data/seeds/math_seed.jsonl`.
