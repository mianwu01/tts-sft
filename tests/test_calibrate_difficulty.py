"""Tests for scripts/calibrate_difficulty.py (single-arm grading + bucketing)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "calibrate_difficulty.py"


@pytest.fixture(scope="module")
def cd():
    spec = importlib.util.spec_from_file_location("calibrate_difficulty", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["calibrate_difficulty"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_bucket_thresholds(cd):
    assert cd.bucket_of(0, easy_threshold=6, hard_threshold=0) == "hard"
    assert cd.bucket_of(1, 6, 0) == "medium"
    assert cd.bucket_of(5, 6, 0) == "medium"
    assert cd.bucket_of(6, 6, 0) == "easy"
    assert cd.bucket_of(8, 6, 0) == "easy"


def test_grade_problem_counts_solved(cd):
    rec = {
        "id": "aime25-000007", "answer": "42", "question": "Q",
        "responses": [
            "reasoning \\boxed{42}",          # correct
            "the answer is 42",               # correct (textual)
            "\\boxed{41}",                    # wrong
            "no final answer here",           # no extractable answer
        ],
    }
    g = cd.grade_problem(rec, easy_threshold=6, hard_threshold=0)
    assert g["dataset"] == "aime25"
    assert g["n_samples"] == 4
    assert g["solved_count"] == 2
    assert g["any_solved"] is True
    assert g["n_with_extractable_answer"] == 3   # 3 produced an answer string
    assert g["bucket"] == "medium"
    assert "1/4 samples had no extractable answer" in g["note"]


def test_grade_problem_hard_and_easy(cd):
    hard = cd.grade_problem({"id": "h-1", "answer": "5", "responses": ["\\boxed{1}"] * 8}, 6, 0)
    assert hard["solved_count"] == 0 and hard["bucket"] == "hard" and hard["any_solved"] is False
    easy = cd.grade_problem({"id": "e-1", "answer": "5", "responses": ["\\boxed{5}"] * 8}, 6, 0)
    assert easy["solved_count"] == 8 and easy["bucket"] == "easy"


def test_grade_problem_latex_equivalence_applies(cd):
    # The corrected evaluator (\left/\right, whitespace) must be in force here too.
    rec = {"id": "x-1", "answer": "\\left( 3, \\frac{\\pi}{2} \\right)",
           "responses": ["\\boxed{(3, \\frac{\\pi}{2})}"] + ["\\boxed{0}"] * 7}
    g = cd.grade_problem(rec, 6, 0)
    assert g["solved_count"] == 1


def test_recommend_excludes_easy_and_orders_least_saturated_first(cd):
    summaries = [
        {"id": "easy1", "bucket": "easy", "solved_count": 7, "frac_with_answer": 1.0},
        {"id": "med3", "bucket": "medium", "solved_count": 3, "frac_with_answer": 1.0},
        {"id": "med1", "bucket": "medium", "solved_count": 1, "frac_with_answer": 1.0},
        {"id": "hard1", "bucket": "hard", "solved_count": 0, "frac_with_answer": 0.5},
    ]
    rec = cd.recommend_subset(summaries, target_min=1, target_max=10)
    ids = [s["id"] for s in rec]
    assert "easy1" not in ids
    assert ids[0] == "hard1"          # least saturated first
    assert ids == ["hard1", "med1", "med3"]


def test_recommend_respects_target_max(cd):
    summaries = [{"id": f"h{i}", "bucket": "hard", "solved_count": 0, "frac_with_answer": 0.0} for i in range(30)]
    assert len(cd.recommend_subset(summaries, target_min=10, target_max=20)) == 20
