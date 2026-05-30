"""Smoke tests for scripts/convert_se_to_sft.py helpers.

The script is invoked as a CLI in real use; here we import its helpers and
test the format-detection / response-picking logic directly.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "convert_se_to_sft.py"


@pytest.fixture(scope="module")
def converter():
    """Import the script as a module (it's not a package)."""
    spec = importlib.util.spec_from_file_location("convert_se_to_sft", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["convert_se_to_sft"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_get_dotted_simple(converter):
    assert converter._get_dotted({"a": 1}, "a") == 1
    assert converter._get_dotted({"a": {"b": 2}}, "a.b") == 2
    assert converter._get_dotted({"a": 1}, "a.b") is None
    assert converter._get_dotted({"a": 1}, "missing") is None


def test_first_string_prefers_order(converter):
    rec = {"final_response": "good", "response": "fallback"}
    assert converter._first_string(rec, ["final_response", "response"]) == "good"


def test_first_string_skips_empty(converter):
    rec = {"final_response": "  ", "response": "real"}
    assert converter._first_string(rec, ["final_response", "response"]) == "real"


def test_detect_format_raw_json(converter, tmp_path: Path):
    p = tmp_path / "raw.json"
    p.write_text(json.dumps({"run_id": "x", "problems": [{"orig_prompt": "q", "candidates": ["c"]}]}), encoding="utf-8")
    assert converter._detect_format(p) == "raw_json"


def test_detect_format_jsonl(converter, tmp_path: Path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"id": "1", "question": "q", "final_response": "r"}\n', encoding="utf-8")
    assert converter._detect_format(p) == "jsonl"


def test_extract_response_direct_key(converter):
    rec = {"final_response": "the answer is \\boxed{42}"}
    out = converter._extract_response(
        rec, converter.DEFAULT_RESPONSE_KEYS, "first", None,
    )
    assert out == "the answer is \\boxed{42}"


def test_extract_response_from_candidates(converter):
    rec = {"candidates": ["first one", "second one"]}
    out = converter._extract_response(rec, converter.DEFAULT_RESPONSE_KEYS, "first", None)
    assert out == "first one"

    out_last = converter._extract_response(rec, converter.DEFAULT_RESPONSE_KEYS, "last", None)
    assert out_last == "second one"

    out_longest = converter._extract_response(
        rec, converter.DEFAULT_RESPONSE_KEYS, "longest", None,
    )
    assert out_longest == "second one"


def test_extract_response_candidate_index(converter):
    rec = {"candidates": ["zero", "one", "two"]}
    assert converter._extract_response(rec, converter.DEFAULT_RESPONSE_KEYS, "first", 1) == "one"
    assert converter._extract_response(rec, converter.DEFAULT_RESPONSE_KEYS, "first", 99) is None


def test_extract_response_dotted_fallback(converter):
    rec = {"result": {"final_response": "deep"}}
    out = converter._extract_response(rec, converter.DEFAULT_RESPONSE_KEYS, "first", None)
    assert out == "deep"


def test_extract_response_missing_returns_none(converter):
    rec = {"id": "x", "question": "q"}
    out = converter._extract_response(rec, converter.DEFAULT_RESPONSE_KEYS, "first", None)
    assert out is None
