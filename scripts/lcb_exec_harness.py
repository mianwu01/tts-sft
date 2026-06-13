#!/usr/bin/env python3
"""Single-sample LiveCodeBench execution harness (one subprocess per candidate).

Runs an extracted code candidate against a problem's hidden test suite and prints
a JSON verdict to stdout. Isolated in its own process so a crash / sys.exit / TLE
in untrusted model code is contained (the parent imposes an overall timeout too).

Usage:
  python lcb_exec_harness.py <code_file> <tests_json_file>

tests_json_file: {"inputs":[...], "outputs":[...], "testtype":"stdin"|"functional",
                  "fn_name":"...", "time_limit":int}
Verdict (stdout, last line): {"passed":bool,"error":"","n_passed":int,"n_total":int,
                              "first_fail":int}

Test semantics (standard LCB):
  * stdin (atcoder): feed input to stdin, run as __main__ script, compare stdout
    line-wise rstrip + overall strip.
  * functional (leetcode): each test `input` is newline-joined JSON args; parse each
    line with json.loads, call Solution().<fn_name>(*args) (or a bare global fn),
    json-compare against json.loads(output) with a float / list fallback.
"""
from __future__ import annotations

import io
import json
import signal
import sys


def _set_alarm(seconds: float) -> None:
    def _handler(signum, frame):
        raise TimeoutError(f"time limit exceeded ({seconds}s)")

    signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, max(0.1, seconds))


def _cancel_alarm() -> None:
    signal.setitimer(signal.ITIMER_REAL, 0)


def _norm_out(s: str) -> str:
    return "\n".join(line.rstrip() for line in str(s).strip().split("\n"))


def _eq(got, want) -> bool:
    if got == want:
        return True
    try:
        if abs(float(got) - float(want)) < 1e-6:
            return True
    except (TypeError, ValueError):
        pass
    try:
        if list(got) == list(want):
            return True
    except TypeError:
        pass
    return False


def run_stdin(code, inputs, outputs, tl):
    for i, (inp, exp) in enumerate(zip(inputs, outputs)):
        stdin_text = inp if isinstance(inp, str) else "\n".join(str(x) for x in inp)
        want = _norm_out(exp if isinstance(exp, str) else str(exp))
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin = io.StringIO(stdin_text)
        buf = io.StringIO()
        sys.stdout = buf
        try:
            _set_alarm(tl)
            try:
                exec(compile(code, "<candidate>", "exec"), {"__name__": "__main__"})
            except SystemExit:
                pass
            _cancel_alarm()
        except Exception as e:  # noqa: BLE001
            _cancel_alarm()
            sys.stdin, sys.stdout = old_in, old_out
            return False, f"{type(e).__name__}: {e}", i
        finally:
            sys.stdin, sys.stdout = old_in, old_out
        if _norm_out(buf.getvalue()) != want:
            return False, "wrong_answer", i
    return True, "", len(inputs)


def run_functional(code, fn_name, inputs, outputs, tl):
    g = {"__name__": "__lcb_harness__"}
    try:
        exec(compile(code, "<candidate>", "exec"), g)
    except Exception as e:  # noqa: BLE001
        return False, f"import_error: {type(e).__name__}: {e}", 0

    def resolve():
        if "Solution" in g:
            return getattr(g["Solution"](), fn_name)
        if fn_name in g and callable(g[fn_name]):
            return g[fn_name]
        return None

    if resolve() is None:
        return False, f"no_callable:{fn_name}", 0

    for i, (inp, exp) in enumerate(zip(inputs, outputs)):
        try:
            lines = inp.split("\n") if isinstance(inp, str) else list(inp)
            args = [json.loads(line) for line in lines]
        except Exception:  # noqa: BLE001
            args = [inp]
        try:
            want = json.loads(exp) if isinstance(exp, str) else exp
        except Exception:  # noqa: BLE001
            want = exp
        try:
            fn = resolve()  # fresh Solution() per test
            _set_alarm(tl)
            got = fn(*args)
            _cancel_alarm()
        except Exception as e:  # noqa: BLE001
            _cancel_alarm()
            return False, f"{type(e).__name__}: {e}", i
        if not _eq(got, want):
            return False, "wrong_answer", i
    return True, "", len(inputs)


def main() -> int:
    code = open(sys.argv[1]).read()
    tests = json.load(open(sys.argv[2]))
    inputs, outputs = tests["inputs"], tests["outputs"]
    tl = float(tests.get("time_limit", 6))
    testtype = tests.get("testtype", "stdin")
    fn_name = tests.get("fn_name", "")
    try:
        if testtype == "functional" and fn_name:
            passed, err, fail_idx = run_functional(code, fn_name, inputs, outputs, tl)
        else:
            passed, err, fail_idx = run_stdin(code, inputs, outputs, tl)
    except Exception as e:  # noqa: BLE001  (harness-level guard)
        passed, err, fail_idx = False, f"harness_error: {type(e).__name__}: {e}", -1
    n_total = len(inputs)
    n_passed = n_total if passed else max(0, fail_idx)
    print(json.dumps({
        "passed": passed, "error": err,
        "n_passed": n_passed, "n_total": n_total, "first_fail": fail_idx,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
