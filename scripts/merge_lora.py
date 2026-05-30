#!/usr/bin/env python
"""Merge a PEFT LoRA adapter into its base model and save the result.

Useful when you want to serve a fine-tuned model from a vanilla inference
stack (e.g. vLLM) that doesn't load PEFT adapters at request time.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

logger = logging.getLogger("merge_lora")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-model", required=True, help="Base model name or path.")
    p.add_argument("--adapter-path", required=True, type=Path, help="Path to the trained LoRA adapter.")
    p.add_argument("--output-dir", required=True, type=Path, help="Where to save the merged model.")
    p.add_argument("--dtype", default="bfloat16", choices=["bfloat16", "float16", "float32"])
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    if not args.adapter_path.exists():
        logger.error("Adapter path does not exist: %s", args.adapter_path)
        return 2

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch_dtype = {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}[args.dtype]

    logger.info("Loading base model: %s", args.base_model)
    base = AutoModelForCausalLM.from_pretrained(
        args.base_model, torch_dtype=torch_dtype, trust_remote_code=True
    )
    logger.info("Loading adapter: %s", args.adapter_path)
    peft_model = PeftModel.from_pretrained(base, str(args.adapter_path))

    logger.info("Merging adapter into base weights.")
    merged = peft_model.merge_and_unload()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Saving merged model to %s", args.output_dir)
    merged.save_pretrained(str(args.output_dir))

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    tokenizer.save_pretrained(str(args.output_dir))
    logger.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
