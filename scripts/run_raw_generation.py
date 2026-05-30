#!/usr/bin/env python
"""Generate one raw model response per seed question via an OpenAI-compatible endpoint.

Each output record:

    {
        "id": "...",
        "question": "...",
        "response": "...",
        "source": "raw_generation",
        "model": "...",
        "metadata": {"temperature": ..., "top_p": ..., "max_tokens": ...}
    }

Existing ids in the output file are skipped (resume). Pass --overwrite to
start fresh.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from tqdm import tqdm

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from tts_sft.io_utils import append_jsonl, iter_jsonl, read_existing_ids  # noqa: E402
from tts_sft.openai_client import GenerationParams, OpenAIChatClient  # noqa: E402
from tts_sft.prompts import DEFAULT_MATH_PROMPT, build_math_user_message  # noqa: E402

logger = logging.getLogger("run_raw_generation")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path, help="Seed JSONL.")
    p.add_argument("--output", required=True, type=Path, help="Output JSONL.")
    p.add_argument("--model", required=True, help="Model name (e.g. Qwen/Qwen3-4B-Thinking-2507).")
    p.add_argument("--base-url", default=None, help="OpenAI-compatible base URL (e.g. http://localhost:8000/v1).")
    p.add_argument("--api-key", default="EMPTY", help="API key. Use 'EMPTY' for vLLM.")
    p.add_argument("--temperature", type=float, default=0.6)
    p.add_argument("--top-p", type=float, default=0.95)
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--prompt-template", default=DEFAULT_MATH_PROMPT, help="Override the prompt template.")
    p.add_argument("--system-prompt", default=None, help="Optional system message.")
    p.add_argument("--limit", type=int, default=None, help="Process at most N seeds.")
    p.add_argument("--overwrite", action="store_true", help="Truncate the output file before writing.")
    p.add_argument("--continue-on-error", action="store_true", help="Log and skip failures instead of aborting.")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    if not args.input.exists():
        logger.error("Input file does not exist: %s", args.input)
        return 2

    if args.overwrite and args.output.exists():
        logger.info("Overwrite requested — removing %s", args.output)
        args.output.unlink()

    already_done = read_existing_ids(args.output)
    if already_done:
        logger.info("Resuming: %d ids already present in %s", len(already_done), args.output)

    client = OpenAIChatClient(model=args.model, base_url=args.base_url, api_key=args.api_key)
    params = GenerationParams(
        temperature=args.temperature,
        top_p=args.top_p,
        max_tokens=args.max_tokens,
        seed=args.seed,
    )

    seeds = list(iter_jsonl(args.input))
    if args.limit is not None:
        seeds = seeds[: args.limit]

    metadata = {
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
    }
    if args.seed is not None:
        metadata["seed"] = args.seed

    n_done = 0
    n_skipped = 0
    n_failed = 0
    for seed in tqdm(seeds, desc="raw-generation"):
        sid = str(seed.get("id", ""))
        question = seed.get("question")
        if not sid or not isinstance(question, str):
            logger.warning("Skipping malformed seed: %r", seed)
            n_skipped += 1
            continue
        if sid in already_done:
            n_skipped += 1
            continue

        user_msg = build_math_user_message(question, template=args.prompt_template)
        messages: list[dict[str, str]] = []
        if args.system_prompt:
            messages.append({"role": "system", "content": args.system_prompt})
        messages.append({"role": "user", "content": user_msg})

        try:
            response_text = client.chat(messages, params)
        except Exception as e:  # noqa: BLE001
            n_failed += 1
            if args.continue_on_error:
                logger.warning("Generation failed for id=%s: %s", sid, e)
                continue
            logger.error("Generation failed for id=%s: %s", sid, e)
            return 1

        record = {
            "id": sid,
            "question": question,
            "response": response_text,
            "source": "raw_generation",
            "model": args.model,
            "metadata": metadata,
        }
        append_jsonl(args.output, record)
        n_done += 1

    logger.info("Done. generated=%d skipped=%d failed=%d -> %s", n_done, n_skipped, n_failed, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
