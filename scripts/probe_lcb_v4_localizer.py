#!/usr/bin/env python3
"""V4 localizer prompt-quality probe. Implements V2-concise deterministic feedback (no LLM) and
tests 3 short V4 localizer variants (V4a one-line, V4b PRESERVE/FIX/CHECK, V4c verifier-free one-line)
on the existing 26 case-study candidates. NO repair, NO recombination, NO in-loop runs. Public/sample
execution only for V2-concise + V4a/b inputs; hidden tests never used here (cases were pre-labelled).

Outputs: outputs/node1_lcb_v4_localizer_probe/{localizer_records.jsonl, summary.json}.
"""
from __future__ import annotations
import argparse, json, subprocess, sys, tempfile, threading, time, re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))
from eval_lcbv6_calibration import extract_code  # noqa: E402
PUB = _REPO / "scripts/lcb_public_probe_harness.py"


def trunc(s, n=400):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[:n] + " …[truncated]"


def v2_concise(pub):
    """Deterministic V2-concise block from public-exec result (non-leaky; never implies hidden failure)."""
    cat = pub["category"]; ff = pub.get("first_fail")
    if cat == "all_pass":
        return "Visible tests passed; no visible failure observed. Verify edge cases, constraints, and complexity."
    if cat == "wrong_answer" and ff:
        return ("Wrong answer on a public/sample test.\n"
                f"Input:\n{trunc(ff['input'])}\nExpected output:\n{trunc(ff['expected'])}\n"
                f"Actual output:\n{trunc(ff['actual'])}")
    if cat in ("runtime_error", "no_callable") and ff:
        return f"Runtime error on a public/sample test: {trunc(ff.get('error'), 300)}"
    if cat == "compile_error" and ff:
        return f"Compile/syntax error: {trunc(ff.get('error'), 300)}"
    if cat == "timeout":
        idx = (ff['idx'] + 1) if ff else '?'
        return f"Time limit exceeded on public/sample test {idx}."
    return "No public/sample execution signal available."


V4A = """You are localizing the bug in an INCORRECT competitive-programming candidate solution, using only the visible public/sample execution result. Output EXACTLY one line and nothing else:
LOCALIZATION: <one concise sentence naming the specific function/branch/edge case that is wrong, grounded in the visible execution result>
If there is no visible failure to ground a localization, output exactly:
LOCALIZATION: No visible bug localization available.
Rules: no corrected code, no full solution, no multi-line explanation, do not mention hidden tests.

Problem:
{problem}

Candidate code:
{code}

Visible public/sample execution feedback:
{v2}"""

V4B = """You are localizing the bug in an INCORRECT competitive-programming candidate solution, using only the visible public/sample execution result. Output EXACTLY these three lines and nothing else, each ONE short sentence:
PRESERVE: <which correct part to keep>
FIX: <the specific bug to fix, grounded in the visible execution result>
CHECK: <one concrete thing to verify>
If there is no visible failure, do not speculate: write 'FIX: No visible failure to localize.' and keep PRESERVE/CHECK generic and short.
Rules: no corrected code, no full solution, no extra lines, do not mention hidden tests.

Problem:
{problem}

Candidate code:
{code}

Visible public/sample execution feedback:
{v2}"""

V4C = """You are localizing the most likely bug in a competitive-programming candidate solution from the code alone (no execution available). Output EXACTLY one line and nothing else:
LOCALIZATION: <one concise sentence naming the most likely wrong function/branch/edge case>
Rules: no corrected code, no full solution, no multi-line explanation, do not mention tests.

Problem:
{problem}

Candidate code:
{code}"""


def parse_line(text, key):
    """Extract the first `KEY: ...` line from (post-think) text."""
    if not text:
        return None
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.upper().startswith(key + ":"):
            return ln[len(key) + 1:].strip()
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, default=Path("outputs/node1_lcb_feedback_case_study/cases.jsonl"))
    ap.add_argument("--outdir", type=Path, default=Path("outputs/node1_lcb_v4_localizer_probe"))
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Thinking-2507")
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--temp", type=float, default=0.1)
    ap.add_argument("--max-tokens", type=int, default=6144)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--concurrency", type=int, default=24)
    args = ap.parse_args()

    cases = [json.loads(l) for l in args.cases.open()]
    hidden = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_non_saturated.jsonl").open()}
    public = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_public_tests.jsonl").open()}
    # full candidate code by (pid, cand_idx)
    want = {(c["problem_id"], int(c["candidate_id"].rsplit("cand", 1)[-1])) for c in cases}
    code = {}
    for l in (_REPO / "outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/se.jsonl.loop_candidates.jsonl").open():
        r = json.loads(l)
        if r["loop_index"] == 0:
            k = (r["id"], int(r["candidate_id"].rsplit("cand", 1)[-1]))
            if k in want:
                code[k] = extract_code(r["full_response"] or "")

    def pub_exec(pid, ci):
        pj = public[pid]["public_tests"]; n = len(json.loads(pj)["inputs"])
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as cf:
            cf.write(code[(pid, ci)]); cp = cf.name
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write(pj); tp = tf.name
        try:
            p = subprocess.run([sys.executable, str(PUB), cp, tp], capture_output=True, text=True,
                               timeout=min(n * 6 + 20, 120))
            return json.loads(p.stdout.strip().splitlines()[-1])
        except Exception:
            return {"category": "unknown", "first_fail": None}
        finally:
            Path(cp).unlink(missing_ok=True); Path(tp).unlink(missing_ok=True)

    # build per-case V2-concise + record problem/code
    items = []
    for c in cases:
        pid = c["problem_id"]; ci = int(c["candidate_id"].rsplit("cand", 1)[-1])
        if (pid, ci) not in code:
            continue
        pub = pub_exec(pid, ci)
        items.append({"pid": pid, "ci": ci, "error_type": c["error_type"], "pub_cat": pub["category"],
                      "v2_concise": v2_concise(pub), "problem": hidden[pid]["problem"], "code": code[(pid, ci)]})
    print(f"{len(items)} cases; V4 calls = {len(items)*3}", flush=True)

    from openai import OpenAI
    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=7200)
    sem = threading.Semaphore(args.concurrency)
    def call(prompt):
        for attempt in range(4):
            try:
                with sem:
                    r = client.chat.completions.create(
                        model=args.model, messages=[{"role": "user", "content": prompt}],
                        temperature=args.temp, top_p=args.top_p, max_tokens=args.max_tokens,
                        seed=args.seed, extra_body={"top_k": args.top_k})
                ch = r.choices[0]; u = r.usage
                return {"text": ch.message.content or "", "ctok": getattr(u, "completion_tokens", 0),
                        "finish": ch.finish_reason}
            except Exception as e:  # noqa: BLE001
                time.sleep(min(20, 2 ** attempt)); last = e
        return {"text": "", "ctok": 0, "finish": "error", "err": str(last)}

    jobs = [(i, v) for i in range(len(items)) for v in ("V4a", "V4b", "V4c")]
    def do(job):
        i, v = job; it = items[i]
        if v == "V4a":
            p = V4A.format(problem=it["problem"], code=it["code"], v2=it["v2_concise"])
        elif v == "V4b":
            p = V4B.format(problem=it["problem"], code=it["code"], v2=it["v2_concise"])
        else:
            p = V4C.format(problem=it["problem"], code=it["code"])
        res = call(p)
        out = {"finish": res["finish"], "ctok": res["ctok"], "raw_tail": res["text"][-600:]}
        if v == "V4b":
            out["preserve"] = parse_line(res["text"], "PRESERVE")
            out["fix"] = parse_line(res["text"], "FIX")
            out["check"] = parse_line(res["text"], "CHECK")
            out["parsed"] = all(out[k] for k in ("preserve", "fix", "check"))
        else:
            out["localization"] = parse_line(res["text"], "LOCALIZATION")
            out["parsed"] = out["localization"] is not None
        return i, v, out

    results = {}
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        done = 0
        for i, v, out in ex.map(do, jobs):
            results.setdefault(i, {})[v] = out; done += 1
            if done % 20 == 0: print(f"  {done}/{len(jobs)}", flush=True)

    args.outdir.mkdir(parents=True, exist_ok=True)
    with (args.outdir / "localizer_records.jsonl").open("w") as f:
        for i, it in enumerate(items):
            f.write(json.dumps({**{k: it[k] for k in ("pid", "ci", "error_type", "pub_cat", "v2_concise")},
                                "code_excerpt": it["code"][:800], **results[i]}, ensure_ascii=False) + "\n")
    # summary: parse rate, length, all_pass handling
    summ = {"n_cases": len(items), "by_variant": {}}
    for v in ("V4a", "V4b", "V4c"):
        rs = [results[i][v] for i in range(len(items))]
        parsed = sum(r["parsed"] for r in rs)
        # "no localization available" rate on all_pass (should abstain for V4a/V4b)
        ap_idx = [i for i, it in enumerate(items) if it["pub_cat"] == "all_pass"]
        ap_abstain = 0
        for i in ap_idx:
            r = results[i][v]
            txt = (r.get("localization") or r.get("fix") or "").lower()
            if "no visible" in txt or "no localization" in txt or "no visible failure" in txt:
                ap_abstain += 1
        summ["by_variant"][v] = {"parsed_rate": round(parsed / len(items), 3), "parsed": parsed,
                                 "avg_ctok": round(sum(r["ctok"] for r in rs) / len(rs), 1),
                                 "truncated": sum(r["finish"] == "length" for r in rs),
                                 "all_pass_cases": len(ap_idx), "all_pass_abstained": ap_abstain}
    (args.outdir / "summary.json").write_text(json.dumps(summ, indent=2))
    print(json.dumps(summ, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
