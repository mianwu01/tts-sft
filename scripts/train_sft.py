#!/usr/bin/env python
"""LoRA (or full) SFT of a causal LM on chat-format JSONL.

Each input record must look like:
    {"id": "...", "messages": [{"role": "user", ...}, {"role": "assistant", ...}], ...}

The full assistant turn (including any ``<think>...</think>`` segments) is
preserved in the training text by default — the tokenizer's chat template
(e.g. Qwen3's) is applied as-is.

Config resolution order (highest precedence first):

    1. Explicit CLI flags.
    2. Keys in the YAML file passed via ``--config``.
    3. Built-in defaults below.

YAML keys use the underscored form of the CLI flag (``--lora-r`` -> ``lora_r``).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from tts_sft.io_utils import load_yaml  # noqa: E402

logger = logging.getLogger("train_sft")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=None, type=Path,
                   help="YAML preset (e.g. configs/sft_qwen3_4b_lora_quick.yaml). CLI flags override its keys.")

    # Paths & model
    p.add_argument("--model-name-or-path", default=None,
                   help="HF model id or local path. Required (from CLI or --config).")
    p.add_argument("--train-file", default=None, type=Path,
                   help="Chat-format JSONL. Required.")
    p.add_argument("--output-dir", default=None, type=Path,
                   help="Where adapters/checkpoints + training_metadata.json land. Required.")

    # Schedule
    p.add_argument("--max-seq-length", type=int, default=8192)
    p.add_argument("--learning-rate", type=float, default=5e-6)
    p.add_argument("--num-train-epochs", type=float, default=1.0)
    p.add_argument("--max-steps", type=int, default=-1,
                   help="If > 0, overrides --num-train-epochs (HF Trainer convention).")
    p.add_argument("--per-device-train-batch-size", type=int, default=1)
    p.add_argument("--gradient-accumulation-steps", type=int, default=16)
    p.add_argument("--warmup-ratio", type=float, default=0.03)
    p.add_argument("--weight-decay", type=float, default=0.0)
    p.add_argument("--max-grad-norm", type=float, default=1.0)
    p.add_argument("--lr-scheduler-type", default="cosine")

    # Optimizer
    p.add_argument("--adam-beta1", type=float, default=0.9)
    p.add_argument("--adam-beta2", type=float, default=0.999)

    # Precision (mutex enforced at runtime so YAML can flip either way).
    p.add_argument("--bf16", action=argparse.BooleanOptionalAction, default=False, help="Use bfloat16.")
    p.add_argument("--fp16", action=argparse.BooleanOptionalAction, default=False, help="Use float16.")

    # LoRA
    p.add_argument("--use-lora", action=argparse.BooleanOptionalAction, default=False,
                   help="Train with PEFT LoRA adapters (else full fine-tune).")
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--lora-dropout", type=float, default=0.05)
    p.add_argument(
        "--target-modules",
        nargs="+",
        default=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        help="LoRA target module names.",
    )

    # Memory / logging / misc
    p.add_argument("--gradient-checkpointing", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--logging-steps", type=int, default=10)
    p.add_argument("--save-steps", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--report-to", default="none", help='HF Trainer `report_to` (e.g. "wandb").')
    return p


def parse_args() -> argparse.Namespace:
    # Pre-scan for --config so we can layer YAML keys under CLI flags.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default=None, type=Path)
    pre_args, _ = pre.parse_known_args()

    yaml_defaults: dict = {}
    if pre_args.config is not None:
        if not pre_args.config.exists():
            raise SystemExit(f"--config file does not exist: {pre_args.config}")
        yaml_defaults = load_yaml(pre_args.config) or {}
        # Coerce types argparse would otherwise convert (Path-valued keys).
        for k in ("train_file", "output_dir"):
            if isinstance(yaml_defaults.get(k), str):
                yaml_defaults[k] = Path(yaml_defaults[k])

    parser = _build_parser()
    # Layer YAML over the built-in defaults. CLI flags override both.
    unknown = set(yaml_defaults) - {a.dest for a in parser._actions}
    if unknown:
        raise SystemExit(
            f"Unknown keys in {pre_args.config}: {sorted(unknown)}. "
            "YAML keys must match argparse `dest` names (use underscores, not hyphens)."
        )
    parser.set_defaults(**yaml_defaults)
    return parser.parse_args()


def _set_seed(seed: int) -> None:
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def _require(args: argparse.Namespace) -> None:
    missing = [n for n in ("model_name_or_path", "train_file", "output_dir")
               if getattr(args, n) in (None, "")]
    if missing:
        raise SystemExit(
            f"Missing required values: {missing}. Pass them on the CLI or in --config."
        )
    if args.bf16 and args.fp16:
        raise SystemExit("--bf16 and --fp16 are mutually exclusive.")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()
    _require(args)

    # Imports are deferred so --help works without torch/trl installed.
    from datasets import load_dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    if not Path(args.train_file).exists():
        logger.error("Train file does not exist: %s", args.train_file)
        return 2

    _set_seed(args.seed)
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    logger.info("Loading tokenizer: %s", args.model_name_or_path)
    tokenizer = AutoTokenizer.from_pretrained(args.model_name_or_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    logger.info("Loading model: %s", args.model_name_or_path)
    model_kwargs: dict = {"trust_remote_code": True}
    if args.bf16:
        import torch

        model_kwargs["torch_dtype"] = torch.bfloat16
    elif args.fp16:
        import torch

        model_kwargs["torch_dtype"] = torch.float16
    model = AutoModelForCausalLM.from_pretrained(args.model_name_or_path, **model_kwargs)

    peft_config = None
    if args.use_lora:
        from peft import LoraConfig

        peft_config = LoraConfig(
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=list(args.target_modules),
        )
        logger.info(
            "LoRA: r=%d alpha=%d dropout=%.3f target_modules=%s",
            args.lora_r, args.lora_alpha, args.lora_dropout, args.target_modules,
        )
    else:
        logger.info("Full fine-tuning (no LoRA).")

    logger.info("Loading dataset: %s", args.train_file)
    raw = load_dataset("json", data_files=str(args.train_file), split="train")
    if "messages" not in raw.column_names:
        logger.error("Train file must contain a `messages` field per record.")
        return 2

    sft_config = SFTConfig(
        output_dir=str(args.output_dir),
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        num_train_epochs=args.num_train_epochs,
        max_steps=args.max_steps,
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        weight_decay=args.weight_decay,
        max_grad_norm=args.max_grad_norm,
        lr_scheduler_type=args.lr_scheduler_type,
        adam_beta1=args.adam_beta1,
        adam_beta2=args.adam_beta2,
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        save_strategy="steps",
        bf16=args.bf16,
        fp16=args.fp16,
        gradient_checkpointing=args.gradient_checkpointing,
        max_seq_length=args.max_seq_length,
        seed=args.seed,
        report_to=args.report_to,
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=raw,
        processing_class=tokenizer,
        peft_config=peft_config,
    )

    if args.max_steps and args.max_steps > 0:
        logger.info(
            "Starting training: max_steps=%d bs=%d ga=%d lr=%.2e scheduler=%s warmup_ratio=%.3f wd=%.3f gc=%.3f",
            args.max_steps, args.per_device_train_batch_size,
            args.gradient_accumulation_steps, args.learning_rate,
            args.lr_scheduler_type, args.warmup_ratio, args.weight_decay, args.max_grad_norm,
        )
    else:
        logger.info(
            "Starting training: epochs=%.2f bs=%d ga=%d lr=%.2e scheduler=%s warmup_ratio=%.3f wd=%.3f gc=%.3f",
            args.num_train_epochs, args.per_device_train_batch_size,
            args.gradient_accumulation_steps, args.learning_rate,
            args.lr_scheduler_type, args.warmup_ratio, args.weight_decay, args.max_grad_norm,
        )
    trainer.train()

    logger.info("Saving final model/adapter to %s", args.output_dir)
    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))

    metadata = {
        "model_name_or_path": args.model_name_or_path,
        "train_file": str(args.train_file),
        "config_file": str(args.config) if args.config else None,
        "use_lora": args.use_lora,
        "lora_r": args.lora_r if args.use_lora else None,
        "lora_alpha": args.lora_alpha if args.use_lora else None,
        "lora_dropout": args.lora_dropout if args.use_lora else None,
        "target_modules": list(args.target_modules) if args.use_lora else None,
        "max_seq_length": args.max_seq_length,
        "learning_rate": args.learning_rate,
        "num_train_epochs": args.num_train_epochs,
        "max_steps": args.max_steps,
        "per_device_train_batch_size": args.per_device_train_batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "warmup_ratio": args.warmup_ratio,
        "weight_decay": args.weight_decay,
        "max_grad_norm": args.max_grad_norm,
        "lr_scheduler_type": args.lr_scheduler_type,
        "adam_beta1": args.adam_beta1,
        "adam_beta2": args.adam_beta2,
        "bf16": args.bf16,
        "fp16": args.fp16,
        "gradient_checkpointing": args.gradient_checkpointing,
        "seed": args.seed,
    }
    (Path(args.output_dir) / "training_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    logger.info("Wrote training_metadata.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
