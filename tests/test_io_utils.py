"""Tests for tts_sft.io_utils."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tts_sft.io_utils import (
    append_jsonl,
    iter_jsonl,
    load_jsonl,
    load_yaml,
    read_existing_ids,
    write_jsonl,
)


def test_write_then_load_roundtrip(tmp_path: Path):
    path = tmp_path / "out.jsonl"
    records = [{"id": "a", "x": 1}, {"id": "b", "x": 2}]
    n = write_jsonl(path, records)
    assert n == 2
    assert load_jsonl(path) == records


def test_write_creates_parent_dirs(tmp_path: Path):
    path = tmp_path / "deep" / "nested" / "out.jsonl"
    write_jsonl(path, [{"id": "1"}])
    assert path.exists()


def test_iter_jsonl_skips_blank_lines(tmp_path: Path):
    path = tmp_path / "x.jsonl"
    path.write_text('{"a": 1}\n\n{"a": 2}\n   \n', encoding="utf-8")
    assert list(iter_jsonl(path)) == [{"a": 1}, {"a": 2}]


def test_iter_jsonl_unicode(tmp_path: Path):
    path = tmp_path / "u.jsonl"
    write_jsonl(path, [{"q": "π ≈ 3.14"}])
    assert load_jsonl(path) == [{"q": "π ≈ 3.14"}]


def test_iter_jsonl_invalid_raises_with_line_info(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"ok": 1}\n{not json}\n', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        list(iter_jsonl(path))


def test_append_jsonl(tmp_path: Path):
    path = tmp_path / "a.jsonl"
    append_jsonl(path, {"id": "1"})
    append_jsonl(path, {"id": "2"})
    assert load_jsonl(path) == [{"id": "1"}, {"id": "2"}]


def test_write_jsonl_append(tmp_path: Path):
    path = tmp_path / "a.jsonl"
    write_jsonl(path, [{"id": "1"}])
    write_jsonl(path, [{"id": "2"}], append=True)
    assert load_jsonl(path) == [{"id": "1"}, {"id": "2"}]


def test_read_existing_ids(tmp_path: Path):
    path = tmp_path / "x.jsonl"
    write_jsonl(path, [{"id": "a"}, {"id": "b"}, {"id": "c"}])
    assert read_existing_ids(path) == {"a", "b", "c"}


def test_read_existing_ids_missing_file(tmp_path: Path):
    assert read_existing_ids(tmp_path / "nope.jsonl") == set()


def test_read_existing_ids_skips_records_without_id(tmp_path: Path):
    path = tmp_path / "x.jsonl"
    write_jsonl(path, [{"id": "a"}, {"foo": "no-id"}, {"id": "b"}])
    assert read_existing_ids(path) == {"a", "b"}


def test_read_existing_ids_coerces_to_str(tmp_path: Path):
    path = tmp_path / "x.jsonl"
    write_jsonl(path, [{"id": 1}, {"id": "2"}])
    assert read_existing_ids(path) == {"1", "2"}


def test_load_yaml(tmp_path: Path):
    path = tmp_path / "c.yaml"
    path.write_text("foo: 1\nbar: [a, b]\n", encoding="utf-8")
    assert load_yaml(path) == {"foo": 1, "bar": ["a", "b"]}


def test_load_yaml_empty(tmp_path: Path):
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    assert load_yaml(path) == {}
