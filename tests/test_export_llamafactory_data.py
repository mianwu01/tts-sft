"""Tests for scripts/export_llamafactory_data.py.

Imports the script as a module (it lives in scripts/, not in a package)
and exercises both the in-process helpers and the full CLI end-to-end
through ``subprocess`` for the overwrite/limit/help paths.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "export_llamafactory_data.py"


@pytest.fixture(scope="module")
def exporter():
    spec = importlib.util.spec_from_file_location("export_llamafactory_data", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["export_llamafactory_data"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


# ---------------------------------------------------------------------------
# Helper-level tests
# ---------------------------------------------------------------------------

class TestValidateMessages:
    def test_valid_pair(self, exporter):
        msgs = [{"role": "user", "content": "Q"}, {"role": "assistant", "content": "A"}]
        assert exporter._validate_messages(msgs) == ("Q", "A")

    def test_wrong_length(self, exporter):
        assert exporter._validate_messages([{"role": "user", "content": "Q"}]) is None
        msgs3 = [
            {"role": "system", "content": "S"},
            {"role": "user", "content": "Q"},
            {"role": "assistant", "content": "A"},
        ]
        assert exporter._validate_messages(msgs3) is None

    def test_wrong_roles(self, exporter):
        bad = [{"role": "assistant", "content": "A"}, {"role": "user", "content": "Q"}]
        assert exporter._validate_messages(bad) is None

    def test_empty_content(self, exporter):
        bad = [{"role": "user", "content": ""}, {"role": "assistant", "content": "A"}]
        assert exporter._validate_messages(bad) is None
        bad2 = [{"role": "user", "content": "Q"}, {"role": "assistant", "content": "   "}]
        assert exporter._validate_messages(bad2) is None

    def test_non_string_content(self, exporter):
        bad = [{"role": "user", "content": 123}, {"role": "assistant", "content": "A"}]
        assert exporter._validate_messages(bad) is None

    def test_not_a_list(self, exporter):
        assert exporter._validate_messages(None) is None
        assert exporter._validate_messages("nope") is None


class TestToShareGPTRecord:
    def test_carries_id_and_source(self, exporter):
        rec = {
            "id": "001",
            "messages": [
                {"role": "user", "content": "Q"},
                {"role": "assistant", "content": "A"},
            ],
            "source": "raw_self_sft",
        }
        out = exporter._to_sharegpt_record(rec, 0)
        assert out == {
            "conversations": [
                {"from": "human", "value": "Q"},
                {"from": "gpt", "value": "A"},
            ],
            "id": "001",
            "source": "raw_self_sft",
        }

    def test_synthesizes_id_when_missing(self, exporter):
        rec = {"messages": [
            {"role": "user", "content": "Q"},
            {"role": "assistant", "content": "A"},
        ]}
        out = exporter._to_sharegpt_record(rec, 7)
        assert out["id"] == "ex_000007"
        assert "source" not in out

    def test_returns_none_for_malformed(self, exporter):
        assert exporter._to_sharegpt_record({"messages": []}, 0) is None


# ---------------------------------------------------------------------------
# CLI-level integration tests
# ---------------------------------------------------------------------------

class TestCli:
    def _make_input(self, tmp_path: Path) -> Path:
        records = [
            {
                "id": "a1",
                "messages": [
                    {"role": "user", "content": "Solve: 2+2"},
                    {"role": "assistant", "content": "<think>add</think>\nAnswer: \\boxed{4}"},
                ],
                "source": "raw_self_sft",
            },
            {
                "id": "a2",
                "messages": [
                    {"role": "user", "content": "Solve: 3+3"},
                    {"role": "assistant", "content": "\\boxed{6}"},
                ],
                "source": "raw_self_sft",
            },
            # malformed — no assistant message
            {"id": "bad1", "messages": [{"role": "user", "content": "x"}], "source": "raw"},
            # malformed — empty messages
            {"id": "bad2", "messages": [], "source": "raw"},
            # malformed — empty assistant content
            {
                "id": "bad3",
                "messages": [
                    {"role": "user", "content": "Q"},
                    {"role": "assistant", "content": ""},
                ],
                "source": "raw",
            },
        ]
        in_path = tmp_path / "input.jsonl"
        _write_jsonl(in_path, records)
        return in_path

    def test_normal_conversion(self, tmp_path: Path):
        in_path = self._make_input(tmp_path)
        out_path = tmp_path / "out.json"
        proc = _run_cli([
            "--input", str(in_path),
            "--output", str(out_path),
            "--format", "sharegpt",
        ])
        assert proc.returncode == 0, proc.stderr
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["id"] == "a1"
        assert data[0]["conversations"][0] == {"from": "human", "value": "Solve: 2+2"}
        assert "raw_self_sft" == data[0]["source"]
        # Counts surface in stderr (logging.info goes to stderr by default).
        assert "input=5" in proc.stderr
        assert "converted=2" in proc.stderr
        assert "skipped=3" in proc.stderr

    def test_preserves_think_tags(self, tmp_path: Path):
        in_path = self._make_input(tmp_path)
        out_path = tmp_path / "out.json"
        _run_cli(["--input", str(in_path), "--output", str(out_path)])
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assistant = data[0]["conversations"][1]["value"]
        assert "<think>add</think>" in assistant
        assert assistant.startswith("<think>")

    def test_preserves_boxed(self, tmp_path: Path):
        in_path = self._make_input(tmp_path)
        out_path = tmp_path / "out.json"
        _run_cli(["--input", str(in_path), "--output", str(out_path)])
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert "\\boxed{4}" in data[0]["conversations"][1]["value"]
        assert "\\boxed{6}" in data[1]["conversations"][1]["value"]

    def test_limit_truncates(self, tmp_path: Path):
        in_path = self._make_input(tmp_path)
        out_path = tmp_path / "out.json"
        proc = _run_cli([
            "--input", str(in_path),
            "--output", str(out_path),
            "--limit", "1",
        ])
        assert proc.returncode == 0
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["id"] == "a1"

    def test_overwrite_refused_without_flag(self, tmp_path: Path):
        in_path = self._make_input(tmp_path)
        out_path = tmp_path / "out.json"
        out_path.write_text("pre-existing", encoding="utf-8")
        proc = _run_cli(["--input", str(in_path), "--output", str(out_path)])
        assert proc.returncode != 0
        assert "already exists" in proc.stderr
        # File untouched.
        assert out_path.read_text(encoding="utf-8") == "pre-existing"

    def test_overwrite_replaces_with_flag(self, tmp_path: Path):
        in_path = self._make_input(tmp_path)
        out_path = tmp_path / "out.json"
        out_path.write_text("pre-existing", encoding="utf-8")
        proc = _run_cli([
            "--input", str(in_path),
            "--output", str(out_path),
            "--overwrite",
        ])
        assert proc.returncode == 0
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert isinstance(data, list) and len(data) == 2

    def test_missing_input_exits_nonzero(self, tmp_path: Path):
        proc = _run_cli([
            "--input", str(tmp_path / "nope.jsonl"),
            "--output", str(tmp_path / "out.json"),
        ])
        assert proc.returncode == 2
        assert "does not exist" in proc.stderr

    def test_help(self):
        proc = _run_cli(["--help"])
        assert proc.returncode == 0
        assert "--format" in proc.stdout
        assert "sharegpt" in proc.stdout
