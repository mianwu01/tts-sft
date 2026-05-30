"""Simple aggregation metrics over per-example evaluation records."""
from __future__ import annotations

from typing import Iterable


def accuracy(records: Iterable[dict]) -> tuple[int, int, float]:
    """Compute (total, correct, accuracy) from records with a ``correct`` field."""
    total = 0
    correct = 0
    for r in records:
        total += 1
        if bool(r.get("correct")):
            correct += 1
    acc = correct / total if total else 0.0
    return total, correct, acc
