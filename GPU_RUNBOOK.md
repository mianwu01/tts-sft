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

## 7. Train Raw-SFT

```bash
python scripts/train_sft.py \
    --model-name-or-path Qwen/Qwen3-4B-Thinking-2507 \
    --train-file data/sft/raw_self_sft_train.jsonl \
    --output-dir outputs/qwen3_4b_raw_sft \
    --use-lora --bf16 \
    --max-seq-length 8192 \
    --learning-rate 5e-6 \
    --num-train-epochs 1 \
    --per-device-train-batch-size 1 \
    --gradient-accumulation-steps 16 \
    --lora-r 16 --lora-alpha 32 --lora-dropout 0.05 \
    --gradient-checkpointing
```

For multi-GPU runs, prefix with `accelerate launch` after
`accelerate config` (or use `torchrun --nproc_per_node 8` if you prefer).
`training_metadata.json` is written next to the adapter on completion.

## 8. Train SqueezeEvolve-SFT

Identical hyperparameters to step 7 — only the train file and output
directory change. That isolation is the whole point of the experiment.

```bash
python scripts/train_sft.py \
    --model-name-or-path Qwen/Qwen3-4B-Thinking-2507 \
    --train-file data/sft/squeeze_evolve_sft_train.jsonl \
    --output-dir outputs/qwen3_4b_se_sft \
    --use-lora --bf16 \
    --max-seq-length 8192 \
    --learning-rate 5e-6 \
    --num-train-epochs 1 \
    --per-device-train-batch-size 1 \
    --gradient-accumulation-steps 16 \
    --lora-r 16 --lora-alpha 32 --lora-dropout 0.05 \
    --gradient-checkpointing
```

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
