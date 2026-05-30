"""Extract and normalize final math answers from model outputs.

Designed for v1: regex-based extraction and shallow string normalization.
Symbolic equivalence (e.g., sympy) is intentionally out of scope.
"""
from __future__ import annotations

import re

_FINAL_ANSWER_PATTERNS = [
    re.compile(r"final\s*answer\s*[:\-]\s*(.+)", re.IGNORECASE),
    re.compile(r"the\s+answer\s+is\s*[:\-]?\s*(.+)", re.IGNORECASE),
    re.compile(r"answer\s*[:\-]\s*(.+)", re.IGNORECASE),
]

_TRAILING_PUNCT = ".,;:!?"


def _find_all_boxed(text: str) -> list[str]:
    """Return every brace-matched ``\\boxed{...}`` payload in order of appearance."""
    results: list[str] = []
    i = 0
    needle = "\\boxed{"
    while True:
        start = text.find(needle, i)
        if start == -1:
            break
        depth = 1
        j = start + len(needle)
        while j < len(text) and depth > 0:
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if depth == 0:
            results.append(text[start + len(needle) : j])
            i = j + 1
        else:
            # unbalanced — bail
            break
    return results


def extract_boxed_answer(text: str) -> str | None:
    """Return the contents of the LAST ``\\boxed{...}`` in text, or None.

    Brace matching is balanced, so nested braces (e.g., ``\\frac{1}{2}``) are
    preserved correctly.
    """
    if not text:
        return None
    matches = _find_all_boxed(text)
    if not matches:
        return None
    return matches[-1]


def extract_final_answer(text: str) -> str | None:
    """Best-effort extraction of a final answer string.

    Order of preference:
        1. Last ``\\boxed{...}`` payload.
        2. Trailing text after "Final answer:", "The answer is", or "Answer:".

    Returns None when no candidate is found.
    """
    if not text:
        return None

    boxed = extract_boxed_answer(text)
    if boxed is not None:
        return boxed

    # Search the tail of the text first, since the final answer is usually
    # near the end.
    for pat in _FINAL_ANSWER_PATTERNS:
        last = None
        for m in pat.finditer(text):
            last = m
        if last is not None:
            tail = last.group(1).strip()
            # Cut at the next newline — keep the answer single-line.
            tail = tail.splitlines()[0].strip()
            if tail:
                return tail
    return None


def normalize_math_answer(ans: str | None) -> str:
    """Normalize an answer string for shallow exact-match comparison."""
    if ans is None:
        return ""
    s = str(ans).strip()

    # Strip surrounding dollar signs (LaTeX inline math).
    while s.startswith("$") and s.endswith("$") and len(s) >= 2:
        s = s[1:-1].strip()

    # Strip surrounding whitespace-only braces — sometimes models wrap a
    # final number in extra braces.
    while s.startswith("{") and s.endswith("}") and len(s) >= 2:
        inner = s[1:-1]
        if inner.count("{") == inner.count("}"):
            s = inner.strip()
        else:
            break

    # Drop simple trailing punctuation.
    while s and s[-1] in _TRAILING_PUNCT:
        s = s[:-1]

    s = s.strip()

    # Remove thousands separators inside pure-digit groups: "1,000" -> "1000",
    # but leave "(1, 2)" alone.
    s = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", s)

    # Collapse internal whitespace.
    s = re.sub(r"\s+", " ", s).strip()

    return s


def is_exact_match(pred: str | None, gold: str | None) -> bool:
    """Return True iff predicted and gold answers match after normalization."""
    p = normalize_math_answer(pred)
    g = normalize_math_answer(gold)
    if not g:
        return False
    if p == g:
        return True
    # Numeric equality fallback: "1000" == "1000.0", "1/2" stays string-only.
    try:
        return float(p) == float(g)
    except (ValueError, TypeError):
        return False
