#!/usr/bin/env python
"""Convert raw self-generated outputs into chat-format SFT JSONL."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from tqdm import tqdm

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from tts_sft.io_utils import iter_jsonl, write_jsonl  # noqa: E402
from tts_sft.prompts import DEFAULT_MATH_PROMPT  # noqa: E402
from tts_sft.sft_formatting import build_sft_example  # noqa: E402

logger = logging.getLogger("convert_raw_to_sft")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path, help="Raw generation JSONL.")
    p.add_argument("--output", required=True, type=Path, help="SFT JSONL output.")
    p.add_argument("--prompt-template", default=DEFAULT_MATH_PROMPT)
    p.add_argument("--source-tag", default="raw_self_sft", help="Value for the `source` field in each record.")
    p.add_argument("--min-response-chars", type=int, default=1,
                   help="Skip examples whose response is shorter than this.")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    if not args.input.exists():
        logger.error("Input file does not exist: %s", args.input)
        return 2

    out_records = []
    n_skipped = 0
    for r in tqdm(list(iter_jsonl(args.input)), desc="convert-raw"):
        rid = str(r.get("id", ""))
        question = r.get("question")
        response = r.get("response")
        if not rid or not isinstance(question, str) or not isinstance(response, str):
            n_skipped += 1
            continue
        if len(response.strip()) < args.min_response_chars:
            n_skipped += 1
            continue
        out_records.append(
            build_sft_example(
                example_id=rid,
                question=question,
                response=response,
                source=args.source_tag,
                prompt_template=args.prompt_template,
            )
        )

    n = write_jsonl(args.output, out_records)
    logger.info("Wrote %d SFT examples to %s (skipped %d).", n, args.output, n_skipped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
