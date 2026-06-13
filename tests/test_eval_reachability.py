"""Tests for scripts/eval_reachability.py — category logic + summary over fixtures."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "eval_reachability.py"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def er():
    spec = importlib.util.spec_from_file_location("eval_reachability", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_reachability"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _load_by_id(name: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for line in (_FIXTURES / name).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            r = json.loads(line)
            out[str(r["id"])] = r
    return out


def test_categorize(er):
    assert er.categorize(True, True) == "both_solved"
    assert er.categorize(True, False) == "only_se_solved"
    assert er.categorize(False, True) == "only_independent_solved"
    assert er.categorize(False, False) == "neither_solved"


def test_evaluate_categories_on_fixtures(er):
    se = _load_by_id("mock_se_outputs.jsonl")
    ind = _load_by_id("mock_independent_outputs.jsonl")
    per_problem, summary = er.evaluate(se, ind, None)

    cat = {r["id"]: r["category"] for r in per_problem}
    assert cat == {
        "p1": "both_solved",
        "p2": "only_se_solved",
        "p3": "only_independent_solved",
        "p4": "neither_solved",
    }

    assert summary["total"] == 4
    assert summary["se_solved"] == 2
    assert summary["independent_solved"] == 2
    assert summary["both_solved"] == 1
    assert summary["only_se_solved"] == 1
    assert summary["only_independent_solved"] == 1
    assert summary["neither_solved"] == 1
    assert set(summary["ids_by_category"]["both_solved"]) == {"p1"}
    assert set(summary["ids_by_category"]["only_se_solved"]) == {"p2"}


def test_per_problem_fields(er):
    se = _load_by_id("mock_se_outputs.jsonl")
    ind = _load_by_id("mock_independent_outputs.jsonl")
    per_problem, _ = er.evaluate(se, ind, None)
    p1 = next(r for r in per_problem if r["id"] == "p1")

    assert p1["gold"] == "42"
    assert p1["se_correct"] is True
    assert p1["independent_correct"] is True
    assert "42" in p1["se_predictions"]
    assert p1["se_num_candidates"] == 2
    assert p1["independent_num_rollouts"] == 2


def test_id_mismatch_is_excluded(er):
    se = {"a": {"id": "a", "gt": "1", "candidates": ["\\boxed{1}"]}}
    ind = {"b": {"id": "b", "answer": "1", "responses": ["\\boxed{1}"]}}
    per_problem, summary = er.evaluate(se, ind, None)
    assert summary["total"] == 0
    assert summary["n_only_in_se_file"] == 1
    assert summary["n_only_in_independent_file"] == 1


def test_extract_se_texts_prefers_candidates(er):
    rec = {"candidates": ["c1", "c2"], "final_response": "fr"}
    assert er.extract_se_texts(rec) == ["c1", "c2"]
    # Falls back to final_response when no candidate list is present.
    assert er.extract_se_texts({"final_response": "fr"}) == ["fr"]


def test_latex_equivalent_tuple_counts_as_solved(er):
    # Node 1 smoke case flowing through the reachability grader: a boxed-tuple SE
    # candidate must count as solving a \left(..\right) gold (the evaluator fix),
    # while a genuinely different independent rollout must not. Before the fix this
    # was scored only_independent/neither; it must now be only_se_solved.
    se = {"q": {"id": "q", "gt": "\\left( 3, \\frac{\\pi}{2} \\right)",
                "candidates": ["I conclude \\boxed{(3, \\frac{\\pi}{2})}"]}}
    ind = {"q": {"id": "q", "answer": "\\left( 3, \\frac{\\pi}{2} \\right)",
                 "responses": ["maybe \\boxed{(0, 0)}"]}}
    per_problem, summary = er.evaluate(se, ind, None)
    assert len(per_problem) == 1
    r = per_problem[0]
    assert r["se_correct"] is True
    assert r["independent_correct"] is False
    assert r["category"] == "only_se_solved"
