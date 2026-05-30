# LLaMA-Factory configs (optional)

This directory holds an **optional** alternative SFT backend. The
research pipeline in this repo still has its own transparent
TRL/PEFT trainer at `scripts/train_sft.py` — that script remains the
default and is not going away.

## What's here

| File | Purpose |
|---|---|
| `dataset_info_example.json` | Template for LLaMA-Factory's `data/dataset_info.json`. Registers `raw_self_sft` and `squeeze_evolve_sft` as ShareGPT-formatted datasets. |
| `qwen3_4b_raw_sft_lora.yaml` | LoRA SFT recipe for the raw self-generated data. |
| `qwen3_4b_se_sft_lora.yaml` | LoRA SFT recipe for the SqueezeEvolve-generated data. **Identical to the raw config except for `dataset` and `output_dir`.** |
| `qwen3_4b_sft_smoke.yaml` | A small config that only verifies LLaMA-Factory training starts (small LoRA, low LR, short cutoff). Use it for liveness checks, not for real comparisons. |

## When to use this backend

- You'd rather use mature, well-tested SFT tooling than our minimal
  trainer.
- You want LLaMA-Factory's logging, checkpoint management, and built-in
  chat templates.
- You're handing the run to a collaborator who already knows
  LLaMA-Factory.

If none of those apply, stick with `scripts/train_sft.py`.

## When NOT to use it

- Anything other than supervised fine-tuning. The whole experiment is
  SFT; we do not enable RL, GRPO, PPO, or any reward-model loop here.
- Cases where you need to inspect or modify the training loop itself —
  the in-repo TRL trainer is shorter and easier to read.

## Both backends share input data

Both LLaMA-Factory and `scripts/train_sft.py` consume the same exported
data files. The export script
(`scripts/export_llamafactory_data.py`) converts our chat-format JSONL
into ShareGPT JSON. The TRL trainer reads our chat-format JSONL
directly. The generated raw and SqueezeEvolve datasets are interchangeable
between the two backends.

## The iron rule (still)

> **Raw self-SFT and SqueezeEvolve-SFT must use the exact same
> hyperparameters.** The only difference between the two LLaMA-Factory
> configs (`qwen3_4b_raw_sft_lora.yaml` vs `qwen3_4b_se_sft_lora.yaml`)
> is `dataset` and `output_dir`. Do not touch the LR, batch size, LoRA
> rank, scheduler, seed, or any other knob for only one of the runs —
> that destroys the comparison.

This rule applies whether you train with LLaMA-Factory or with our
TRL/PEFT script.

## Hyperparameter parity with the in-repo TRL preset

These configs intentionally match
`configs/sft_qwen3_4b_lora_quick.yaml` (the recommended preset for the
headline experiment) on every shared knob: `learning_rate: 2.0e-5`,
effective batch 64, `lora_rank: 32`, `lora_alpha: 64`,
`lora_dropout: 0.05`, `lr_scheduler_type: cosine`, `warmup_ratio: 0.03`,
`weight_decay: 0.0`, `max_grad_norm: 0.2`, bf16, seed 42.

If you change a hyperparameter in one backend, change it in the other
too so the two backends remain comparable runs.

## Running

See `GPU_RUNBOOK_LLAMAFATORY.md` at the repo root for the full
step-by-step (clone, install, export, register, train, evaluate).
