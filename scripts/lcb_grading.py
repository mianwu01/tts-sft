#!/usr/bin/env python3
"""P5 grading hardening: shared subprocess-exec wrapper with a PERSISTENT code-hash→verdict cache and
best-of-N retry on timeout-category failures.

Why: hidden grading uses per-test SIGALRM; candidates near the limit flip pass/fail with machine load
(observed ±1–2 problems per pass on 126). Retrying ONLY timeout-category failures removes load flakes
(a candidate that times out on every attempt stays failed); the cache makes repeated passes consistent
and fast. Defaults keep the historical TLE (6 s/test) so numbers stay comparable; pass tle=10.0 for
hardened reruns. The canonical score_se_subset.py pipeline is intentionally NOT modified (cross-node
comparability) — use this in probes/ad-hoc graders.

Usage:
    from lcb_grading import GradingCache, run_harness_cached
    cache = GradingCache("outputs/grading_cache/hidden.jsonl")
    v = run_harness_cached(HARNESS, code, tests_json, n_tests, cache=cache)   # {"passed":bool,...}
"""
from __future__ import annotations
import hashlib, json, os, subprocess, sys, tempfile, threading
from pathlib import Path

_TIMEOUT_MARKERS = ("timeout", "tle", "timeouterror", "timeoutexpired")


def _is_timeout_verdict(v: dict | None) -> bool:
    if v is None:
        return True  # parent-level harness timeout
    err = str(v.get("error", "")) + str(v.get("category", ""))
    return any(m in err.lower() for m in _TIMEOUT_MARKERS)


class GradingCache:
    """Append-only JSONL cache: key -> verdict dict. Thread-safe; survives across passes/scripts."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._d: dict[str, dict] = {}
        if self.path.exists():
            for line in self.path.open():
                try:
                    r = json.loads(line)
                    self._d[r["k"]] = r["v"]
                except Exception:  # noqa: BLE001
                    continue

    def get(self, k):
        return self._d.get(k)

    def put(self, k, v):
        with self._lock:
            if k in self._d:
                return
            self._d[k] = v
            with self.path.open("a") as f:
                f.write(json.dumps({"k": k, "v": v}, ensure_ascii=False) + "\n")

    def __len__(self):
        return len(self._d)


def cache_key(harness, code: str, tests_json: str, tl: float) -> str:
    h = hashlib.md5()
    for part in (str(harness), code or "", tests_json, f"{tl}"):
        h.update(part.encode("utf-8", "ignore")); h.update(b"\x00")
    return h.hexdigest()


def _run_once(harness, code: str, tests_json: str, n_tests: int, tl: float) -> dict | None:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as cf:
        cf.write(code); cp = cf.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        tf.write(tests_json); tp = tf.name
    try:
        p = subprocess.run([sys.executable, str(harness), cp, tp], capture_output=True, text=True,
                           timeout=min(n_tests * tl + 20, 300))
        out = p.stdout.strip().splitlines()
        return json.loads(out[-1]) if out else None
    except Exception:  # noqa: BLE001  (incl. parent TimeoutExpired)
        return None
    finally:
        Path(cp).unlink(missing_ok=True); Path(tp).unlink(missing_ok=True)


def run_harness_cached(harness, code: str, tests_json: str, n_tests: int, *,
                       tl: float = 6.0, retries_on_timeout: int = 1,
                       cache: GradingCache | None = None) -> dict | None:
    """Run a candidate through a harness with caching + timeout-only retry.

    Retry rule: a non-timeout verdict (pass OR deterministic fail) is final on first attempt.
    A timeout-category failure is retried up to `retries_on_timeout` times; passing any attempt
    counts as pass (load flake), timing out every attempt stays a timeout failure.
    """
    if not code:
        return {"passed": False, "error": "no_code", "category": "no_code"}
    k = cache_key(harness, code, tests_json, tl) if cache is not None else None
    if cache is not None:
        hit = cache.get(k)
        if hit is not None:
            return hit
    v = _run_once(harness, code, tests_json, n_tests, tl)
    attempts = 0
    while _is_timeout_verdict(v) and not (v or {}).get("passed") and attempts < retries_on_timeout:
        attempts += 1
        v2 = _run_once(harness, code, tests_json, n_tests, tl)
        if v2 is not None and (v2.get("passed") or not _is_timeout_verdict(v2)):
            v = v2  # flake resolved (pass, or a deterministic non-timeout failure)
            break
        v = v2 or v
    if v is None:
        v = {"passed": False, "error": "harness_timeout", "category": "timeout"}
    if cache is not None:
        cache.put(k, v)
    return v
