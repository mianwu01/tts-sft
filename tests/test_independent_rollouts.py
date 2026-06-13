"""Tests for scripts/run_independent_rollouts.py — output-record schema (no network)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run_independent_rollouts.py"


@pytest.fixture(scope="module")
def rir():
    spec = importlib.util.spec_from_file_location("run_independent_rollouts", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_independent_rollouts"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_build_record_schema(rir):
    rec = rir.build_record(
        sid="x1",
        question="What is 1+1?",
        answer="2",
        responses=["think ... \\boxed{2}", "alt ... \\boxed{2}"],
        model="Qwen/Qwen3-4B-Thinking-2507",
        generation_params={"temperature": 0.7, "top_p": 0.95, "max_tokens": 8192, "n_samples": 2},
    )
    assert rec["id"] == "x1"
    assert rec["question"] == "What is 1+1?"
    assert rec["answer"] == "2"
    assert rec["responses"] == ["think ... \\boxed{2}", "alt ... \\boxed{2}"]
    assert rec["n_rollouts"] == 2
    assert rec["model"] == "Qwen/Qwen3-4B-Thinking-2507"
    assert rec["source"] == "independent_rollouts"
    assert rec["generation_params"]["n_samples"] == 2


def test_build_record_allows_null_answer(rir):
    rec = rir.build_record(
        sid="x2", question="q", answer=None, responses=["r"],
        model="m", generation_params={},
    )
    assert rec["answer"] is None
    assert rec["n_rollouts"] == 1
    # build_record copies the inputs (defensive against aliasing).
    src = ["a"]
    rec2 = rir.build_record(sid="x3", question="q", answer="1", responses=src, model="m", generation_params={})
    src.append("b")
    assert rec2["responses"] == ["a"]
