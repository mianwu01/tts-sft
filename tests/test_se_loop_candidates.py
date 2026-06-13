"""Tests for scripts/se_loop_candidates.py — parser preserves loop_index + full_response.

Uses mock SqueezeEvolve per-loop checkpoint fixtures under
tests/fixtures/se_checkpoints/ (the real client writes one such file per loop).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "se_loop_candidates.py"
_FIX = Path(__file__).resolve().parent / "fixtures" / "se_checkpoints"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("se_loop_candidates", _SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules["se_loop_candidates"] = m
    spec.loader.exec_module(m)  # type: ignore[union-attr]
    return m


def _load(name: str) -> dict:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def test_find_checkpoint_files_sorted(mod):
    files = mod.find_checkpoint_files(_FIX, "tts_sft_se")
    assert [i for i, _ in files] == [0, 1]


def test_split_thinking_and_loop_index(mod):
    assert mod.split_thinking("<think>abc def</think> rest") == "abc def"
    assert mod.split_thinking("no think here") is None
    # Qwen3-Thinking-2507 shape: opening tag auto-prepended, only the closing tag emitted.
    assert mod.split_thinking("reasoning here </think>\n\nThe answer is 5") == "reasoning here"
    assert mod.loop_index_from_filename(Path("tts_sft_se_loop3.json")) == 3
    assert mod.loop_index_from_filename(Path("not_a_ckpt.json")) is None


def test_loop0_records_full_response_and_nulls(mod):
    payload = _load("tts_sft_se_loop0.json")
    recs = mod.candidate_records_for_loop(0, payload)
    assert len(recs) == 4
    assert all(r["loop_index"] == 0 for r in recs)

    r0 = recs[0]
    # full_response preserved verbatim (incl. <think>)
    assert r0["full_response"] == payload["problems"][0]["candidates"][0]
    assert r0["raw_candidate"] == r0["full_response"]
    assert r0["thinking_trace"] == "I think it is 41"
    assert r0["final_answer"] == "41"
    assert recs[1]["final_answer"] == "42"
    # loop 0: no parents / fitness / scores / routing -> null (never fabricated)
    assert r0["parent_ids"] is None
    assert r0["parent_texts"] == []
    assert r0["fitness"] is None
    assert r0["score"] is None
    assert r0["routing_metadata"] is None
    # no --config / --model given -> null
    assert r0["model"] is None
    assert r0["generation_params"] is None


def test_loop1_records_parents_fitness_routing(mod):
    payload = _load("tts_sft_se_loop1.json")
    recs = mod.candidate_records_for_loop(1, payload)
    assert len(recs) == 4

    first = recs[0]
    assert first["loop_index"] == 1
    assert first["full_response"] == payload["problems"][0]["candidates"][0]
    assert first["parent_ids"] == [1, 0]               # indices into previous loop's population
    assert first["parent_texts"] == payload["problems"][0]["candidate_groups"][0]
    assert first["fitness"] == 2.0
    assert first["score"] is None                       # diversity -> candidate_confidences {}
    assert first["routing_metadata"]["route"] == "model_0"
    assert first["group_id"] == 0


def test_id_map_and_model_override(mod):
    payload = _load("tts_sft_se_loop0.json")
    id_map = [
        {"id": "math500-000001", "question": "Q1", "gt": "42"},
        {"id": "math500-000002", "question": "Q2", "gt": "7"},
    ]
    recs = mod.candidate_records_for_loop(
        0, payload, id_map=id_map, model_override="Qwen/Qwen3-4B-Thinking-2507",
        gen_params={"temperature": 0.7},
    )
    assert recs[0]["id"] == "math500-000001"
    assert recs[0]["answer"] == "42"
    assert recs[0]["candidate_id"] == "math500-000001::loop0::cand0"
    assert recs[0]["model"] == "Qwen/Qwen3-4B-Thinking-2507"
    assert recs[0]["generation_params"] == {"temperature": 0.7}


def test_model_from_config_loop0_uses_top_model(mod):
    payload = _load("tts_sft_se_loop0.json")
    models_cfg = [{"name": "cheap"}, {"name": "expensive"}]
    recs = mod.candidate_records_for_loop(0, payload, models_cfg=models_cfg)
    assert recs[0]["model"] == "expensive"  # loop 0 generates with the top (last) model


def test_main_end_to_end(mod, tmp_path, monkeypatch):
    out = tmp_path / "loop_candidates.jsonl"
    monkeypatch.setattr(sys, "argv", [
        "se_loop_candidates.py",
        "--checkpoint-dir", str(_FIX),
        "--run-name", "tts_sft_se",
        "--output", str(out),
    ])
    assert mod.main() == 0
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 8                                   # 2 loops x 2 problems x 2 candidates
    assert sorted({r["loop_index"] for r in rows}) == [0, 1]
    assert all(r["full_response"] for r in rows)
