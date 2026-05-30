# GPU runbook — LLaMA-Factory backend

End-to-end run instructions for the **optional** LLaMA-Factory SFT
backend. This is a parallel path to `GPU_RUNBOOK.md` (which uses the
in-repo TRL/PEFT trainer); the two share the same data generation and
evaluation steps.

> `GPU_RUNBOOK_LLAMAFATORY.md` — yes, that filename has a typo
> (`LLAMAFATORY` should be `LLAMAFACTORY`). It was specified verbatim
> in the task brief; rename freely if you want.

This box must have GPU(s) and `Qwen/Qwen3-4B-Thinking-2507` weights
accessible (either downloaded from HF or mounted locally). All steps
below assume you start from a fresh shell on the GPU machine.

## A. Clone this repo

```bash
git clone <repo-url>
cd tts-sft
```

## B. Create a Python environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## C. Clone Squeeze-Evolve (for the SE data path)

```bash
git clone --recurse-submodules \
    https://github.com/squeeze-evolve/squeeze-evolve.git external/squeeze-evolve
cd external/squeeze-evolve
pip install -e ".[dev]"
cd ../..
```

Skip this step if you only want to retrain on the raw self-generated
dataset.

## D. Clone LLaMA-Factory

```bash
git clone https://github.com/hiyouga/LLaMA-Factory.git external/LLaMA-Factory
cd external/LLaMA-Factory
pip install -e ".[torch,metrics]"
cd ../..
which llamafactory-cli      # must print a path
```

`external/LLaMA-Factory/` is gitignored on purpose; every contributor
clones it themselves.

## E. Generate or prepare SFT data

Generate first (see `GPU_RUNBOOK.md` §4–§5 for vLLM + raw + SE
generation), then convert each generation file to our chat-format SFT
JSONL:

```bash
# Raw self-generated -> chat-format SFT
python scripts/convert_raw_to_sft.py \
    --input  data/generated/raw_generations.jsonl \
    --output data/sft/raw_self_sft_train.jsonl

# SqueezeEvolve -> chat-format SFT
python scripts/convert_se_to_sft.py \
    --input  data/generated/squeeze_evolve_outputs.jsonl \
    --output data/sft/squeeze_evolve_sft_train.jsonl
```

These are the same chat-format JSONL files our TRL trainer would
consume. Both backends share them.

## F. Export to LLaMA-Factory format

```bash
python scripts/export_llamafactory_data.py \
    --input  data/sft/raw_self_sft_train.jsonl \
    --output external/LLaMA-Factory/data/raw_self_sft_llamafactory.json \
    --format sharegpt \
    --overwrite

python scripts/export_llamafactory_data.py \
    --input  data/sft/squeeze_evolve_sft_train.jsonl \
    --output external/LLaMA-Factory/data/squeeze_evolve_sft_llamafactory.json \
    --format sharegpt \
    --overwrite
```

The exporter writes a single JSON array per file (LLaMA-Factory's
ShareGPT schema): `<think>...</think>` blocks and `\boxed{...}` are
copied verbatim. Examples with anything other than exactly one user
turn followed by one assistant turn are skipped with a warning.

## G. Register the two datasets in `dataset_info.json`

LLaMA-Factory looks up dataset names against
`external/LLaMA-Factory/data/dataset_info.json`. Open that file and
**merge in** the two entries from
`configs/llamafactory/dataset_info_example.json`:

```jsonc
// snippet from configs/llamafactory/dataset_info_example.json
"raw_self_sft": {
  "file_name": "raw_self_sft_llamafactory.json",
  "formatting": "sharegpt",
  "columns": {"messages": "conversations"},
  "tags": {
    "role_tag": "from",
    "content_tag": "value",
    "user_tag": "human",
    "assistant_tag": "gpt"
  }
},
"squeeze_evolve_sft": {
  "file_name": "squeeze_evolve_sft_llamafactory.json",
  "formatting": "sharegpt",
  "columns": {"messages": "conversations"},
  "tags": {
    "role_tag": "from",
    "content_tag": "value",
    "user_tag": "human",
    "assistant_tag": "gpt"
  }
}
```

`file_name` is resolved relative to `external/LLaMA-Factory/data/`, so
either keep the exported files there (recommended — step F already does
this) or change `file_name` to an absolute path.

Do not blindly overwrite LLaMA-Factory's `dataset_info.json` — it ships
with many useful entries; just splice the two new ones in.

## H. Train Raw-SFT

```bash
cd external/LLaMA-Factory
llamafactory-cli train ../../configs/llamafactory/qwen3_4b_raw_sft_lora.yaml
```

The adapter lands under `external/LLaMA-Factory/saves/qwen3_4b_raw_sft_lora/`.

For multi-GPU, prepend `accelerate launch` (after `accelerate config`)
and override `gradient_accumulation_steps` on the CLI to keep effective
batch = 64:

```bash
# 8x GPU example
accelerate launch --num_processes 8 \
    $(which llamafactory-cli) train \
    ../../configs/llamafactory/qwen3_4b_raw_sft_lora.yaml \
    --gradient_accumulation_steps 8
```

## I. Train SqueezeEvolve-SFT

```bash
# still inside external/LLaMA-Factory
llamafactory-cli train ../../configs/llamafactory/qwen3_4b_se_sft_lora.yaml
```

Adapter lands at `external/LLaMA-Factory/saves/qwen3_4b_se_sft_lora/`.

**This config is identical to the raw-SFT config except for `dataset`
and `output_dir`** (and must stay that way — see the iron rule in
`configs/llamafactory/README.md`).

For multi-GPU, mirror the override from step H exactly. Anything you
change for one run, change for the other too.

## J. Evaluate Base / Raw-SFT / SE-SFT

Return to the repo root and use the existing `scripts/eval_math.py`.
LLaMA-Factory's LoRA adapters are saved in HF PEFT format, so
`--adapter-path` accepts them directly.

```bash
cd ../..   # back to repo root

# Base (no adapter)
python scripts/eval_math.py \
    --eval-file data/eval/aime_or_hmmt.jsonl \
    --model-name-or-path Qwen/Qwen3-4B-Thinking-2507 \
    --output data/results/base_eval.jsonl

# Raw self-SFT
python scripts/eval_math.py \
    --eval-file data/eval/aime_or_hmmt.jsonl \
    --model-name-or-path Qwen/Qwen3-4B-Thinking-2507 \
    --adapter-path external/LLaMA-Factory/saves/qwen3_4b_raw_sft_lora \
    --output data/results/raw_sft_eval.jsonl

# SqueezeEvolve-SFT
python scripts/eval_math.py \
    --eval-file data/eval/aime_or_hmmt.jsonl \
    --model-name-or-path Qwen/Qwen3-4B-Thinking-2507 \
    --adapter-path external/LLaMA-Factory/saves/qwen3_4b_se_sft_lora \
    --output data/results/se_sft_eval.jsonl
```

Each run prints `total=<N> correct=<K> accuracy=<P>` and writes one
JSONL record per example.

### Optional: merge adapters and serve via vLLM

If you'd rather serve the fine-tuned models from vanilla vLLM than load
the adapter at eval time, merge with either tool:

- **In-repo helper:**
  ```bash
  python scripts/merge_lora.py \
      --base-model Qwen/Qwen3-4B-Thinking-2507 \
      --adapter-path external/LLaMA-Factory/saves/qwen3_4b_raw_sft_lora \
      --output-dir outputs/qwen3_4b_raw_sft_merged
  ```
- **LLaMA-Factory CLI:** `llamafactory-cli export` accepts a YAML with
  `export_dir` set and the same adapter — see LLaMA-Factory's docs.

Then re-run `eval_math.py` with `--use-vllm-server --base-url ...`
pointed at a vLLM serving the merged path.
