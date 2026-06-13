"""Tests for the run_squeeze_evolve.py wrapper additions (no network):

- _preserve_loop_checkpoints snapshots the official per-loop checkpoints.
- _normalize_orchestrator_output merges the checkpoint metadata in.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run_squeeze_evolve.py"


@pytest.fixture(scope="module")
def rse():
    spec = importlib.util.spec_from_file_location("run_squeeze_evolve", _SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules["run_squeeze_evolve"] = m
    spec.loader.exec_module(m)  # type: ignore[union-attr]
    return m


def test_preserve_loop_checkpoints_snapshots(rse, tmp_path):
    se_dir = tmp_path / "se"
    ckpt = se_dir / "outputs" / "squeeze_evolve" / "checkpoints"
    ckpt.mkdir(parents=True)
    (ckpt / "tts_sft_se_loop0.json").write_text('{"problems": [], "metrics": {}}', encoding="utf-8")
    (ckpt / "tts_sft_se_loop1.json").write_text('{"problems": [], "metrics": {}}', encoding="utf-8")
    # A stray file from another run_name must NOT be picked up.
    (ckpt / "other_loop0.json").write_text("{}", encoding="utf-8")

    output = tmp_path / "out" / "se.jsonl"
    output.parent.mkdir(parents=True)
    patched = {"run_name": "tts_sft_se", "checkpoint_dir": "./outputs/squeeze_evolve/checkpoints"}

    info = rse._preserve_loop_checkpoints(se_dir, patched, output)
    assert info["n_loop_checkpoints"] == 2
    dest = output.parent / (output.name + ".checkpoints")
    assert (dest / "tts_sft_se_loop0.json").exists()
    assert (dest / "tts_sft_se_loop1.json").exists()
    assert not (dest / "other_loop0.json").exists()


def test_preserve_returns_zero_when_missing(rse, tmp_path):
    se_dir = tmp_path / "se_empty"
    se_dir.mkdir()
    output = tmp_path / "o2" / "se.jsonl"
    output.parent.mkdir(parents=True)
    info = rse._preserve_loop_checkpoints(se_dir, {"run_name": "tts_sft_se", "checkpoint_dir": "./nope"}, output)
    assert info["n_loop_checkpoints"] == 0


def test_normalize_merges_extra_metadata(rse, tmp_path):
    raw = {"run_id": "r1", "problems": [{"orig_prompt": "q", "gt": "42", "candidates": ["x \\boxed{42}"]}]}
    raw_path = tmp_path / "raw.json"
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    out = tmp_path / "norm.jsonl"
    seeds = [{"id": "p1", "question": "q"}]

    n = rse._normalize_orchestrator_output(
        seeds, raw_path, out, "mymodel",
        extra_metadata={"checkpoint_dir": "/snap", "run_name": "tts_sft_se", "n_loop_checkpoints": 3},
    )
    assert n == 1
    rec = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert rec["metadata"]["n_candidates"] == 1
    assert rec["metadata"]["n_loop_checkpoints"] == 3
    assert rec["metadata"]["checkpoint_dir"] == "/snap"
    # Backward compatible: no extra_metadata still works.
    out2 = tmp_path / "norm2.jsonl"
    assert rse._normalize_orchestrator_output(seeds, raw_path, out2, "mymodel") == 1
