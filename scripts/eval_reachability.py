#!/usr/bin/env python
"""Reachability evaluator: SqueezeEvolve vs. compute-matched independent rollouts.

Offline grader (no model calls). For each problem present in BOTH arms it asks:
does *any* SqueezeEvolve candidate solve it, and does *any* of the N independent
rollouts solve it — then assigns a category::

    both_solved | only_se_solved | only_independent_solved | neither_solved

Grading reuses the repo's exact-match checker (``src/tts_sft/answer_extraction.py``);
no symbolic equivalence (a known limitation — see repo-evidence-map.md / results-schema.md).

Inputs:
  --se-output           normalized SqueezeEvolve JSONL (id, gt, candidates/final_response/...)
  --independent-output  independent-rollouts JSONL (id, answer, responses/response)
  --output-jsonl        per-problem result records
  --summary-json        aggregate summary + ids_by_category
  --se-budget-jsonl /   optional per-problem budget (from scripts/se_budget.py) to source
  --se-budget-json      ``se_num_candidates`` from, instead of len(candidates)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from tts_sft.answer_extraction import extract_final_answer, is_exact_match, normalize_math_answer  # noqa: E402
from tts_sft.io_utils import iter_jsonl, write_jsonl  # noqa: E402
from tts_sft.metrics import accuracy  # noqa: E402

logger = logging.getLogger("eval_reachability")

CATEGORIES = ("both_solved", "only_se_solved", "only_independent_solved", "neither_solved")


def categorize(se_correct: bool, independent_correct: bool) -> str:
    if se_correct and independent_correct:
        return "both_solved"
    if se_correct and not independent_correct:
        return "only_se_solved"
    if (not se_correct) and independent_correct:
        return "only_independent_solved"
    return "neither_solved"


def _as_text_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, str) or v is not None]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def extract_se_texts(rec: dict) -> list[str]:
    """All candidate solution texts from a SqueezeEvolve record (any-of-N)."""
    for key in ("candidates", "population", "responses"):
        texts = _as_text_list(rec.get(key))
        if texts:
            return texts
    # Single-response fallbacks.
    for key in ("final_response", "response"):
        texts = _as_text_list(rec.get(key))
        if texts:
            return texts
    return []


def extract_independent_texts(rec: dict) -> list[str]:
    """All rollout texts from an independent-rollouts record (any-of-N)."""
    texts = _as_text_list(rec.get("responses"))
    if texts:
        return texts
    return _as_text_list(rec.get("response"))


def _predictions(texts: list[str]) -> list[str]:
    """Extracted + normalized final answers (drops texts with no extractable answer)."""
    preds: list[str] = []
    for t in texts:
        a = extract_final_answer(t)
        if a is not None:
            preds.append(normalize_math_answer(a))
    return preds


def _any_correct(texts: list[str], gold: str | None) -> bool:
    if not gold:
        return False
    return any(is_exact_match(extract_final_answer(t), gold) for t in texts)


def _get_gold(se_rec: dict, ind_rec: dict) -> str | None:
    se_gold = se_rec.get("gt")
    ind_gold = ind_rec.get("answer")
    se_gold = str(se_gold) if se_gold is not None else None
    ind_gold = str(ind_gold) if ind_gold is not None else None
    if se_gold and ind_gold and normalize_math_answer(se_gold) != normalize_math_answer(ind_gold):
        logger.warning(
            "Gold mismatch for a problem: SE gt=%r vs independent answer=%r — using SE gt.",
            se_gold, ind_gold,
        )
    return se_gold or ind_gold


def _se_num_candidates(se_rec: dict, se_texts: list[str], budget_rec: dict | None) -> int:
    if isinstance(budget_rec, dict) and isinstance(budget_rec.get("final_candidate_count"), int):
        return budget_rec["final_candidate_count"]
    meta = se_rec.get("metadata") or {}
    if isinstance(meta.get("n_candidates"), int):
        return meta["n_candidates"]
    return len(se_texts)


def evaluate(
    se_by_id: dict[str, dict],
    ind_by_id: dict[str, dict],
    budget_by_id: dict[str, dict] | None = None,
) -> tuple[list[dict], dict]:
    """Compare the two arms over the problems present in BOTH. Pure; unit-tested.

    Returns ``(per_problem_records, summary)``. Problems present in only one arm
    cannot be compared (matched-budget requires both attempted them); they are
    excluded from ``total`` and reported as ``n_only_in_*_file`` in the summary.
    """
    budget_by_id = budget_by_id or {}
    common = sorted(set(se_by_id) & set(ind_by_id))
    only_se = sorted(set(se_by_id) - set(ind_by_id))
    only_ind = sorted(set(ind_by_id) - set(se_by_id))
    if only_se or only_ind:
        logger.warning(
            "ID mismatch between arms: %d only in SE file, %d only in independent file "
            "(excluded from the comparison).", len(only_se), len(only_ind),
        )

    per_problem: list[dict] = []
    ids_by_category: dict[str, list[str]] = {c: [] for c in CATEGORIES}
    for pid in common:
        se_rec = se_by_id[pid]
        ind_rec = ind_by_id[pid]
        gold = _get_gold(se_rec, ind_rec)

        se_texts = extract_se_texts(se_rec)
        ind_texts = extract_independent_texts(ind_rec)

        se_correct = _any_correct(se_texts, gold)
        ind_correct = _any_correct(ind_texts, gold)
        category = categorize(se_correct, ind_correct)
        ids_by_category[category].append(pid)

        ind_n = ind_rec.get("n_rollouts")
        per_problem.append({
            "id": pid,
            "gold": gold,
            "se_correct": se_correct,
            "independent_correct": ind_correct,
            "se_num_candidates": _se_num_candidates(se_rec, se_texts, budget_by_id.get(pid)),
            "independent_num_rollouts": ind_n if isinstance(ind_n, int) else len(ind_texts),
            "se_predictions": _predictions(se_texts),
            "independent_predictions": _predictions(ind_texts),
            "category": category,
        })

    summary = {
        "total": len(per_problem),
        "se_solved": sum(1 for r in per_problem if r["se_correct"]),
        "independent_solved": sum(1 for r in per_problem if r["independent_correct"]),
        "both_solved": len(ids_by_category["both_solved"]),
        "only_se_solved": len(ids_by_category["only_se_solved"]),
        "only_independent_solved": len(ids_by_category["only_independent_solved"]),
        "neither_solved": len(ids_by_category["neither_solved"]),
        "ids_by_category": ids_by_category,
        "n_only_in_se_file": len(only_se),
        "n_only_in_independent_file": len(only_ind),
    }
    return per_problem, summary


def _load_by_id(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in iter_jsonl(path):
        rid = str(r.get("id", ""))
        if rid:
            out[rid] = r
    return out


def _load_budget(jsonl: Path | None, json_path: Path | None) -> dict[str, dict] | None:
    if jsonl is not None and jsonl.exists():
        return _load_by_id(jsonl)
    if json_path is not None and json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items()}
        if isinstance(data, list):
            return {str(r.get("id", "")): r for r in data if isinstance(r, dict)}
    return None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--se-output", required=True, type=Path, help="Normalized SqueezeEvolve JSONL.")
    p.add_argument("--independent-output", required=True, type=Path, help="Independent-rollouts JSONL.")
    p.add_argument("--output-jsonl", required=True, type=Path, help="Per-problem result JSONL.")
    p.add_argument("--summary-json", required=True, type=Path, help="Aggregate summary JSON.")
    p.add_argument("--se-budget-jsonl", type=Path, default=None, help="Optional budget JSONL (scripts/se_budget.py).")
    p.add_argument("--se-budget-json", type=Path, default=None, help="Optional budget JSON mapping (id -> record).")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    for f in (args.se_output, args.independent_output):
        if not f.exists():
            logger.error("Input file does not exist: %s", f)
            return 2

    se_by_id = _load_by_id(args.se_output)
    ind_by_id = _load_by_id(args.independent_output)
    budget_by_id = _load_budget(args.se_budget_jsonl, args.se_budget_json)

    per_problem, summary = evaluate(se_by_id, ind_by_id, budget_by_id)

    write_jsonl(args.output_jsonl, per_problem)
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # Light reuse of metrics.accuracy for human-readable solved-rates.
    _, _, se_rate = accuracy({"correct": r["se_correct"]} for r in per_problem)
    _, _, ind_rate = accuracy({"correct": r["independent_correct"]} for r in per_problem)
    logger.info(
        "Reachability: total=%d both=%d only_se=%d only_independent=%d neither=%d",
        summary["total"], summary["both_solved"], summary["only_se_solved"],
        summary["only_independent_solved"], summary["neither_solved"],
    )
    logger.info("any-of-N solved rate: SE=%.4f independent=%.4f", se_rate, ind_rate)
    print(
        f"total={summary['total']} both={summary['both_solved']} "
        f"only_se={summary['only_se_solved']} only_independent={summary['only_independent_solved']} "
        f"neither={summary['neither_solved']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
