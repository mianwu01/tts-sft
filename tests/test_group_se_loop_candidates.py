"""Tests for scripts/group_se_loop_candidates.py (per-problem regrouping)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "group_se_loop_candidates.py"


@pytest.fixture(scope="module")
def gc():
    spec = importlib.util.spec_from_file_location("group_se_loop_candidates", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["group_se_loop_candidates"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _mk(pid, loop, c, ans="42"):
    return {
        "id": pid, "loop_index": loop, "group_id": c,
        "candidate_id": f"{pid}::loop{loop}::cand{c}",
        "answer": ans, "question": "Q",
        "full_response": f"resp-{pid}-L{loop}-C{c} \\boxed{{{ans}}}",
        "final_answer": ans, "parent_ids": None if loop == 0 else [0, 1], "fitness": None if loop == 0 else 0.5,
    }


def test_groups_all_loops_per_problem(gc):
    # 2 problems x (2 loops x 2 candidates) = 8 rows -> 2 problems x 4 candidates.
    recs = [_mk(pid, loop, c) for pid in ("p1", "p2") for loop in (0, 1) for c in (0, 1)]
    out = gc.group_candidates(recs)
    assert [g["id"] for g in out] == ["p1", "p2"]
    g = out[0]
    assert g["metadata"]["n_candidates"] == 4
    assert g["metadata"]["n_by_loop"] == {"0": 2, "1": 2}
    assert g["gt"] == "42"
    assert len(g["candidates"]) == 4


def test_ordered_loop0_before_loop1(gc):
    recs = [_mk("p1", 1, 0), _mk("p1", 0, 1), _mk("p1", 0, 0), _mk("p1", 1, 1)]
    out = gc.group_candidates(recs)
    loops = [m["loop_index"] for m in out[0]["candidate_meta"]]
    assert loops == [0, 0, 1, 1]  # sorted by (loop_index, group_id)


def test_include_loops_filter(gc):
    recs = [_mk("p1", loop, c) for loop in (0, 1) for c in (0, 1)]
    out = gc.group_candidates(recs, include_loops={0})
    assert out[0]["metadata"]["n_candidates"] == 2
    assert out[0]["metadata"]["n_by_loop"] == {"0": 2}


def test_eval_reachability_can_grade_grouped_output(gc):
    # The grouped record must be consumable by eval_reachability's SE extractor + grader.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from tts_sft.answer_extraction import extract_final_answer, is_exact_match

    recs = [_mk("p1", loop, c, ans="588") for loop in (0, 1) for c in (0, 1)]
    g = gc.group_candidates(recs)[0]
    assert g["gt"] == "588"
    solved = any(is_exact_match(extract_final_answer(t), g["gt"]) for t in g["candidates"])
    assert solved is True


def test_preserves_candidate_provenance(gc):
    recs = [_mk("p1", 1, 0)]
    meta = gc.group_candidates(recs)[0]["candidate_meta"][0]
    assert meta["loop_index"] == 1
    assert meta["candidate_id"] == "p1::loop1::cand0"
    assert meta["parent_ids"] == [0, 1]
    assert meta["fitness"] == 0.5
    assert meta["final_answer"] == "42"
