#!/usr/bin/env python
"""LoRA (or full) SFT of a causal LM on chat-format JSONL.

Each input record must look like:
    {"id": "...", "messages": [{"role": "user", ...}, {"role": "assistant", ...}], ...}

The full assistant turn (including any ``<think>...</think>`` segments) is
preserved in the training text by default.
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

logger = logging.getLogger("train_sft")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model-name-or-path", required=True)
    p.add_argument("--train-file", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--max-seq-length", type=int, default=8192)
    p.add_argument("--learning-rate", type=float, default=5e-6)
    p.add_argument("--num-train-epochs", type=float, default=1.0)
    p.add_argument("--per-device-train-batch-size", type=int, default=1)
    p.add_argument("--gradient-accumulation-steps", type=int, default=16)

    dtype_group = p.add_mutually_exclusive_group()
    dtype_group.add_argument("--bf16", action="store_true", help="Use bfloat16.")
    dtype_group.add_argument("--fp16", action="store_true", help="Use float16.")

    p.add_argument("--use-lora", action="store_true", help="Train with PEFT LoRA adapters.")
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--lora-dropout", type=float, default=0.05)
    p.add_argument(
        "--target-modules",
        nargs="+",
        default=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        help="LoRA target module names.",
    )
    p.add_argument("--gradient-checkpointing", action="store_true", default=True)
    p.add_argument("--no-gradient-checkpointing", dest="gradient_checkpointing", action="store_false")
    p.add_argument("--logging-steps", type=int, default=10)
    p.add_argument("--save-steps", type=int, default=200)
    p.add_argument("--warmup-ratio", type=float, default=0.03)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--report-to", default="none", help='HF Trainer `report_to` (e.g. "wandb").')
    return p.parse_args()


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


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    # Imports are deferred so --help works without torch/trl installed.
    from datasets import load_dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    if not args.train_file.exists():
        logger.error("Train file does not exist: %s", args.train_file)
        return 2

    _set_seed(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)

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
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
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

    logger.info("Starting training: epochs=%.2f bs=%d ga=%d lr=%.2e",
                args.num_train_epochs, args.per_device_train_batch_size,
                args.gradient_accumulation_steps, args.learning_rate)
    trainer.train()

    logger.info("Saving final model/adapter to %s", args.output_dir)
    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))

    metadata = {
        "model_name_or_path": args.model_name_or_path,
        "train_file": str(args.train_file),
        "use_lora": args.use_lora,
        "lora_r": args.lora_r if args.use_lora else None,
        "lora_alpha": args.lora_alpha if args.use_lora else None,
        "lora_dropout": args.lora_dropout if args.use_lora else None,
        "target_modules": list(args.target_modules) if args.use_lora else None,
        "max_seq_length": args.max_seq_length,
        "learning_rate": args.learning_rate,
        "num_train_epochs": args.num_train_epochs,
        "per_device_train_batch_size": args.per_device_train_batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "bf16": args.bf16,
        "fp16": args.fp16,
        "gradient_checkpointing": args.gradient_checkpointing,
        "seed": args.seed,
    }
    (args.output_dir / "training_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    logger.info("Wrote training_metadata.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
