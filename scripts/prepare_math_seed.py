#!/usr/bin/env python
"""Normalize an arbitrary math dataset into the canonical seed JSONL format.

Canonical record format:

    {"id": "000001", "question": "...", "answer": "optional"}

Input may be JSON or JSONL. Field names for the question and answer can be
overridden with --question-field / --answer-field. Ids are assigned by
position if --id-field is missing or not found.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Make ``src`` layout importable when the script is run directly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from tts_sft.io_utils import write_jsonl  # noqa: E402

logger = logging.getLogger("prepare_math_seed")


def _iter_input(path: Path):
    """Yield raw records from either a JSON array or a JSONL file."""
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("["):
        for r in json.loads(text):
            yield r
        return
    for line_num, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError as e:
            raise SystemExit(f"{path}:{line_num}: {e.msg}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path, help="Input JSON or JSONL file.")
    p.add_argument("--output", required=True, type=Path, help="Output JSONL file (canonical seed format).")
    p.add_argument("--question-field", default="question", help="Source field for the question text.")
    p.add_argument("--answer-field", default="answer", help="Source field for the answer (may be missing).")
    p.add_argument("--id-field", default="id", help="Source field for the id; positional if absent.")
    p.add_argument("--id-prefix", default="", help="Optional prefix prepended to generated ids.")
    p.add_argument("--limit", type=int, default=None, help="If set, keep only the first N examples.")
    p.add_argument("--require-answer", action="store_true", help="Skip examples missing an answer.")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    if not args.input.exists():
        logger.error("Input file does not exist: %s", args.input)
        return 2

    out_records: list[dict] = []
    kept = 0
    skipped = 0
    for idx, raw in enumerate(_iter_input(args.input)):
        if args.limit is not None and kept >= args.limit:
            break
        q = raw.get(args.question_field)
        if not isinstance(q, str) or not q.strip():
            skipped += 1
            continue
        ans = raw.get(args.answer_field)
        if args.require_answer and (ans is None or str(ans).strip() == ""):
            skipped += 1
            continue
        raw_id = raw.get(args.id_field)
        ex_id = str(raw_id) if raw_id is not None else f"{args.id_prefix}{idx:06d}"
        rec: dict = {"id": ex_id, "question": q.strip()}
        if ans is not None:
            rec["answer"] = str(ans).strip()
        out_records.append(rec)
        kept += 1

    n = write_jsonl(args.output, out_records)
    logger.info("Wrote %d records to %s (skipped %d).", n, args.output, skipped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
