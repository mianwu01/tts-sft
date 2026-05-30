#!/usr/bin/env python
"""Convert our chat-format SFT JSONL into a LLaMA-Factory dataset file.

Our input format (one record per line):

    {
        "id": "...",
        "messages": [
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."}
        ],
        "source": "..."
    }

ShareGPT output (a single JSON array):

    [
      {
        "conversations": [
          {"from": "human", "value": "..."},
          {"from": "gpt", "value": "..."}
        ],
        "id": "...",
        "source": "..."
      }
    ]

The assistant turn is copied verbatim — ``<think>...</think>`` and
``\\boxed{}`` are kept as-is. Examples without exactly one user message
followed by one assistant message are skipped with a warning.

Register the output file in LLaMA-Factory's ``data/dataset_info.json``
using the schema in ``configs/llamafactory/dataset_info_example.json``.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from tts_sft.io_utils import iter_jsonl  # noqa: E402

logger = logging.getLogger("export_llamafactory_data")

SUPPORTED_FORMATS = ("sharegpt",)


def _validate_messages(messages: Any) -> tuple[str, str] | None:
    """Return (user_text, assistant_text) iff messages is exactly [user, assistant].

    Returns None for any malformed shape so the caller can warn + skip.
    """
    if not isinstance(messages, list) or len(messages) != 2:
        return None
    first, second = messages
    if not (isinstance(first, dict) and isinstance(second, dict)):
        return None
    if first.get("role") != "user" or second.get("role") != "assistant":
        return None
    u = first.get("content")
    a = second.get("content")
    if not isinstance(u, str) or not isinstance(a, str):
        return None
    if not u.strip() or not a.strip():
        return None
    return u, a


def _to_sharegpt_record(rec: dict, idx: int) -> dict | None:
    pair = _validate_messages(rec.get("messages"))
    if pair is None:
        return None
    user_text, assistant_text = pair
    out: dict[str, Any] = {
        "conversations": [
            {"from": "human", "value": user_text},
            {"from": "gpt", "value": assistant_text},
        ],
    }
    if "id" in rec:
        out["id"] = str(rec["id"])
    else:
        out["id"] = f"ex_{idx:06d}"
    if "source" in rec and rec["source"] is not None:
        out["source"] = rec["source"]
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path, help="Chat-format SFT JSONL.")
    p.add_argument("--output", required=True, type=Path, help="LLaMA-Factory dataset file (single JSON array).")
    p.add_argument("--format", choices=SUPPORTED_FORMATS, default="sharegpt",
                   help="Output schema. Only `sharegpt` is supported in v1.")
    p.add_argument("--limit", type=int, default=None, help="Keep only the first N valid examples.")
    p.add_argument("--overwrite", action="store_true", help="Replace --output if it exists.")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    if not args.input.exists():
        logger.error("Input file does not exist: %s", args.input)
        return 2

    if args.output.exists() and not args.overwrite:
        logger.error("Output file already exists: %s (pass --overwrite to replace)", args.output)
        return 2

    n_in = 0
    n_out = 0
    n_skipped = 0
    converted: list[dict] = []
    for idx, rec in enumerate(iter_jsonl(args.input)):
        n_in += 1
        sgrec = _to_sharegpt_record(rec, idx)
        if sgrec is None:
            n_skipped += 1
            logger.warning(
                "id=%s: malformed messages (need [user, assistant] pair); skipping.",
                rec.get("id", f"ex_{idx:06d}"),
            )
            continue
        converted.append(sgrec)
        n_out += 1
        if args.limit is not None and n_out >= args.limit:
            break

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(converted, f, ensure_ascii=False, indent=2)

    logger.info(
        "Done. format=%s input=%d converted=%d skipped=%d -> %s",
        args.format, n_in, n_out, n_skipped, args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
