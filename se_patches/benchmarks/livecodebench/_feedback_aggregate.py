"""Additive `livecodebench-feedback-aggregate` recombination operator (vfonly config).

Frozen config (see tts-sft/docs/LCB_R2C_OLD_VISIBLE_FAILED_ONLY_CONFIRM.md):
  stay-close + top-level "feedback only for failed candidates" note + CHECK-bearing V2-concise
  feedback ONLY for candidates with a visible PUBLIC/sample-test failure + NO block for all_pass.

Public/sample execution ONLY for feedback (hidden tests never touched here). Self-contained and
fully guarded: any error falls back to a no-feedback stay-close prompt so the SE loop never breaks.
The ORIGINAL `livecodebench-aggregate` operator is untouched; this is a separate registration selected
only when the config sets `recombination: livecodebench-feedback-aggregate`.

Env vars (set by the launcher):
  LCB_FB_SEED    seed JSONL with {id, question, ...} (maps the SE `query` text -> problem id)
  LCB_FB_PUBLIC  data/filtered/lcbv6_public_tests.jsonl ({id, public_tests}) — PUBLIC tests only
  LCB_FB_HARNESS absolute path to scripts/lcb_public_probe_harness.py
"""
from __future__ import annotations
import hashlib, json, os, re, subprocess, sys, tempfile, threading
from concurrent.futures import ThreadPoolExecutor

_LOG_LOCK = threading.Lock()


def _log(rec: dict):
    """Append one audit record per recombination call to LCB_FB_LOG (guarded; never raises)."""
    path = os.environ.get("LCB_FB_LOG")
    if not path:
        return
    try:
        with _LOG_LOCK, open(path, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass

_STAYCLOSE_TOP = """You are given a competitive programming problem, several candidate solutions, and visible execution feedback for the candidates that failed public/sample execution.

Some candidate solutions may be incorrect. Visible execution feedback is provided only for candidates that failed public/sample execution. Candidates without a feedback block are not guaranteed to be correct; they simply have no visible failure signal. Use visible failures as evidence of bugs, but do not overfit only to the shown public/sample tests. Hidden tests are not available.

Your task is to synthesize one correct Python solution.

Correctness is the primary goal. However, to the extent possible, keep the final solution close to the candidate attempts. Prefer repairing, combining, and minimally modifying useful parts of the candidate solutions over writing a completely different solution from scratch. Only deviate substantially from the candidate attempts if their approaches are clearly flawed.

Do not blindly trust any single candidate or any single feedback item. Reason about the full problem constraints.

Return only one complete Python code block enclosed with triple backticks. Do not include explanation outside the code block.

Problem:
{problem}

Candidate solutions and visible feedback:
{blocks}
Now write one improved solution. Return only a single Python code block enclosed with triple backticks."""

_STATE = {"q2pub": None, "by_problem": None, "q2id": None, "prob2id": None}
_EXEC_CACHE: dict[str, dict] = {}


def _load_lookup():
    id2pub = {}
    with open(os.environ["LCB_FB_PUBLIC"]) as f:
        for line in f:
            r = json.loads(line); id2pub[r["id"]] = r["public_tests"]
    q2pub, by_problem, q2id, prob2id = {}, {}, {}, {}
    with open(os.environ["LCB_FB_SEED"]) as f:
        for line in f:
            r = json.loads(line)
            pid = r.get("id")
            if r.get("question"):
                q2id[r["question"]] = pid
            if r.get("problem"):
                prob2id[r["problem"]] = pid
            pub = id2pub.get(pid)
            if pub is None:
                continue
            if r.get("question"):
                q2pub[r["question"]] = pub
            if r.get("problem"):
                by_problem[r["problem"]] = pub  # fallback: raw problem text is a substring of `query`
    return q2pub, by_problem, q2id, prob2id


def _ensure_lookup():
    if _STATE["q2pub"] is None:
        _STATE["q2pub"], _STATE["by_problem"], _STATE["q2id"], _STATE["prob2id"] = _load_lookup()


def _tests_for(query: str):
    _ensure_lookup()
    pub = _STATE["q2pub"].get(query)
    if pub is not None:
        return pub
    for prob, p in _STATE["by_problem"].items():  # robust fallback (≤ subset size)
        if prob and prob in query:
            return p
    return None


def _id_for(query: str):
    _ensure_lookup()
    pid = _STATE["q2id"].get(query)
    if pid is not None:
        return pid
    for prob, pid in _STATE["prob2id"].items():
        if prob and prob in query:
            return pid
    return None


def _load_grader_extract():
    """Import the OFFLINE GRADER's extract_code so operator and grader agree on what counts as code.
    Located via LCB_FB_HARNESS's directory (tts-sft/scripts). Guarded: returns None on any failure."""
    try:
        import importlib.util
        sdir = os.path.dirname(os.environ.get("LCB_FB_HARNESS", ""))
        spec = importlib.util.spec_from_file_location(
            "lcb_fb_grader_extract", os.path.join(sdir, "eval_lcbv6_calibration.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.extract_code
    except Exception:  # noqa: BLE001
        return None


_GRADER_EXTRACT = _load_grader_extract()
# Fallback: VERBATIM copy of the grader's _CODE_BLOCK regex (eval_lcbv6_calibration.py:34) — keep in sync.
_CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n?(.*?)```", re.DOTALL)


def _extract_code(text: str) -> str:
    if _GRADER_EXTRACT is not None:
        try:
            return (_GRADER_EXTRACT(text) or "").strip()
        except Exception:  # noqa: BLE001
            pass
    blocks = _CODE_BLOCK.findall(text or "")
    return blocks[-1].strip() if blocks else ""


def _public_result(code: str, tests_json: str) -> dict:
    key = hashlib.md5((code + "\x00" + tests_json).encode("utf-8", "ignore")).hexdigest()
    if key in _EXEC_CACHE:
        return _EXEC_CACHE[key]
    cp = tp = None
    try:
        n = len(json.loads(tests_json)["inputs"])
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as cf:
            cf.write(code); cp = cf.name
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write(tests_json); tp = tf.name
        p = subprocess.run([sys.executable, os.environ["LCB_FB_HARNESS"], cp, tp],
                           capture_output=True, text=True, timeout=min(n * 6 + 20, 120))
        res = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        res = {"category": "unknown", "first_fail": None}
    finally:
        for x in (cp, tp):
            if x:
                try: os.unlink(x)
                except OSError: pass
    _EXEC_CACHE[key] = res
    return res


def _trunc(s, n=400):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[:n] + " …[truncated]"


def _v2_block(pub: dict):
    """CHECK-bearing V2-concise block for visible-failed candidates; None for all_pass / no-signal."""
    cat = pub.get("category"); ff = pub.get("first_fail")
    head = ("Visible execution feedback:\nSTATUS: {st}\n\nOBSERVED:\n{ob}\n\nDETAIL:\n{dt}\n\nCHECK:\n"
            "Use this visible execution result to identify possible bugs, but do not overfit only to the "
            "shown public/sample test. Hidden tests are not available.")
    if cat == "wrong_answer" and ff:
        return head.format(st="wrong_answer", ob="A shown public/sample test failed.",
                           dt=f"Input:\n{_trunc(ff.get('input'))}\nExpected output:\n{_trunc(ff.get('expected'))}\n"
                              f"Actual output:\n{_trunc(ff.get('actual'))}")
    if cat in ("runtime_error", "no_callable") and ff:
        return head.format(st="runtime_error", ob="The program raised an error on a shown test.",
                           dt=f"Error:\n{_trunc(ff.get('error'), 300)}")
    if cat == "compile_error" and ff:
        return head.format(st="compile_error", ob="The program failed to compile/parse.",
                           dt=f"Error:\n{_trunc(ff.get('error'), 300)}")
    if cat == "timeout":
        return head.format(st="timeout", ob="The program timed out on a shown public/sample test.",
                           dt="The program did not finish within the time limit on a shown test.")
    return None  # all_pass / unknown -> NO block


def feedback_aggregate(query, candidates, **kwargs):
    if not candidates:
        return query  # loop 0 (matches the original operator's empty-candidate behaviour)
    try:
        tests = _tests_for(query)

        def assess(c):
            """Return (category, feedback_block_or_None) for one parent candidate."""
            if tests is None:
                return ("no_tests", None)  # lookup miss -> no block (audited via tests_found=False)
            code = _extract_code(c)
            if not code:
                return ("no_code", _v2_block({"category": "compile_error",
                        "first_fail": {"error": "No extractable Python code block."}}))
            pub = _public_result(code, tests)
            return (pub.get("category"), _v2_block(pub))

        with ThreadPoolExecutor(max_workers=4) as ex:
            assessed = list(ex.map(assess, candidates))
        parts, n_blocks = [], 0
        for j, (c, (cat, fb)) in enumerate(zip(candidates, assessed), 1):
            parts.append(f"\n---- Solution {j} ----\n{(c or '').strip()}\n")
            if fb is not None:
                parts.append(f"---- Visible feedback on Solution {j} ----\n{fb}\n"); n_blocks += 1
        cats = [a[0] for a in assessed]
        _log({"id": _id_for(query), "n_candidates": len(candidates), "categories": cats,
              "n_feedback_blocks": n_blocks, "n_allpass_omitted": cats.count("all_pass"),
              "tests_found": tests is not None, "fallback": False})
        return _STAYCLOSE_TOP.format(problem=query, blocks="".join(parts))
    except Exception as e:  # noqa: BLE001 — never break the SE loop; fall back to stay-close, no feedback
        _log({"id": _id_for(query) if candidates else None, "n_candidates": len(candidates),
              "fallback": True, "error": f"{type(e).__name__}: {e}"})
        parts = [f"\n---- Solution {j} ----\n{(c or '').strip()}\n" for j, c in enumerate(candidates, 1)]
        return _STAYCLOSE_TOP.format(problem=query, blocks="".join(parts))
