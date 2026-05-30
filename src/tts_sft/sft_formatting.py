"""Helpers for building supervised fine-tuning chat examples."""
from __future__ import annotations

from typing import Any

from tts_sft.prompts import DEFAULT_MATH_PROMPT, build_math_user_message


def build_sft_example(
    *,
    example_id: str,
    question: str,
    response: str,
    source: str,
    prompt_template: str = DEFAULT_MATH_PROMPT,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a chat-format SFT record from a (question, response) pair.

    The user turn is rendered with the math prompt template; the assistant
    turn is the model's response, kept verbatim (including any
    ``<think>...</think>`` segments).
    """
    user_msg = build_math_user_message(question, template=prompt_template)
    record: dict[str, Any] = {
        "id": example_id,
        "messages": [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": response},
        ],
        "source": source,
    }
    if extra_metadata:
        record["metadata"] = extra_metadata
    return record


def messages_to_text(
    messages: list[dict[str, str]],
    tokenizer: Any,
) -> str:
    """Render chat messages with the tokenizer's chat template.

    Uses ``add_generation_prompt=False`` since SFT examples include the
    assistant turn directly.
    """
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False,
    )
