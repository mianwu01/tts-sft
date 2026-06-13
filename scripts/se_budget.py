#!/usr/bin/env python
"""Estimate the per-problem rollout budget ``N_i`` from SqueezeEvolve outputs.

The reachability diagnostic compares SqueezeEvolve against *compute-matched*
independent sampling. "Compute-matched" means: for each problem, draw the SAME
number of independent rollouts that SqueezeEvolve actually spent on that problem.
That number is the TOTAL count of LLM generations across all evolutionary loops —
**not** the size of the final candidate population.

HONESTY CONTRACT (read before trusting any number here)
-------------------------------------------------------
* ``final_candidate_count`` (== ``metadata.n_candidates`` == ``len(candidates)``)
  is the FINAL population size only. It is a *lower bound* on total generations,
  NOT the budget. This tool reports it as ``lower_bound_generations`` and will
  **never** pass it off as the total.
* The true total must come from SqueezeEvolve's own telemetry — the ``metrics`` /
  ``routing_details`` in the kept ``<output>.raw.json`` and/or ``metrics_path``
  (``metrics.json``). Their exact field layout is **not yet verified against a
  real run**. Until a recognized field is found, ``estimated_total_generations``
  is ``null`` and ``budget_status`` is ``"UNKNOWN"``.
* ``heuristic_lower_bound_from_config`` (= ``population * loops`` if a config is
  supplied) is a rough, clearly-labeled heuristic — also a lower bound, also not
  authoritative.

DONE (2026-06-04 smoke): per-loop ``metrics`` (raw.json["metrics"] / metrics.json) expose
``model_<tier>_count`` (+ ``lite_count``) = generations per loop, aggregated over problems.
``_total_generations_from_metrics`` sums them; per-problem ``N_i`` = that total / n_problems
(uniform-budget assumption), which flips ``budget_status`` to ``"FROM_RAW_METRICS"``.
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

from tts_sft.io_utils import iter_jsonl, load_yaml, write_jsonl  # noqa: E402

logger = logging.getLogger("se_budget")

# Field names that, IF present in SqueezeEvolve telemetry, plausibly hold a
# per-problem total-generation count. We only trust an explicit, recognized
# field — we never infer a total from the final population size.
_TOTAL_GEN_KEYS = ("total_generations", "num_generations", "n_generations", "generations")

# Per-loop LLM-call counts in SqueezeEvolve metrics (raw.json["metrics"] entries and
# metrics.json): each loop logs model_<tier>_count (calls per backend tier) + lite_count.
# Summed across loops these give the run-wide total number of generations.
_LOOP_COUNT_RE = re.compile(r"^model_\d+_count$")


def _total_generations_from_metrics(metrics: object | None) -> int | None:
    """Sum LLM generation calls across all loops from SqueezeEvolve per-loop metrics.

    Each per-loop entry exposes ``model_<tier>_count`` (+ ``lite_count``) = generations
    that loop, AGGREGATED over all problems in the run. Returns the run-wide total
    (across loops and problems), or ``None`` if no such count field is present.
    """
    if isinstance(metrics, dict):
        metrics = [metrics]
    if not isinstance(metrics, list) or not metrics:
        return None
    total = 0
    found = False
    for loop in metrics:
        if not isinstance(loop, dict):
            continue
        for k, v in loop.items():
            if isinstance(v, bool) or not isinstance(v, int):
                continue
            if _LOOP_COUNT_RE.match(k):
                total += v
                found = True
            elif k == "lite_count":
                total += v
    return total if found else None


def final_candidate_count(rec: dict) -> int:
    """Final population size for one normalized SqueezeEvolve record.

    Prefers ``metadata.n_candidates`` (what the wrapper recorded), falling back
    to ``len(candidates)``. This is NOT the total rollout budget.
    """
    meta = rec.get("metadata") or {}
    n = meta.get("n_candidates")
    if isinstance(n, int):
        return n
    cands = rec.get("candidates")
    return len(cands) if isinstance(cands, list) else 0


def _extract_total_generations(raw_problem: dict | None, metrics: object | None) -> int | None:
    """Return the total LLM generations for a problem IF a recognized field exists.

    Returns ``None`` (=> UNKNOWN) when no trusted field is found. Deliberately
    conservative: we do not synthesize a number from unknown telemetry.
    """
    if isinstance(raw_problem, dict):
        # Direct keys on the problem.
        for k in _TOTAL_GEN_KEYS:
            v = raw_problem.get(k)
            if isinstance(v, int):
                return v
        # Per-loop routing telemetry: sum if every loop exposes a recognized key.
        rd = raw_problem.get("routing_details")
        if isinstance(rd, list) and rd:
            totals = []
            for loop in rd:
                if isinstance(loop, dict):
                    for k in _TOTAL_GEN_KEYS:
                        if isinstance(loop.get(k), int):
                            totals.append(loop[k])
                            break
            if len(totals) == len(rd):
                return sum(totals)
    return None


def heuristic_lower_bound_from_config(cfg: dict | None) -> int | None:
    """Rough ``population * loops`` lower bound, or ``None`` if config lacks them."""
    if not isinstance(cfg, dict):
        return None
    routing = cfg.get("routing") or {}
    pop = routing.get("population")
    loops = routing.get("loops")
    if isinstance(pop, int) and isinstance(loops, int):
        return pop * loops
    return None


def build_budget_record(
    rec: dict,
    *,
    raw_problem: dict | None,
    metrics: object | None,
    cfg: dict | None,
    run_id: str | None,
    metrics_per_problem: int | None = None,
    metrics_total_all_problems: int | None = None,
    n_problems: int | None = None,
) -> dict:
    """Build one per-problem budget record (pure; unit-tested).

    ``estimated_total_generations`` (the per-problem budget ``N_i``) is taken, in order:
    (1) a recognized field on the raw problem / its per-loop routing_details list, else
    (2) ``metrics_per_problem`` = run-wide generations (sum of per-loop model_*_count +
    lite_count) / n_problems. Stays ``None`` (UNKNOWN) when neither is available.
    """
    fcc = final_candidate_count(rec)
    total = _extract_total_generations(raw_problem, metrics)
    basis: str | None = "raw_problem_field" if total is not None else None
    if total is None and metrics_per_problem is not None:
        total = metrics_per_problem
        basis = "metrics:sum(model_*_count+lite_count)/n_problems"
    heuristic = heuristic_lower_bound_from_config(cfg)

    raw_fields: dict = {}
    if isinstance(raw_problem, dict):
        rd = raw_problem.get("routing_details")
        cg = raw_problem.get("candidate_groups")
        raw_fields = {
            "problem_keys": sorted(raw_problem.keys()),
            "routing_details_type": type(rd).__name__,
            "routing_details_len": len(rd) if isinstance(rd, (list, dict)) else None,
            "candidate_groups_len": len(cg) if isinstance(cg, list) else None,
            "n_candidates_in_raw": len(raw_problem["candidates"]) if isinstance(raw_problem.get("candidates"), list) else None,
        }

    return {
        "id": str(rec.get("id", "")),
        "run_id": (rec.get("metadata") or {}).get("squeeze_evolve_run_id") or run_id,
        "final_candidate_count": fcc,
        "lower_bound_generations": fcc,
        "estimated_total_generations": total,                 # per-problem N_i; None => UNKNOWN
        "budget_basis": basis,                                # how N_i was derived (None if UNKNOWN)
        "metrics_total_generations_all_problems": metrics_total_all_problems,
        "n_problems": n_problems,
        "heuristic_lower_bound_from_config": heuristic,        # rough population*loops, may be None
        "budget_status": "FROM_RAW_METRICS" if total is not None else "UNKNOWN",
        "raw_available_fields": raw_fields,
        "notes": (
            "estimated_total_generations is the per-problem total LLM generations N_i. With "
            "budget_basis='metrics:...', it is sum(model_*_count+lite_count) over all loops / "
            "n_problems (assumes ~uniform per-problem budget; if problems differ, refine from "
            "per-loop checkpoint candidate counts). final_candidate_count/lower_bound_generations "
            "is the FINAL population size only, never the total."
        ),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--se-output", required=True, type=Path,
                   help="Normalized SqueezeEvolve output JSONL (from run_squeeze_evolve.py).")
    p.add_argument("--raw-json", type=Path, default=None,
                   help="Kept raw orchestrator JSON (<output>.raw.json) for routing_details/metrics.")
    p.add_argument("--metrics-json", type=Path, default=None,
                   help="SqueezeEvolve metrics.json (from the config's metrics_path), if available.")
    p.add_argument("--config", type=Path, default=None,
                   help="SqueezeEvolve YAML config — used ONLY for a labeled population*loops heuristic.")
    p.add_argument("--output", required=True, type=Path, help="Per-problem budget JSONL (id -> budget fields).")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    if not args.se_output.exists():
        logger.error("SE output file does not exist: %s", args.se_output)
        return 2

    se_records = list(iter_jsonl(args.se_output))

    raw_problems: list = []
    raw_metrics: object | None = None
    run_id: str | None = None
    if args.raw_json is not None and args.raw_json.exists():
        payload = json.loads(args.raw_json.read_text(encoding="utf-8"))
        run_id = payload.get("run_id")
        probs = payload.get("problems")
        if isinstance(probs, list):
            raw_problems = probs
        raw_metrics = payload.get("metrics")
        logger.info("Loaded raw JSON with %d problems (run_id=%s).", len(raw_problems), run_id)
    elif args.raw_json is not None:
        logger.warning("--raw-json given but not found: %s (continuing without it).", args.raw_json)

    metrics: object | None = None
    if args.metrics_json is not None and args.metrics_json.exists():
        metrics = json.loads(args.metrics_json.read_text(encoding="utf-8"))
        logger.info("Loaded metrics.json: %s", args.metrics_json)

    cfg = load_yaml(args.config) if (args.config is not None and args.config.exists()) else None

    # Per-loop generation counts: prefer metrics.json, fall back to raw.json["metrics"].
    metrics_source = metrics if metrics is not None else raw_metrics
    metrics_total = _total_generations_from_metrics(metrics_source)
    n_problems = len(se_records) or len(raw_problems)
    metrics_per_problem: int | None = None
    if metrics_total is not None and n_problems:
        metrics_per_problem, remainder = divmod(metrics_total, n_problems)
        if remainder:
            logger.warning(
                "Per-loop generation total %d not divisible by n_problems %d (remainder %d): "
                "per-problem budget likely NON-uniform — using floor %d; refine from per-loop "
                "checkpoint candidate counts if exactness matters.",
                metrics_total, n_problems, remainder, metrics_per_problem,
            )
        else:
            logger.info("Recovered per-problem N_i=%d from metrics (%d generations / %d problems).",
                        metrics_per_problem, metrics_total, n_problems)

    out_records: list[dict] = []
    n_known = 0
    for i, rec in enumerate(se_records):
        raw_problem = raw_problems[i] if i < len(raw_problems) else None
        budget = build_budget_record(
            rec, raw_problem=raw_problem, metrics=metrics_source, cfg=cfg, run_id=run_id,
            metrics_per_problem=metrics_per_problem,
            metrics_total_all_problems=metrics_total, n_problems=n_problems,
        )
        if budget["budget_status"] == "FROM_RAW_METRICS":
            n_known += 1
        out_records.append(budget)

    n = write_jsonl(args.output, out_records)
    logger.info("Wrote %d budget records to %s.", n, args.output)
    logger.info("Per-problem total generations KNOWN for %d/%d problems; the rest are UNKNOWN.", n_known, n)
    if n_known == 0:
        logger.warning(
            "No total-generation counts were recoverable. Compute-matching is NOT yet possible. "
            "Run a small SqueezeEvolve smoke run, inspect the raw JSON / metrics.json, then update "
            "_extract_total_generations() to read the real field(s)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
