#!/usr/bin/env python
"""Normalize SqueezeEvolve's per-loop candidate history into a flat JSONL dataset.

Harman: "save all the candidates from every squeeze evolve loop ... the full
thinking traces and outputs of the model at every step, and ... which loop they
belong to." This is the parser that produces that dataset (for later
curriculum-style SFT experiments). It does NOT call any model.

WHERE THE DATA COMES FROM (verified against the official source, cloned at
external/squeeze-evolve/):
  * The client's ``--output`` JSON keeps only the FINAL loop's ProblemState
    (orchestrator.run -> ``{run_id, metrics, problems:[final state]}``); with
    ``update: replace`` the per-loop candidates and routing_details are
    overwritten each loop, so they are NOT in that file.
  * Per-loop history lives in the CHECKPOINTS that the client writes every loop:
    ``<checkpoint_dir>/<run_name>_loop<t>.json`` =
    ``{"problems": [ProblemState.__dict__ ...], "metrics": <flat loop metrics>}``.
    ``scripts/run_squeeze_evolve.py`` snapshots these into ``<output>.checkpoints/``.

Each ProblemState (per loop) exposes:
  candidates: list[str]              full model responses (incl. <think> if strip_think=false)
  candidate_groups: list[list[str]]  parent solution TEXTS each candidate was recombined from
  routing_details: dict | None       per-loop: routes, thresholds, group_fitnesses,
                                      group_index_members (parent INDICES), candidate_confidences

NON-FABRICATION CONTRACT: fields the official output does not expose are emitted
as ``null`` with a documented reason — never invented. Notably:
  * loop 0 has no parents/fitness/scores -> parent_ids/fitness/score = null.
  * with ``fitness: diversity`` (our default) per-candidate confidence is not
    computed -> ``score`` = null (``candidate_confidences`` is empty).
  * the exact rendered recombination prompt is not persisted -> ``prompt`` is the
    base question; parent solutions are preserved under ``parent_texts``.
  * per-candidate ``generation_params``/``model`` are not stored per candidate;
    they are filled from ``--config``/``--model`` when given, else null.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from tts_sft.answer_extraction import extract_final_answer  # noqa: E402
from tts_sft.io_utils import iter_jsonl, load_yaml, write_jsonl  # noqa: E402

logger = logging.getLogger("se_loop_candidates")

_LOOP_RE = re.compile(r"_loop(\d+)\.json$")
_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)
# Qwen3-Thinking-2507's chat template auto-prepends "<think>" to the assistant turn, so the
# model's output starts INSIDE the block and emits only the closing "</think>". When no
# opening tag is present, the reasoning is everything up to the first closing tag.
_THINK_CLOSE_RE = re.compile(r"^(.*?)</think>", re.DOTALL)


def loop_index_from_filename(path: Path) -> int | None:
    m = _LOOP_RE.search(path.name)
    return int(m.group(1)) if m else None


def find_checkpoint_files(checkpoint_dir: Path, run_name: str | None = None) -> list[tuple[int, Path]]:
    """Return ``(loop_index, path)`` for checkpoint files, sorted by loop index."""
    pattern = f"{run_name}_loop*.json" if run_name else "*_loop*.json"
    out: list[tuple[int, Path]] = []
    for p in checkpoint_dir.glob(pattern):
        idx = loop_index_from_filename(p)
        if idx is not None:
            out.append((idx, p))
    return sorted(out, key=lambda t: t[0])


def _prompt_text(orig_prompt) -> str | None:
    if isinstance(orig_prompt, str):
        return orig_prompt
    if orig_prompt is None:
        return None
    return str(orig_prompt)  # multimodal prompt object -> best-effort string


def split_thinking(text: str) -> str | None:
    """Return the model's thinking trace, or None.

    Handles two shapes: a full ``<think>...</think>`` block (content between), and the
    Qwen3-Thinking-2507 shape where only the closing ``</think>`` is emitted (the opening
    tag is auto-prepended by the chat template) — then everything before the first
    ``</think>`` is the trace. (The full output is preserved verbatim in ``full_response``
    regardless; this only fills the convenience ``thinking_trace`` field.)
    """
    if not text:
        return None
    m = _THINK_RE.search(text)
    if m:
        return m.group(1).strip() or None
    m = _THINK_CLOSE_RE.search(text)
    if m:
        return m.group(1).strip() or None
    return None


def _resolve_model(
    loop_index: int,
    routing_details: dict | None,
    c: int,
    model_override: str | None,
    models_cfg: list | None,
) -> str | None:
    """Best-effort model name for candidate ``c``. None when not determinable."""
    if model_override:
        return model_override
    if not models_cfg:
        return None
    names = [m.get("name") for m in models_cfg if isinstance(m, dict)]
    if not names:
        return None
    if loop_index == 0:
        return names[-1]  # loop 0 generates with the top (last) model
    routes = (routing_details or {}).get("routes")
    if isinstance(routes, list) and c < len(routes) and isinstance(routes[c], str):
        m = re.fullmatch(r"model_(\d+)", routes[c])
        if m and int(m.group(1)) < len(names):
            return names[int(m.group(1))]
        return routes[c]  # e.g. "lite"
    return names[0] if len(names) == 1 else None


def candidate_records_for_loop(
    loop_index: int,
    payload: dict,
    *,
    id_map: list[dict] | None = None,
    model_override: str | None = None,
    models_cfg: list | None = None,
    gen_params: dict | None = None,
) -> list[dict]:
    """Flatten one checkpoint (one loop) into per-candidate records. Pure; tested."""
    problems = payload.get("problems")
    if not isinstance(problems, list):
        return []
    loop_metrics = payload.get("metrics")

    records: list[dict] = []
    for q, prob in enumerate(problems):
        if not isinstance(prob, dict):
            continue
        candidates = prob.get("candidates") or []
        groups = prob.get("candidate_groups") or []
        rd = prob.get("routing_details") if isinstance(prob.get("routing_details"), dict) else None

        seed_info = id_map[q] if (id_map and q < len(id_map)) else {}
        pid = str(seed_info.get("id") or f"prob-{q:06d}")
        question = seed_info.get("question") or prob.get("question") or _prompt_text(prob.get("orig_prompt"))
        answer = seed_info.get("answer")
        if answer is None:
            answer = seed_info.get("gt")
        if answer is None:
            answer = prob.get("gt")

        group_fitnesses = (rd or {}).get("group_fitnesses")
        group_members = (rd or {}).get("group_index_members")
        confidences = (rd or {}).get("candidate_confidences") or {}
        routes = (rd or {}).get("routes")

        for c, cand in enumerate(candidates):
            full_response = cand if isinstance(cand, str) else json.dumps(cand, ensure_ascii=False)
            parent_texts = groups[c] if (isinstance(groups, list) and c < len(groups)) else None
            parent_ids = group_members[c] if (isinstance(group_members, list) and c < len(group_members)) else None
            fitness = group_fitnesses[c] if (isinstance(group_fitnesses, list) and c < len(group_fitnesses)) else None
            # candidate_confidences keys are ints in-process but strings after JSON round-trip.
            score = confidences.get(str(c), confidences.get(c)) if isinstance(confidences, dict) else None

            routing_metadata = None
            if rd is not None:
                routing_metadata = {
                    "route": routes[c] if (isinstance(routes, list) and c < len(routes)) else None,
                    "thresholds": rd.get("thresholds"),
                    "percentiles": rd.get("percentiles"),
                }
            records.append({
                "id": pid,
                "question": question,
                "answer": str(answer) if answer is not None else None,
                "loop_index": loop_index,
                "candidate_id": f"{pid}::loop{loop_index}::cand{c}",
                "group_id": c,
                "parent_ids": parent_ids,                 # indices into loop (loop_index-1); null at loop 0
                "parent_texts": parent_texts,             # parent solution strings; [] / null at loop 0
                "model": _resolve_model(loop_index, rd, c, model_override, models_cfg),
                "prompt": _prompt_text(prob.get("orig_prompt")),  # base question; recomb prompt not persisted
                "full_response": full_response,
                "thinking_trace": split_thinking(full_response),
                "final_answer": extract_final_answer(full_response),
                "fitness": fitness,                       # group fitness; null at loop 0
                "score": score,                           # confidence; null under diversity / loop 0
                "routing_metadata": routing_metadata,     # null at loop 0 (no routing yet)
                "generation_params": gen_params,          # from --config; null if not given
                "loop_metrics": loop_metrics,             # aggregate metrics for this loop
                "raw_candidate": full_response,           # SE stores candidates as plain strings
            })
    return records


def _build_id_map(se_output: Path | None) -> list[dict] | None:
    if se_output is None or not se_output.exists():
        return None
    return list(iter_jsonl(se_output))  # order matches problem order throughout the pipeline


def _gen_params_and_models(config: Path | None) -> tuple[dict | None, list | None]:
    if config is None or not config.exists():
        return None, None
    cfg = load_yaml(config)
    models = cfg.get("models") if isinstance(cfg.get("models"), list) else None
    gp = None
    if models:
        m0 = models[0]
        gp = {k: m0[k] for k in ("temperature", "top_p", "max_tokens") if isinstance(m0, dict) and k in m0}
        gp = gp or None
    return gp, models


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--checkpoint-dir", required=True, type=Path,
                   help="Dir with <run_name>_loop<t>.json checkpoints (e.g. <output>.checkpoints/).")
    p.add_argument("--output", required=True, type=Path, help="Per-loop candidate JSONL to write.")
    p.add_argument("--run-name", default=None, help="Restrict to this run_name's checkpoints.")
    p.add_argument("--se-output", type=Path, default=None,
                   help="Normalized SE JSONL (run_squeeze_evolve.py output) to map problem index -> id/question/answer.")
    p.add_argument("--config", type=Path, default=None,
                   help="SE YAML config — fills generation_params/model names (else null).")
    p.add_argument("--model", default=None, help="Override the model name stamped on every candidate.")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    if not args.checkpoint_dir.is_dir():
        logger.error("Checkpoint dir does not exist: %s", args.checkpoint_dir)
        logger.error("Per-loop history is only available after a real SqueezeEvolve run "
                     "(run_squeeze_evolve.py snapshots it to <output>.checkpoints/).")
        return 2

    files = find_checkpoint_files(args.checkpoint_dir, args.run_name)
    if not files:
        logger.error("No '<run_name>_loop<t>.json' checkpoints under %s.", args.checkpoint_dir)
        return 3

    id_map = _build_id_map(args.se_output)
    gen_params, models_cfg = _gen_params_and_models(args.config)

    all_records: list[dict] = []
    for loop_index, path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        recs = candidate_records_for_loop(
            loop_index, payload, id_map=id_map,
            model_override=args.model, models_cfg=models_cfg, gen_params=gen_params,
        )
        all_records.extend(recs)
        logger.info("loop %d: %d candidates from %s", loop_index, len(recs), path.name)

    n = write_jsonl(args.output, all_records)
    loops = sorted({lo for lo, _ in files})
    logger.info("Wrote %d per-loop candidate records across loops %s -> %s", n, loops, args.output)
    print(f"records={n} loops={loops} checkpoints={len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
