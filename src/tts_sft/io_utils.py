"""I/O helpers for JSONL and YAML files."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable, Iterator

logger = logging.getLogger(__name__)


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    """Yield records from a JSONL file, one dict per line.

    Blank lines are skipped. Lines that fail to parse raise json.JSONDecodeError
    with the offending line number for easier debugging.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise json.JSONDecodeError(
                    f"{path}:{line_num}: {e.msg}", e.doc, e.pos
                ) from None


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Load all records from a JSONL file into a list."""
    return list(iter_jsonl(path))


def write_jsonl(
    path: str | Path,
    records: Iterable[dict[str, Any]],
    *,
    append: bool = False,
) -> int:
    """Write records to a JSONL file. Returns the number written.

    The parent directory is created if it does not exist.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    n = 0
    with path.open(mode, encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False))
            f.write("\n")
            n += 1
    return n


def append_jsonl(path: str | Path, record: dict[str, Any]) -> None:
    """Append a single record to a JSONL file, flushing immediately.

    Useful for streaming generation outputs where each example may be
    expensive and resume-on-crash matters.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False))
        f.write("\n")
        f.flush()


def read_existing_ids(path: str | Path, id_field: str = "id") -> set[str]:
    """Return the set of ids already present in a JSONL file.

    Returns an empty set if the file does not exist. Records without the
    id field are skipped.
    """
    path = Path(path)
    if not path.exists():
        return set()
    ids: set[str] = set()
    for r in iter_jsonl(path):
        v = r.get(id_field)
        if v is not None:
            ids.add(str(v))
    return ids


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file into a dict. Returns {} if the file is empty."""
    import yaml

    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}
