"""Local HuggingFace model loading with optional PEFT adapter."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_tokenizer(model_name_or_path: str) -> Any:
    """Load a tokenizer; ensure a pad token exists."""
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        model_name_or_path,
        trust_remote_code=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def load_model_for_inference(
    model_name_or_path: str,
    *,
    adapter_path: str | Path | None = None,
    dtype: str = "bfloat16",
    device_map: str | dict[str, Any] = "auto",
) -> Any:
    """Load a causal LM for inference, optionally applying a PEFT adapter."""
    import torch
    from transformers import AutoModelForCausalLM

    torch_dtype = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }.get(dtype, torch.bfloat16)

    model = AutoModelForCausalLM.from_pretrained(
        model_name_or_path,
        torch_dtype=torch_dtype,
        device_map=device_map,
        trust_remote_code=True,
    )

    if adapter_path is not None:
        from peft import PeftModel

        logger.info("Attaching PEFT adapter from %s", adapter_path)
        model = PeftModel.from_pretrained(model, str(adapter_path))

    model.eval()
    return model


def generate_text(
    model: Any,
    tokenizer: Any,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.6,
    top_p: float = 0.95,
    max_new_tokens: int = 8192,
    do_sample: bool = True,
) -> str:
    """Run a single chat-template generation locally and return the new text."""
    import torch

    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            do_sample=do_sample,
            temperature=temperature,
            top_p=top_p,
            max_new_tokens=max_new_tokens,
            pad_token_id=tokenizer.pad_token_id,
        )

    new_tokens = output_ids[0, inputs["input_ids"].shape[1] :]
    return tokenizer.decode(new_tokens, skip_special_tokens=True)
