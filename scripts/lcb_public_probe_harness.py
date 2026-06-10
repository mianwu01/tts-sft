#!/usr/bin/env python3
"""Run a candidate against PUBLIC (non-hidden) LCB tests and return DETAILED, structured results
for building non-leaky execution feedback (V2/V3/V4 in the LCB feedback-repair probe).

Subprocess-isolated (untrusted code), per-test SIGALRM timeout. NEVER touches hidden tests.

argv: <code_file> <public_tests_json_file>   (tests json = {inputs,outputs,testtype,fn_name,time_limit})
stdout (last line) JSON: {"category","n_pass","n_total","first_fail":{idx,input,expected,actual,error}|null}
category in: compile_error | runtime_error | wrong_answer | timeout | all_pass | no_callable
"""
from __future__ import annotations
import io, json, signal, sys


def _alarm(sec):
    def h(s, f): raise TimeoutError(f"TLE {sec}s")
    signal.signal(signal.SIGALRM, h); signal.setitimer(signal.ITIMER_REAL, max(0.1, sec))
def _cancel(): signal.setitimer(signal.ITIMER_REAL, 0)
def _norm(s): return "\n".join(l.rstrip() for l in str(s).strip().split("\n"))


def run_stdin(code, inputs, outputs, tl):
    # compile once to detect syntax/compile errors up front
    try:
        compiled = compile(code, "<candidate>", "exec")
    except Exception as e:  # noqa: BLE001
        return ("compile_error", 0, len(inputs), {"idx": -1, "input": None, "expected": None, "actual": None, "error": f"{type(e).__name__}: {e}"})
    npass = 0
    for i, (inp, exp) in enumerate(zip(inputs, outputs)):
        stdin = inp if isinstance(inp, str) else "\n".join(str(x) for x in inp)
        want = _norm(exp if isinstance(exp, str) else str(exp))
        oi, oo = sys.stdin, sys.stdout
        sys.stdin = io.StringIO(stdin); buf = io.StringIO(); sys.stdout = buf
        try:
            _alarm(tl)
            try:
                exec(compiled, {"__name__": "__main__"})
            except SystemExit:
                pass
            _cancel()
        except TimeoutError as e:
            _cancel(); sys.stdin, sys.stdout = oi, oo
            return ("timeout", npass, len(inputs), {"idx": i, "input": stdin, "expected": want, "actual": None, "error": str(e)})
        except Exception as e:  # noqa: BLE001
            _cancel(); sys.stdin, sys.stdout = oi, oo
            return ("runtime_error", npass, len(inputs), {"idx": i, "input": stdin, "expected": want, "actual": None, "error": f"{type(e).__name__}: {e}"})
        finally:
            sys.stdin, sys.stdout = oi, oo
        got = _norm(buf.getvalue())
        if got == want:
            npass += 1
        else:
            return ("wrong_answer", npass, len(inputs), {"idx": i, "input": stdin, "expected": want, "actual": got[:2000]})
    return ("all_pass", npass, len(inputs), None)


def run_functional(code, fn_name, inputs, outputs, tl):
    g = {"__name__": "__h__"}
    try:
        exec(compile(code, "<candidate>", "exec"), g)
    except Exception as e:  # noqa: BLE001
        return ("compile_error", 0, len(inputs), {"idx": -1, "input": None, "expected": None, "actual": None, "error": f"{type(e).__name__}: {e}"})
    def resolve():
        if "Solution" in g:
            try: return getattr(g["Solution"](), fn_name)
            except Exception: return None
        return g.get(fn_name) if callable(g.get(fn_name)) else None
    if resolve() is None:
        return ("no_callable", 0, len(inputs), {"idx": -1, "input": None, "expected": None, "actual": None, "error": f"no callable {fn_name}"})
    npass = 0
    for i, (inp, exp) in enumerate(zip(inputs, outputs)):
        try:
            args = [json.loads(x) for x in (inp.split("\n") if isinstance(inp, str) else list(inp))]
        except Exception:
            args = [inp]
        try:
            want = json.loads(exp) if isinstance(exp, str) else exp
        except Exception:
            want = exp
        try:
            fn = resolve(); _alarm(tl); got = fn(*args); _cancel()
        except TimeoutError as e:
            _cancel(); return ("timeout", npass, len(inputs), {"idx": i, "input": str(inp), "expected": str(want), "actual": None, "error": str(e)})
        except Exception as e:  # noqa: BLE001
            _cancel(); return ("runtime_error", npass, len(inputs), {"idx": i, "input": str(inp), "expected": str(want), "actual": None, "error": f"{type(e).__name__}: {e}"})
        if got == want or str(got) == str(want):
            npass += 1
        else:
            return ("wrong_answer", npass, len(inputs), {"idx": i, "input": str(inp), "expected": str(want), "actual": str(got)[:2000]})
    return ("all_pass", npass, len(inputs), None)


def main():
    code = open(sys.argv[1]).read()
    t = json.load(open(sys.argv[2]))
    inp, out = t["inputs"], t["outputs"]; tl = float(t.get("time_limit", 6))
    if t.get("testtype") == "functional" and t.get("fn_name"):
        cat, npass, ntot, ff = run_functional(code, t["fn_name"], inp, out, tl)
    else:
        cat, npass, ntot, ff = run_stdin(code, inp, out, tl)
    print(json.dumps({"category": cat, "n_pass": npass, "n_total": ntot, "first_fail": ff}, ensure_ascii=False))


if __name__ == "__main__":
    main()
