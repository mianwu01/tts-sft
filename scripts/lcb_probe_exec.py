#!/usr/bin/env python3
"""P1 step 2: run a candidate on PROBE INPUTS with NO expected outputs — capture raw behavior only
(stdout / function return / error / timeout). Used purely for cross-candidate disagreement detection;
no correctness judgement is made or implied. Subprocess-isolated, per-input SIGALRM.

argv: <code_file> <spec_json_file>   spec = {"inputs":[...], "testtype":"stdin"|"functional", "fn_name":""}
stdout (last line) JSON: {"results":[{"kind":"output"|"error"|"timeout","value":str}, ...]}
"""
from __future__ import annotations
import io, json, signal, sys


def _alarm(sec):
    def h(s, f): raise TimeoutError("TLE")
    signal.signal(signal.SIGALRM, h); signal.setitimer(signal.ITIMER_REAL, max(0.1, sec))
def _cancel(): signal.setitimer(signal.ITIMER_REAL, 0)
def _norm(s): return "\n".join(l.rstrip() for l in str(s).strip().split("\n"))


def run_stdin(code, inputs, tl):
    try:
        compiled = compile(code, "<candidate>", "exec")
    except Exception as e:  # noqa: BLE001
        return [{"kind": "error", "value": f"compile: {type(e).__name__}"} for _ in inputs]
    out = []
    for inp in inputs:
        oi, oo = sys.stdin, sys.stdout
        sys.stdin = io.StringIO(inp); buf = io.StringIO(); sys.stdout = buf
        try:
            _alarm(tl)
            try:
                exec(compiled, {"__name__": "__main__"})
            except SystemExit:
                pass
            _cancel()
            out.append({"kind": "output", "value": _norm(buf.getvalue())[:1000]})
        except TimeoutError:
            _cancel(); out.append({"kind": "timeout", "value": ""})
        except Exception as e:  # noqa: BLE001
            _cancel(); out.append({"kind": "error", "value": f"{type(e).__name__}"})
        finally:
            sys.stdin, sys.stdout = oi, oo
    return out


def run_functional(code, fn_name, inputs, tl):
    g = {"__name__": "__probe__"}
    try:
        exec(compile(code, "<candidate>", "exec"), g)
    except Exception as e:  # noqa: BLE001
        return [{"kind": "error", "value": f"compile: {type(e).__name__}"} for _ in inputs]
    def resolve():
        if "Solution" in g:
            try: return getattr(g["Solution"](), fn_name)
            except Exception: return None
        f = g.get(fn_name); return f if callable(f) else None
    if resolve() is None:
        return [{"kind": "error", "value": "no_callable"} for _ in inputs]
    out = []
    for inp in inputs:
        try:
            args = [json.loads(x) for x in str(inp).split("\n") if x.strip()]
        except Exception:
            args = [inp]
        try:
            fn = resolve(); _alarm(tl); res = fn(*args); _cancel()
            out.append({"kind": "output", "value": repr(res)[:1000]})
        except TimeoutError:
            _cancel(); out.append({"kind": "timeout", "value": ""})
        except Exception as e:  # noqa: BLE001
            _cancel(); out.append({"kind": "error", "value": f"{type(e).__name__}"})
    return out


def main():
    code = open(sys.argv[1]).read()
    spec = json.load(open(sys.argv[2]))
    inputs = spec["inputs"]; tl = float(spec.get("time_limit", 6))
    if spec.get("testtype") == "functional" and spec.get("fn_name"):
        res = run_functional(code, spec["fn_name"], inputs, tl)
    else:
        res = run_stdin(code, inputs, tl)
    print(json.dumps({"results": res}, ensure_ascii=False))


if __name__ == "__main__":
    main()
