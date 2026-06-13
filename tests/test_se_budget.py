"""Tests for scripts/se_budget.py — the honesty contract (no pretend budgets)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "se_budget.py"


@pytest.fixture(scope="module")
def seb():
    spec = importlib.util.spec_from_file_location("se_budget", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["se_budget"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_final_candidate_count_prefers_metadata(seb):
    assert seb.final_candidate_count({"metadata": {"n_candidates": 3}, "candidates": ["a", "b"]}) == 3
    assert seb.final_candidate_count({"candidates": ["a", "b"]}) == 2
    assert seb.final_candidate_count({}) == 0


def test_budget_unknown_without_metrics(seb):
    rec = {"id": "p1", "candidates": ["a", "b", "c"], "metadata": {"n_candidates": 3, "squeeze_evolve_run_id": "r"}}
    out = seb.build_budget_record(rec, raw_problem=None, metrics=None, cfg=None, run_id=None)
    # The key honesty invariant: never claim a total from the final population.
    assert out["final_candidate_count"] == 3
    assert out["lower_bound_generations"] == 3
    assert out["estimated_total_generations"] is None
    assert out["budget_status"] == "UNKNOWN"
    assert out["run_id"] == "r"


def test_heuristic_from_config(seb):
    assert seb.heuristic_lower_bound_from_config({"routing": {"population": 4, "loops": 4}}) == 16
    assert seb.heuristic_lower_bound_from_config({"routing": {}}) is None
    assert seb.heuristic_lower_bound_from_config(None) is None


def test_extract_total_generations_when_field_present(seb):
    # Direct recognized field -> trusted.
    assert seb._extract_total_generations({"total_generations": 37}, None) == 37
    # Per-loop telemetry summed only when every loop exposes a recognized key.
    rd = {"routing_details": [{"n_generations": 8}, {"n_generations": 8}, {"n_generations": 4}]}
    assert seb._extract_total_generations(rd, None) == 20
    # Unknown structure -> None (UNKNOWN), never guessed.
    assert seb._extract_total_generations({"routing_details": {"weird": 1}}, None) is None
    assert seb._extract_total_generations(None, None) is None


def test_total_generations_from_metrics(seb):
    metrics = [
        {"loop": 0, "model_0_count": 4, "lite_count": 0},
        {"loop": 1, "model_0_count": 4, "lite_count": 0},
    ]
    assert seb._total_generations_from_metrics(metrics) == 8           # 4 + 4 generations
    assert seb._total_generations_from_metrics(None) is None
    assert seb._total_generations_from_metrics([{"loop": 0, "time_total_s": 1.0}]) is None  # no count field


def test_budget_from_metrics_per_problem(seb):
    rec = {"id": "p1", "candidates": ["a", "b", "c", "d"], "metadata": {"n_candidates": 4}}
    out = seb.build_budget_record(
        rec, raw_problem=None, metrics=None, cfg=None, run_id=None,
        metrics_per_problem=8, metrics_total_all_problems=8, n_problems=1,
    )
    assert out["estimated_total_generations"] == 8
    assert out["budget_status"] == "FROM_RAW_METRICS"
    assert out["budget_basis"].startswith("metrics")
    assert out["lower_bound_generations"] == 4    # final population size never promoted to total
