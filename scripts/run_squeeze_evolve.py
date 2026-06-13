#!/usr/bin/env python
"""Wrapper around the official Squeeze-Evolve CLI (``squeeze-evolve-client``).

Pipeline:

1.  Verify ``--squeeze-evolve-dir`` exists and the ``squeeze-evolve-client``
    console script is callable.
2.  Convert our seed JSONL (``{id, question, answer?}``) into the format
    the orchestrator expects (one JSONL record per problem,
    ``{orig_prompt, gt, question}``).
3.  Load the user's YAML config. If ``--model`` / ``--base-url`` /
    ``--api-key`` are passed, splice them into every entry of ``models:``
    (and ``scoring_model`` if present).
4.  Invoke ``squeeze-evolve-client --config <patched> --input <converted>
    --output <orchestrator-out.json>``.
5.  Normalize the orchestrator's single-JSON output into our project's
    one-record-per-line JSONL format, keeping the original seed ``id`` and
    ``question`` plus the full evolved candidate population.

The wrapper never fabricates outputs. If the CLI is missing or fails, the
script prints manual instructions and exits non-zero.
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from tts_sft.io_utils import iter_jsonl, load_yaml, write_jsonl  # noqa: E402

logger = logging.getLogger("run_squeeze_evolve")


def _print_manual_instructions(se_dir: Path, config: Path, converted_input: Path, raw_output: Path) -> None:
    print(
        "\n=== Manual Squeeze-Evolve instructions ===\n"
        "Could not invoke `squeeze-evolve-client`. Make sure the package is\n"
        "installed:\n\n"
        f"    cd {se_dir}\n"
        "    pip install -e \".[dev]\"\n\n"
        "Then run it by hand (input/output are written by this wrapper):\n\n"
        f"    squeeze-evolve-client \\\n"
        f"        --config {config} \\\n"
        f"        --input {converted_input} \\\n"
        f"        --output {raw_output}\n\n"
        "Finally re-run this wrapper with the same arguments — it will\n"
        f"detect {raw_output} and normalize it to JSONL.\n",
        file=sys.stderr,
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path, help="Seed JSONL (id, question, answer?).")
    p.add_argument("--output", required=True, type=Path,
                   help="Normalized JSONL output (one record per problem).")
    p.add_argument("--config", required=True, type=Path,
                   help="YAML config for squeeze-evolve-client. Override knobs are merged in.")
    p.add_argument("--squeeze-evolve-dir", required=True, type=Path,
                   help="Path to the cloned Squeeze-Evolve repo (for auto-benchmark discovery and as a cwd).")

    p.add_argument("--model", default=None, help="If set, overrides `name` in every config `models:` entry.")
    p.add_argument("--base-url", default=None, help="If set, overrides `base_url` in every config model entry.")
    p.add_argument("--api-key", default=None, help="If set, overrides `api_key` in every config model entry.")

    p.add_argument("--n-problems", type=int, default=None, help="Forwarded to squeeze-evolve-client --n-problems.")
    p.add_argument("--raw-output", type=Path, default=None,
                   help="Where to keep the raw JSON written by squeeze-evolve-client. "
                        "Defaults to <output>.raw.json.")
    p.add_argument("--keep-tmp", action="store_true",
                   help="Don't delete the temp directory holding the patched config and converted input.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the command and exit 0 without invoking squeeze-evolve-client.")
    return p.parse_args()


def _convert_seeds(seed_path: Path, dest_jsonl: Path) -> int:
    """Emit one JSONL record per seed in the format ProblemState accepts."""
    records: list[dict] = []
    for s in iter_jsonl(seed_path):
        q = s.get("question")
        if not isinstance(q, str) or not q.strip():
            logger.warning("Skipping seed without `question`: %r", s)
            continue
        rec: dict = {"orig_prompt": q, "question": q}
        ans = s.get("answer")
        if ans is not None:
            rec["gt"] = str(ans)
        else:
            rec["gt"] = None
        records.append(rec)
    return write_jsonl(dest_jsonl, records)


def _patch_config(
    config_path: Path,
    *,
    model: str | None,
    base_url: str | None,
    api_key: str | None,
) -> dict:
    """Load the YAML config and splice in CLI overrides for model endpoint fields."""
    cfg = load_yaml(config_path)
    if not cfg:
        raise SystemExit(f"Config file is empty or unreadable: {config_path}")

    if "models" not in cfg or not isinstance(cfg["models"], list) or not cfg["models"]:
        raise SystemExit(
            f"Config {config_path} must define a non-empty `models:` list "
            "(see external/squeeze-evolve/README.md)."
        )

    patched = copy.deepcopy(cfg)
    for m in patched["models"]:
        if model is not None:
            m["name"] = model
        if base_url is not None:
            m["base_url"] = base_url
        if api_key is not None:
            m["api_key"] = api_key

    scoring = patched.get("scoring_model")
    if isinstance(scoring, dict):
        if model is not None:
            scoring["name"] = model
        if base_url is not None:
            scoring["base_url"] = base_url
        if api_key is not None:
            scoring["api_key"] = api_key

    return patched


def _write_patched_config(patched: dict, dest_yaml: Path) -> None:
    import yaml

    with dest_yaml.open("w", encoding="utf-8") as f:
        yaml.safe_dump(patched, f, sort_keys=False)


def _preserve_loop_checkpoints(se_dir: Path, patched: dict, output: Path) -> dict | None:
    """Snapshot the official client's per-loop checkpoints next to our output.

    SqueezeEvolve writes one checkpoint per evolutionary loop to
    ``<checkpoint_dir>/<run_name>_loop<t>.json`` (orchestrator.save_checkpoint,
    every loop incl. loop 0). Each holds the FULL ProblemState for that loop:
    every candidate's full response (with ``<think>`` traces), parent groups
    (``candidate_groups``), and per-loop ``routing_details`` (fitness/scores/routes).
    The client's ``--output`` JSON only keeps the FINAL loop, so these checkpoints
    are the ONLY source of per-loop candidate history. They live inside the
    SqueezeEvolve clone and are overwritten by the next run with the same
    ``run_name``, so we copy them into ``<output>.checkpoints/`` to preserve them
    (Harman: "save all candidates from every squeeze evolve loop").

    Returns snapshot metadata for embedding in normalized records, or None on
    error. Never raises — preservation must not break the run.
    """
    try:
        run_name = patched.get("run_name", "default")
        src = Path(patched.get("checkpoint_dir", "./artifacts/checkpoints"))
        if not src.is_absolute():
            src = se_dir / src                      # client runs with cwd=se_dir
        files = sorted(src.glob(f"{run_name}_loop*.json")) if src.is_dir() else []
        if not files:
            logger.warning(
                "No per-loop checkpoints found under %s (pattern '%s_loop*.json'). "
                "Per-loop candidate history will be UNAVAILABLE — verify checkpointing "
                "and run_name after a smoke run.", src, run_name,
            )
            return {"run_name": run_name, "checkpoint_dir": str(src), "n_loop_checkpoints": 0}
        dest = output.parent / (output.name + ".checkpoints")
        dest.mkdir(parents=True, exist_ok=True)
        for f in files:
            shutil.copy2(f, dest / f.name)
        logger.info("Preserved %d per-loop checkpoint(s) -> %s", len(files), dest)
        logger.info(
            "Build the per-loop candidate dataset with:\n"
            "    python scripts/se_loop_candidates.py --checkpoint-dir %s "
            "--se-output %s --output %s.loop_candidates.jsonl",
            dest, output, output,
        )
        return {"run_name": run_name, "checkpoint_dir": str(dest), "n_loop_checkpoints": len(files)}
    except Exception as e:  # noqa: BLE001 - preservation is best-effort
        logger.warning("Could not preserve loop checkpoints: %s", e)
        return None


def _normalize_orchestrator_output(
    seeds: list[dict],
    raw_path: Path,
    out_path: Path,
    model_name: str,
    extra_metadata: dict | None = None,
) -> int:
    """Convert the orchestrator's JSON output back to one JSONL record per seed.

    Each output record:

        {
            "id": "<seed id>",
            "question": "<seed question>",
            "gt": "<gold or null>",
            "final_response": "<chosen candidate>",      # first of the final population
            "candidates": ["<all final candidates>", ...],
            "source": "squeeze_evolve",
            "model": "<model name>",
            "metadata": {"squeeze_evolve_run_id": "...", ...}
        }
    """
    with raw_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    problems = payload.get("problems")
    if not isinstance(problems, list):
        raise SystemExit(
            f"Unexpected Squeeze-Evolve output at {raw_path}: missing top-level `problems` list."
        )

    if len(problems) != len(seeds):
        logger.warning(
            "Seed count (%d) and orchestrator problem count (%d) differ — "
            "matching by position. If you used --n-problems, the wrapper will "
            "only emit the prefix that ran.",
            len(seeds), len(problems),
        )

    run_id = payload.get("run_id")
    n_emitted = 0
    n_skipped = 0
    out_records: list[dict] = []
    for seed, prob in zip(seeds, problems):
        candidates = prob.get("candidates") or []
        if not isinstance(candidates, list) or not candidates:
            logger.warning("id=%s: empty candidates from Squeeze-Evolve; skipping.", seed.get("id"))
            n_skipped += 1
            continue
        # Pick a representative final response. With `update: replace`, every
        # candidate in the final population is a fully-refined solution; index 0
        # is fine. Downstream converters can override.
        final = candidates[0]

        rec = {
            "id": str(seed.get("id", "")),
            "question": seed.get("question"),
            "gt": prob.get("gt"),
            "final_response": final,
            "candidates": candidates,
            "source": "squeeze_evolve",
            "model": model_name,
            "metadata": {
                "squeeze_evolve_run_id": run_id,
                "n_candidates": len(candidates),
                **(extra_metadata or {}),
            },
        }
        out_records.append(rec)
        n_emitted += 1

    n = write_jsonl(out_path, out_records)
    logger.info("Normalized %d records to %s (skipped %d).", n, out_path, n_skipped)
    return n_emitted


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    if not args.input.exists():
        logger.error("Input seed file does not exist: %s", args.input)
        return 2

    se_dir = args.squeeze_evolve_dir
    if not se_dir.exists():
        logger.error("Squeeze-Evolve directory does not exist: %s", se_dir)
        logger.error("Clone it first, e.g.:")
        logger.error(
            "  git clone --recurse-submodules "
            "https://github.com/squeeze-evolve/squeeze-evolve.git %s", se_dir
        )
        return 2

    if not args.config.exists():
        logger.error("Config file does not exist: %s", args.config)
        return 2

    cli_path = shutil.which("squeeze-evolve-client")
    if cli_path is None:
        msg = (
            "`squeeze-evolve-client` not found on PATH. Install Squeeze-Evolve first:\n"
            f"    cd {se_dir} && pip install -e \".[dev]\""
        )
        if args.dry_run:
            logger.warning("%s", msg)
            logger.warning("--dry-run set; continuing with placeholder path `squeeze-evolve-client`.")
            cli_path = "squeeze-evolve-client"
        else:
            logger.error("%s", msg)
            return 3
    else:
        logger.info("Using squeeze-evolve-client at: %s", cli_path)

    seeds = list(iter_jsonl(args.input))
    if not seeds:
        logger.error("Seed file %s is empty.", args.input)
        return 2

    # Resolve to ABSOLUTE: squeeze-evolve-client is invoked with cwd=se_dir, so a *relative*
    # --output would be written inside the SE clone instead of next to our --output (and the
    # existence check below would then fail). args.output stays as-is — it is only used by this
    # process (which runs from the repo root).
    raw_output: Path = (args.raw_output or args.output.with_suffix(args.output.suffix + ".raw.json")).resolve()
    raw_output.parent.mkdir(parents=True, exist_ok=True)

    tmp_dir = Path(tempfile.mkdtemp(prefix="tts_sft_se_"))
    try:
        converted_input = tmp_dir / "se_input.jsonl"
        patched_config = tmp_dir / "patched_config.yaml"

        n_in = _convert_seeds(args.input, converted_input)
        logger.info("Converted %d seeds -> %s", n_in, converted_input)

        patched = _patch_config(
            args.config, model=args.model, base_url=args.base_url, api_key=args.api_key,
        )
        _write_patched_config(patched, patched_config)
        logger.info("Wrote patched config -> %s", patched_config)

        cmd: list[str] = [
            cli_path,
            "--config", str(patched_config),
            "--input", str(converted_input),
            "--output", str(raw_output),
        ]
        if args.n_problems is not None:
            cmd += ["--n-problems", str(args.n_problems)]

        logger.info("Invoking Squeeze-Evolve:")
        logger.info("  %s", " ".join(cmd))
        logger.info("  cwd=%s", se_dir)

        if args.dry_run:
            logger.info("--dry-run set; skipping actual invocation.")
            return 0

        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in [str(se_dir / "src"), env.get("PYTHONPATH", "")] if p
        )

        try:
            proc = subprocess.run(cmd, cwd=str(se_dir), env=env, check=False)
        except FileNotFoundError as e:
            logger.error("Failed to launch squeeze-evolve-client: %s", e)
            _print_manual_instructions(se_dir, patched_config, converted_input, raw_output)
            return 3

        if proc.returncode != 0:
            logger.error("squeeze-evolve-client exited with code %d", proc.returncode)
            _print_manual_instructions(se_dir, patched_config, converted_input, raw_output)
            return proc.returncode

        if not raw_output.exists():
            logger.error("squeeze-evolve-client returned 0 but produced no output at %s", raw_output)
            return 4

        model_name = patched["models"][0]["name"] if patched.get("models") else "unknown"
        ckpt_info = _preserve_loop_checkpoints(se_dir, patched, args.output)
        _normalize_orchestrator_output(seeds, raw_output, args.output, model_name, extra_metadata=ckpt_info)
        return 0
    finally:
        if not args.keep_tmp:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
