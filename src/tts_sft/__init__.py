"""tts-sft: data generation, SFT, and evaluation utilities."""

from tts_sft.answer_extraction import (
    extract_boxed_answer,
    extract_final_answer,
    is_exact_match,
    normalize_math_answer,
)
from tts_sft.io_utils import (
    iter_jsonl,
    load_jsonl,
    load_yaml,
    read_existing_ids,
    write_jsonl,
)
from tts_sft.prompts import DEFAULT_MATH_PROMPT, build_math_user_message
from tts_sft.sft_formatting import build_sft_example

__all__ = [
    "DEFAULT_MATH_PROMPT",
    "build_math_user_message",
    "build_sft_example",
    "extract_boxed_answer",
    "extract_final_answer",
    "is_exact_match",
    "iter_jsonl",
    "load_jsonl",
    "load_yaml",
    "normalize_math_answer",
    "read_existing_ids",
    "write_jsonl",
]

__version__ = "0.1.0"
