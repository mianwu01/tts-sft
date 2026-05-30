#!/usr/bin/env python
"""Evaluate a model on math problems via exact-match on extracted final answers.

Two backends:

A. Local HuggingFace model + optional PEFT adapter (default).
B. OpenAI-compatible endpoint (e.g. local vLLM) via --use-vllm-server.

Reports total / correct / accuracy and writes a per-example JSONL log.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from tqdm import tqdm

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from tts_sft.answer_extraction import (  # noqa: E402
    extract_final_answer,
    is_exact_match,
    normalize_math_answer,
)
from tts_sft.io_utils import append_jsonl, iter_jsonl, read_existing_ids  # noqa: E402
from tts_sft.prompts import DEFAULT_MATH_PROMPT, build_math_user_message  # noqa: E402

logger = logging.getLogger("eval_math")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--eval-file", required=True, type=Path, help="Evaluation JSONL with id/question/answer.")
    p.add_argument("--model-name-or-path", required=True)
    p.add_argument("--adapter-path", type=Path, default=None, help="Optional PEFT adapter directory.")
    p.add_argument("--output", required=True, type=Path, help="Per-example JSONL output.")

    p.add_argument("--use-vllm-server", action="store_true",
                   help="Use an OpenAI-compatible HTTP server instead of loading locally.")
    p.add_argument("--base-url", default=None, help="OpenAI-compatible base URL (with --use-vllm-server).")
    p.add_argument("--api-key", default="EMPTY")

    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--top-p", type=float, default=1.0)
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument("--seed", type=int, default=0)

    p.add_argument("--prompt-template", default=DEFAULT_MATH_PROMPT)
    p.add_argument("--system-prompt", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--overwrite", action="store_true", help="Truncate the output file before writing.")
    p.add_argument("--dtype", default="bfloat16", choices=["bfloat16", "float16", "float32"])
    return p.parse_args()


def _generate_via_server(args, examples):
    from tts_sft.openai_client import GenerationParams, OpenAIChatClient

    client = OpenAIChatClient(model=args.model_name_or_path, base_url=args.base_url, api_key=args.api_key)
    params = GenerationParams(
        temperature=args.temperature,
        top_p=args.top_p,
        max_tokens=args.max_tokens,
        seed=args.seed if args.seed else None,
    )
    for ex in examples:
        messages: list[dict[str, str]] = []
        if args.system_prompt:
            messages.append({"role": "system", "content": args.system_prompt})
        messages.append({"role": "user", "content": build_math_user_message(ex["question"], args.prompt_template)})
        text = client.chat(messages, params)
        yield ex, text


def _generate_locally(args, examples):
    from tts_sft.model_loading import generate_text, load_model_for_inference, load_tokenizer

    tokenizer = load_tokenizer(args.model_name_or_path)
    model = load_model_for_inference(
        args.model_name_or_path,
        adapter_path=args.adapter_path,
        dtype=args.dtype,
    )
    for ex in examples:
        messages: list[dict[str, str]] = []
        if args.system_prompt:
            messages.append({"role": "system", "content": args.system_prompt})
        messages.append({"role": "user", "content": build_math_user_message(ex["question"], args.prompt_template)})
        text = generate_text(
            model,
            tokenizer,
            messages,
            temperature=args.temperature,
            top_p=args.top_p,
            max_new_tokens=args.max_tokens,
            do_sample=args.temperature > 0.0,
        )
        yield ex, text


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    if not args.eval_file.exists():
        logger.error("Eval file does not exist: %s", args.eval_file)
        return 2

    if args.use_vllm_server and args.adapter_path is not None:
        logger.warning(
            "--adapter-path is ignored with --use-vllm-server; the server must "
            "already be serving the adapted model."
        )

    if args.overwrite and args.output.exists():
        args.output.unlink()

    already_done = read_existing_ids(args.output)
    if already_done:
        logger.info("Resuming: %d ids already evaluated in %s", len(already_done), args.output)

    examples = []
    for r in iter_jsonl(args.eval_file):
        rid = str(r.get("id", ""))
        question = r.get("question")
        gold = r.get("answer")
        if not rid or not isinstance(question, str) or gold is None:
            logger.warning("Skipping malformed eval record: %r", r)
            continue
        if rid in already_done:
            continue
        examples.append({"id": rid, "question": question, "answer": str(gold)})
    if args.limit is not None:
        examples = examples[: args.limit]

    gen = _generate_via_server(args, examples) if args.use_vllm_server else _generate_locally(args, examples)

    model_tag = args.model_name_or_path
    if args.adapter_path is not None:
        model_tag = f"{model_tag}+{args.adapter_path}"

    n_correct = 0
    n_total = 0
    for ex, response in tqdm(gen, total=len(examples), desc="eval"):
        pred = extract_final_answer(response)
        gold = ex["answer"]
        correct = is_exact_match(pred, gold)
        record = {
            "id": ex["id"],
            "question": ex["question"],
            "gold": gold,
            "prediction": normalize_math_answer(pred) if pred is not None else None,
            "raw_prediction": pred,
            "correct": correct,
            "response": response,
            "model": model_tag,
        }
        append_jsonl(args.output, record)
        n_total += 1
        if correct:
            n_correct += 1

    # Aggregate over the whole output file (covers resumed runs too).
    total = 0
    correct = 0
    for r in iter_jsonl(args.output):
        total += 1
        if r.get("correct"):
            correct += 1
    acc = correct / total if total else 0.0
    logger.info("This run: %d/%d (%.2f%%) correct.", n_correct, n_total, 100.0 * n_correct / max(n_total, 1))
    logger.info("Cumulative: total=%d correct=%d accuracy=%.4f", total, correct, acc)
    print(f"total={total} correct={correct} accuracy={acc:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
