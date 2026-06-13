#!/usr/bin/env python
"""Generate N *independent* rollouts per seed question (OpenAI-compatible endpoint).

This is the "independent sampling" arm of the **solution-reachability diagnostic**
(official SqueezeEvolve vs. compute-matched independent rollouts). It is a sibling
of ``run_raw_generation.py`` — that script emits exactly ONE ``response`` per seed
for the SFT pipeline and is left untouched. This script instead emits a LIST of
``responses`` so a matched-budget *any-of-N* comparison is possible.

Each output record::

    {
        "id": "...",
        "question": "...",
        "answer": "<gold or null>",        # carried through for *offline* grading; unused here
        "responses": ["...", "...", ...],   # n_rollouts independent samples
        "n_rollouts": <int>,
        "model": "...",
        "generation_params": {"temperature": ..., "top_p": ..., "max_tokens": ...,
                              "n_samples": ..., "seed": ...},
        "source": "independent_rollouts"
    }

Design notes:

* Sampling defaults (``temperature=0.7``, ``top_p=0.95``, ``max_tokens=8192``)
  deliberately match ``configs/squeeze_evolve_generation.yaml`` so the only
  difference between arms is *evolution vs. independent draws*. Override per run.
* For a true compute-matched diagnostic, set ``--n-samples`` to SqueezeEvolve's
  per-problem rollout budget ``N_i`` (see ``scripts/se_budget.py`` — that budget
  is currently UNKNOWN until a real SqueezeEvolve smoke run is inspected).
* Resume is **whole-problem**: ids already present in the output are skipped.
  Topping up a half-finished problem is intentionally unsupported — rerun that
  id with ``--overwrite`` if you need a different N.

This script NEVER grades and never imports the answer checker. It only calls the
model when actually run against a live endpoint; ``--help`` and unit tests touch
no network.
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

logger = logging.getLogger("run_independent_rollouts")


def build_record(
    *,
    sid: str,
    question: str,
    answer: str | None,
    responses: list[str],
    model: str,
    generation_params: dict,
) -> dict:
    """Assemble one independent-rollouts output record (pure; unit-tested)."""
    return {
        "id": sid,
        "question": question,
        "answer": answer,
        "responses": list(responses),
        "n_rollouts": len(responses),
        "model": model,
        "generation_params": dict(generation_params),
        "source": "independent_rollouts",
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path, help="Seed JSONL (id, question, answer?).")
    p.add_argument("--output", required=True, type=Path, help="Output JSONL (one record per problem).")
    p.add_argument("--model", required=True, help="Model name (e.g. Qwen/Qwen3-4B-Thinking-2507).")
    p.add_argument("--base-url", default=None, help="OpenAI-compatible base URL (e.g. http://localhost:8000/v1).")
    p.add_argument("--api-key", default="EMPTY", help="API key. Use 'EMPTY' for vLLM.")

    p.add_argument("--n-samples", type=int, default=1,
                   help="Independent rollouts per problem (N). Match SqueezeEvolve's per-problem budget.")
    p.add_argument("--temperature", type=float, default=0.7, help="Match SqueezeEvolve (0.7), not raw-gen's 0.6.")
    p.add_argument("--top-p", type=float, default=0.95)
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument("--seed", type=int, default=None,
                   help="Base RNG seed; sample i uses seed+i for reproducible-but-distinct draws.")

    p.add_argument("--prompt-template", default=DEFAULT_MATH_PROMPT, help="Override the prompt template.")
    p.add_argument("--system-prompt", default=None, help="Optional system message.")
    p.add_argument("--limit", type=int, default=None, help="Process at most N seeds.")
    p.add_argument("--overwrite", action="store_true", help="Truncate the output file before writing.")
    p.add_argument("--continue-on-error", action="store_true",
                   help="On a generation failure, skip the whole problem instead of aborting.")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    if args.n_samples < 1:
        logger.error("--n-samples must be >= 1 (got %d).", args.n_samples)
        return 2
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

    seeds = list(iter_jsonl(args.input))
    if args.limit is not None:
        seeds = seeds[: args.limit]

    generation_params = {
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
        "n_samples": args.n_samples,
    }
    if args.seed is not None:
        generation_params["seed"] = args.seed

    n_done = 0
    n_skipped = 0
    n_failed = 0
    for seed in tqdm(seeds, desc="independent-rollouts"):
        sid = str(seed.get("id", ""))
        question = seed.get("question")
        if not sid or not isinstance(question, str):
            logger.warning("Skipping malformed seed: %r", seed)
            n_skipped += 1
            continue
        if sid in already_done:
            n_skipped += 1
            continue

        answer = seed.get("answer")
        answer = str(answer) if answer is not None else None

        user_msg = build_math_user_message(question, template=args.prompt_template)
        messages: list[dict[str, str]] = []
        if args.system_prompt:
            messages.append({"role": "system", "content": args.system_prompt})
        messages.append({"role": "user", "content": user_msg})

        responses: list[str] = []
        failed = False
        for i in range(args.n_samples):
            params = GenerationParams(
                temperature=args.temperature,
                top_p=args.top_p,
                max_tokens=args.max_tokens,
                seed=(args.seed + i) if args.seed is not None else None,
            )
            try:
                responses.append(client.chat(messages, params))
            except Exception as e:  # noqa: BLE001
                failed = True
                msg = f"Generation failed for id={sid} sample {i + 1}/{args.n_samples}: {e}"
                if args.continue_on_error:
                    logger.warning("%s — skipping this problem.", msg)
                    break
                logger.error("%s", msg)
                return 1

        # Skip the whole problem on partial failure so we never write an
        # under-budget record that would silently break compute-matching.
        if failed:
            n_failed += 1
            continue

        record = build_record(
            sid=sid, question=question, answer=answer, responses=responses,
            model=args.model, generation_params=generation_params,
        )
        append_jsonl(args.output, record)
        n_done += 1

    logger.info("Done. problems=%d skipped=%d failed=%d (n_samples=%d) -> %s",
                n_done, n_skipped, n_failed, args.n_samples, args.output)
    logger.info("No grading performed — score offline with scripts/eval_reachability.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
