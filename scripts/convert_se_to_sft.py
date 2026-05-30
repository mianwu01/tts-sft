#!/usr/bin/env python
"""Convert Squeeze-Evolve outputs into chat-format SFT JSONL.

Primary input: the JSONL produced by ``scripts/run_squeeze_evolve.py``,
one record per seed problem:

    {
        "id": "...",
        "question": "...",
        "final_response": "...",          # chosen evolved solution
        "candidates": ["...", ...],        # full final population
        "source": "squeeze_evolve",
        "model": "...",
        ...
    }

Also accepts a raw Squeeze-Evolve orchestrator JSON (the file
``squeeze-evolve-client --output ...`` writes — single JSON object with
top-level ``problems`` list); pass ``--input-format auto`` (default) or
``--input-format raw_json`` explicitly.

Question key fallback order: ``question`` → ``problem`` → ``input`` →
``prompt`` → ``orig_prompt``.

Response key fallback order: ``final_response`` → ``final_solution`` →
``evolved_solution`` → ``response`` → ``answer`` → ``output`` →
``result.final_response`` → ``result.final_solution``. Dotted paths walk
nested dicts. Override with ``--response-key``.

If neither a string response nor a non-empty ``candidates`` list is
present, the example is skipped with a warning.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterable

from tqdm import tqdm

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from tts_sft.io_utils import iter_jsonl, write_jsonl  # noqa: E402
from tts_sft.prompts import DEFAULT_MATH_PROMPT  # noqa: E402
from tts_sft.sft_formatting import build_sft_example  # noqa: E402

logger = logging.getLogger("convert_se_to_sft")

DEFAULT_RESPONSE_KEYS = [
    "final_response",
    "final_solution",
    "evolved_solution",
    "response",
    "answer",
    "output",
    "result.final_response",
    "result.final_solution",
]

DEFAULT_QUESTION_KEYS = ["question", "problem", "input", "prompt", "orig_prompt"]


def _get_dotted(d: Any, key: str) -> Any:
    cur: Any = d
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _first_string(d: dict, keys: list[str]) -> str | None:
    for k in keys:
        v = _get_dotted(d, k)
        if isinstance(v, str) and v.strip():
            return v
    return None


def _detect_format(input_path: Path) -> str:
    """Heuristic: a JSON file whose top-level is `{run_id, problems: [...]}`
    is the raw orchestrator output; anything else is treated as JSONL."""
    suffix = input_path.suffix.lower()
    if suffix == ".json":
        try:
            with input_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except json.JSONDecodeError:
            return "jsonl"
        if isinstance(payload, dict) and isinstance(payload.get("problems"), list):
            return "raw_json"
        if isinstance(payload, list):
            return "json_array"
    return "jsonl"


def _iter_records(input_path: Path, fmt: str) -> Iterable[dict]:
    if fmt == "raw_json":
        with input_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        for p in payload.get("problems", []):
            yield p
        return
    if fmt == "json_array":
        with input_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        for r in payload:
            yield r
        return
    # default: jsonl
    yield from iter_jsonl(input_path)


def _extract_response(
    rec: dict,
    response_keys: list[str],
    candidate_strategy: str,
    candidate_index: int | None,
) -> str | None:
    """Pull the final evolved solution out of a single record."""
    # 1. Explicit response field (covers both our wrapper output and
    #    common fork schemas).
    direct = _first_string(rec, response_keys)
    if direct is not None:
        return direct

    # 2. Fall back to the candidates list (raw orchestrator output).
    candidates = rec.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None
    if candidate_index is not None:
        if 0 <= candidate_index < len(candidates):
            c = candidates[candidate_index]
            return c if isinstance(c, str) and c.strip() else None
        return None
    if candidate_strategy == "first":
        c = candidates[0]
    elif candidate_strategy == "last":
        c = candidates[-1]
    elif candidate_strategy == "longest":
        c = max((s for s in candidates if isinstance(s, str)), key=len, default=None)
    else:
        c = candidates[0]
    return c if isinstance(c, str) and c.strip() else None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path,
                   help="Squeeze-Evolve output (.jsonl from our wrapper, or .json raw orchestrator dump).")
    p.add_argument("--output", required=True, type=Path, help="SFT JSONL output.")
    p.add_argument("--input-format", choices=["auto", "jsonl", "raw_json", "json_array"],
                   default="auto", help="Override input-format detection.")
    p.add_argument("--response-key", default=None,
                   help="Explicit response key. Supports dotted paths (e.g. result.final_response).")
    p.add_argument("--question-key", default=None,
                   help="Explicit question key. Supports dotted paths.")
    p.add_argument("--id-key", default="id", help="Field used as the example id.")
    p.add_argument("--candidate-strategy", choices=["first", "last", "longest"],
                   default="first",
                   help="When no direct response field is found, pick from `candidates` this way.")
    p.add_argument("--candidate-index", type=int, default=None,
                   help="Override --candidate-strategy with an explicit index into `candidates`.")
    p.add_argument("--prompt-template", default=DEFAULT_MATH_PROMPT)
    p.add_argument("--source-tag", default="squeeze_evolve_sft")
    p.add_argument("--min-response-chars", type=int, default=1)
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    if not args.input.exists():
        logger.error("Input file does not exist: %s", args.input)
        return 2

    fmt = args.input_format if args.input_format != "auto" else _detect_format(args.input)
    logger.info("Reading %s as %s", args.input, fmt)

    response_keys = [args.response_key] if args.response_key else DEFAULT_RESPONSE_KEYS
    question_keys = [args.question_key] if args.question_key else DEFAULT_QUESTION_KEYS

    out_records: list[dict] = []
    n_skipped_no_response = 0
    n_skipped_no_question = 0
    n_skipped_short = 0

    records = list(_iter_records(args.input, fmt))
    for idx, r in enumerate(tqdm(records, desc="convert-se")):
        raw_id = _get_dotted(r, args.id_key)
        ex_id = str(raw_id) if raw_id is not None else f"se_{idx:06d}"

        question = _first_string(r, question_keys)
        if question is None:
            logger.warning("id=%s: no question field found in %s", ex_id, question_keys)
            n_skipped_no_question += 1
            continue

        response = _extract_response(
            r, response_keys, args.candidate_strategy, args.candidate_index,
        )
        if response is None:
            logger.warning(
                "id=%s: no response (tried keys %s + candidates list)", ex_id, response_keys,
            )
            n_skipped_no_response += 1
            continue

        if len(response.strip()) < args.min_response_chars:
            n_skipped_short += 1
            continue

        out_records.append(
            build_sft_example(
                example_id=ex_id,
                question=question,
                response=response,
                source=args.source_tag,
                prompt_template=args.prompt_template,
            )
        )

    n = write_jsonl(args.output, out_records)
    logger.info(
        "Wrote %d SFT examples to %s (skipped: no-response=%d no-question=%d short=%d).",
        n, args.output, n_skipped_no_response, n_skipped_no_question, n_skipped_short,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
