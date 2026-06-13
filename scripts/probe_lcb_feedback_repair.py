#!/usr/bin/env python3
"""LCB feedback-quality probe: ONE-STEP repair of incorrect loop-0 candidates.

Question: given an incorrect LCB candidate, which NON-LEAKY feedback type best helps the model
repair it? Arms: V0_no_feedback, V1_verification_only, V2_raw_execution_feedback,
V3_structured_execution_feedback, V4_llm_diagnosis_feedback.

Leakage policy (strict): feedback is built ONLY from PUBLIC/sample-test execution
(data/filtered/lcbv6_public_tests.jsonl) — never hidden tests. Hidden tests (the seed `tests`)
are used ONLY to (a) select incorrect candidates and (b) grade the repaired code. They never appear
in any feedback or repair prompt.

Does NOT modify the SE orchestrator/baseline. Writes under outputs/node1_lcb_feedback_probe/.
"""
from __future__ import annotations
import argparse, json, subprocess, sys, tempfile, threading, time
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))
from eval_lcbv6_calibration import extract_code, HARNESS  # noqa: E402
PUB_HARNESS = _REPO / "scripts/lcb_public_probe_harness.py"
ARMS = ["V0_no_feedback", "V1_verification_only", "V2_raw_execution_feedback",
        "V3_structured_execution_feedback", "V4_llm_diagnosis_feedback"]

REPAIR_PROMPT = """You are given a programming problem, a candidate solution, and optional non-hidden feedback from public/sample execution.

Your task is to repair the candidate solution.

Rules:
- Correctness is the primary goal.
- Stay as close as possible to the candidate solution.
- Prefer repairing, preserving, and minimally modifying useful parts of the candidate code over rewriting from scratch.
- Use the feedback to identify the bug when feedback is provided.
- Do not overfit only to the shown public/sample test case.
- Return only one corrected Python code block.
- Do not include explanation outside the code.

Problem:
{problem}

Candidate solution:
{candidate_code}

Verification:
{verification}

Feedback:
{feedback}"""

V4_CRITIC = """You are reviewing an INCORRECT candidate solution to a programming problem, plus the result of running it on the public/sample tests. Give concise, actionable repair suggestions ONLY.

Constraints:
- Do NOT provide a full corrected solution or write replacement code.
- Do NOT solve the problem from scratch.
- Base your feedback ONLY on the candidate code and the public/sample execution result below.
- Keep it concise (2-5 short bullet points), in preserve / fix / check style.

Problem:
{problem}

Candidate code:
{code}

Public/sample execution result:
{exec_result}"""


def run_harness(harness, code, tests_json, n_tests, tl=6.0):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as cf:
        cf.write(code); cp = cf.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        tf.write(tests_json); tp = tf.name
    try:
        p = subprocess.run([sys.executable, str(harness), cp, tp], capture_output=True, text=True,
                           timeout=min(n_tests * tl + 20, 240))
    except subprocess.TimeoutExpired:
        return None
    finally:
        Path(cp).unlink(missing_ok=True); Path(tp).unlink(missing_ok=True)
    out = p.stdout.strip().splitlines()
    if not out:
        return None
    try:
        return json.loads(out[-1])
    except json.JSONDecodeError:
        return None


def hidden_pass(code, hidden_json, n):
    v = run_harness(HARNESS, code, hidden_json, n)
    return bool(v and v.get("passed"))


def public_result(code, public_json, n):
    return run_harness(PUB_HARNESS, code, public_json, n)  # {category,n_pass,n_total,first_fail}


def short(s, n=600):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[:n] + " …[truncated]"


def build_static_feedback(arm, pub):
    """V0/V1/V2/V3 feedback from public execution `pub` (non-leaky). Returns (verification, feedback)."""
    if arm == "V0_no_feedback":
        return "", ""
    verif = "This solution is incorrect."
    if arm == "V1_verification_only":
        return verif, ""
    cat = pub["category"] if pub else "unknown"
    ff = pub.get("first_fail") if pub else None
    if arm == "V2_raw_execution_feedback":
        if cat == "wrong_answer" and ff:
            fb = (f"Failed public test {ff['idx']+1}.\nInput:\n{short(ff['input'])}\n"
                  f"Expected output:\n{short(ff['expected'])}\nActual output:\n{short(ff['actual'])}")
        elif cat in ("runtime_error", "compile_error", "no_callable") and ff:
            fb = f"The program failed to run on public tests: {short(ff.get('error'),300)}"
        elif cat == "timeout":
            fb = f"The program exceeded the time limit on public test {(ff['idx']+1) if ff else '?'}."
        elif cat == "all_pass":
            fb = "The program passes all shown public/sample tests (no visible failure), but is still incorrect."
        else:
            fb = "No public/sample execution signal available."
        return verif, "Execution feedback:\n" + fb
    if arm == "V3_structured_execution_feedback":
        if cat == "wrong_answer" and ff:
            fb = ("Feedback type: wrong answer on public test\n"
                  f"Observed behavior: the program outputs {short(ff['actual'],120)} instead of "
                  f"{short(ff['expected'],120)} on a shown test.\n"
                  "Repair hint: inspect the code path responsible for this case; do not assume the shown test is the only failing case.")
        elif cat == "compile_error":
            fb = ("Feedback type: compile/syntax error\n"
                  f"Observed behavior: {short(ff.get('error') if ff else '',200)}\n"
                  "Repair hint: fix the syntax/definition error so the program runs, then re-check logic.")
        elif cat in ("runtime_error", "no_callable"):
            fb = ("Feedback type: runtime error\n"
                  f"Observed behavior: {short(ff.get('error') if ff else '',200)}\n"
                  "Repair hint: handle the failing operation/edge case causing the exception.")
        elif cat == "timeout":
            fb = ("Feedback type: timeout / TLE\nObserved behavior: the program exceeds the time limit on a shown test.\n"
                  "Repair hint: reduce algorithmic complexity or avoid redundant work; the approach may be too slow.")
        elif cat == "all_pass":
            fb = ("Feedback type: passes public tests but incorrect\n"
                  "Observed behavior: no visible failure on the shown tests.\n"
                  "Repair hint: the failing case is not among the shown tests; re-examine edge cases and constraints not covered by the samples.")
        else:
            fb = "Feedback type: unknown\nObserved behavior: no public execution signal.\nRepair hint: re-read the problem constraints."
        return verif, fb
    return verif, ""  # V4 handled separately (LLM)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-problems", type=int, default=24)
    ap.add_argument("--max-cands-per-problem", type=int, default=5)
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Thinking-2507")
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--repair-temp", type=float, default=0.1)
    ap.add_argument("--critic-temp", type=float, default=0.3)
    ap.add_argument("--max-tokens-repair", type=int, default=16384)
    ap.add_argument("--max-tokens-critic", type=int, default=1024)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--concurrency", type=int, default=24)
    ap.add_argument("--outdir", type=Path, default=Path("outputs/node1_lcb_feedback_probe"))
    args = ap.parse_args()

    hidden = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_non_saturated.jsonl").open()}
    public = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_public_tests.jsonl").open()}
    lc = _REPO / "outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/se.jsonl.loop_candidates.jsonl"
    # loop-0 candidates per problem
    cands = defaultdict(list)
    for line in lc.open():
        r = json.loads(line)
        if r["loop_index"] == 0:
            cands[r["id"]].append((int(r["candidate_id"].rsplit("cand", 1)[-1]), r["full_response"] or ""))

    # ---- selection: incorrect (hidden) loop-0 candidates with extractable code; categorize by public exec ----
    print("grading loop-0 candidates (hidden, for SELECTION only) + public categorization ...", flush=True)
    excluded = Counter()
    sel = defaultdict(list)  # pid -> [{idx,code,pub_cat,pub}]
    def assess(pid):
        h = hidden[pid]; nt_h = len(json.loads(h["tests"])["inputs"])
        pj = public[pid]["public_tests"]; nt_p = len(json.loads(pj)["inputs"])
        rows = []
        for idx, full in cands[pid]:
            code = extract_code(full)
            if not code:
                excluded["no_code"] += 1; continue
            if hidden_pass(code, h["tests"], nt_h):
                continue  # correct -> not a repair target
            pub = public_result(code, pj, nt_p)
            if pub is None:
                excluded["public_exec_failed"] += 1; continue
            rows.append({"idx": idx, "code": code, "pub_cat": pub["category"], "pub": pub})
        return pid, rows
    pids_all = sorted(cands)
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for pid, rows in ex.map(assess, pids_all):
            if rows:
                sel[pid] = rows
    # pick problems with >=4 incorrect candidates; stratify candidates by public category
    elig = [pid for pid in sorted(sel) if len(sel[pid]) >= 4][: args.n_problems]
    chosen = {}
    for pid in elig:
        rows = sel[pid]
        by_cat = defaultdict(list)
        for r in rows: by_cat[r["pub_cat"]].append(r)
        picked, ci = [], 0
        cats = sorted(by_cat)
        while len(picked) < args.max_cands_per_problem and any(by_cat.values()):
            cat = cats[ci % len(cats)]; ci += 1
            if by_cat[cat]: picked.append(by_cat[cat].pop(0))
        chosen[pid] = picked
    n_cand = sum(len(v) for v in chosen.values())
    catdist = Counter(r["pub_cat"] for v in chosen.values() for r in v)
    print(f"selected {len(chosen)} problems, {n_cand} incorrect candidates | public-category dist: {dict(catdist)}", flush=True)
    print(f"excluded: {dict(excluded)}", flush=True)

    # ---- model client ----
    from openai import OpenAI
    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=7200)
    sem = threading.Semaphore(args.concurrency)
    def call(prompt, max_tokens, temp, seed):
        for attempt in range(4):
            try:
                with sem:
                    r = client.chat.completions.create(
                        model=args.model, messages=[{"role": "user", "content": prompt}],
                        temperature=temp, top_p=args.top_p, max_tokens=max_tokens, seed=seed,
                        extra_body={"top_k": args.top_k})
                ch = r.choices[0]; u = r.usage
                return {"text": ch.message.content or "", "ptok": getattr(u, "prompt_tokens", 0),
                        "ctok": getattr(u, "completion_tokens", 0), "finish": ch.finish_reason}
            except Exception as e:  # noqa: BLE001
                time.sleep(min(20, 2 ** attempt)); last = e
        return {"text": "", "ptok": 0, "ctok": 0, "finish": "error", "err": str(last)}

    # ---- V4 critic feedback (LLM) ----
    flat = [(pid, r) for pid, rows in chosen.items() for r in rows]
    print(f"V4 critic feedback calls: {len(flat)}", flush=True)
    def exec_result_text(pub):
        cat = pub["category"]; ff = pub.get("first_fail")
        if cat == "all_pass": return "Passes all shown public/sample tests, but is known to be incorrect."
        if cat == "wrong_answer" and ff:
            return f"Wrong answer on public test {ff['idx']+1}. Input: {short(ff['input'],300)} Expected: {short(ff['expected'],150)} Actual: {short(ff['actual'],150)}"
        if ff and ff.get("error"): return f"{cat}: {short(ff['error'],300)}"
        return cat
    def do_v4(item):
        pid, r = item
        prompt = V4_CRITIC.format(problem=hidden[pid]["problem"], code=r["code"], exec_result=exec_result_text(r["pub"]))
        res = call(prompt, args.max_tokens_critic, args.critic_temp, args.seed)
        return (pid, r["idx"], res)
    v4 = {}
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for pid, idx, res in ex.map(do_v4, flat):
            v4[(pid, idx)] = res

    # ---- repair (5 arms) ----
    jobs = [(pid, r, arm) for pid, r in flat for arm in ARMS]
    print(f"repair calls: {len(jobs)} ({n_cand} candidates x 5 arms)", flush=True)
    def do_repair(job):
        pid, r, arm = job
        if arm == "V4_llm_diagnosis_feedback":
            verif = "This solution is incorrect."; fb = v4[(pid, r["idx"])]["text"]
        else:
            verif, fb = build_static_feedback(arm, r["pub"])
        prompt = REPAIR_PROMPT.format(problem=hidden[pid]["problem"], candidate_code=r["code"],
                                      verification=verif or "(none)", feedback=fb or "(none)")
        res = call(prompt, args.max_tokens_repair, args.repair_temp, args.seed)
        rcode = extract_code(res["text"])
        h = hidden[pid]; nt_h = len(json.loads(h["tests"])["inputs"])
        pj = public[pid]["public_tests"]; nt_p = len(json.loads(pj)["inputs"])
        ok = bool(rcode) and hidden_pass(rcode, h["tests"], nt_h)
        rpub = public_result(rcode, pj, nt_p) if rcode else None
        return (pid, r["idx"], arm, {"code_valid": bool(rcode), "repaired_hidden_pass": ok,
                "repaired_pub_cat": (rpub or {}).get("category"), "orig_pub_cat": r["pub_cat"],
                "ptok": res["ptok"], "ctok": res["ctok"], "finish": res["finish"]})
    recs = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        done = 0
        for pid, idx, arm, res in ex.map(do_repair, jobs):
            recs.append({"pid": pid, "cand_idx": idx, "arm": arm, **res}); done += 1
            if done % 100 == 0: print(f"  repair {done}/{len(jobs)}", flush=True)

    # ---- write + aggregate ----
    args.outdir.mkdir(parents=True, exist_ok=True)
    with (args.outdir / "feedback_records.jsonl").open("w") as f:
        for pid, r in flat:
            for arm in ARMS:
                if arm == "V4_llm_diagnosis_feedback":
                    verif, fb = "This solution is incorrect.", v4[(pid, r["idx"])]["text"]
                else:
                    verif, fb = build_static_feedback(arm, r["pub"])
                f.write(json.dumps({"pid": pid, "cand_idx": r["idx"], "arm": arm, "orig_pub_cat": r["pub_cat"],
                                    "verification": verif, "feedback": fb}, ensure_ascii=False) + "\n")
    with (args.outdir / "repair_records.jsonl").open("w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    by_arm = defaultdict(list)
    for r in recs: by_arm[r["arm"]].append(r)
    summary = {"n_problems": len(chosen), "n_incorrect_candidates": n_cand,
               "public_category_dist": dict(catdist), "excluded": dict(excluded),
               "selection_rule": ">=4 incorrect(hidden) loop-0 candidates/problem; per problem up to "
               f"{args.max_cands_per_problem} stratified across public-exec categories; no-code excluded",
               "decoding": {"repair_temp": args.repair_temp, "critic_temp": args.critic_temp,
                            "top_p": args.top_p, "top_k": args.top_k, "max_tokens_repair": args.max_tokens_repair},
               "arms": {}}
    for arm in ARMS:
        rs = by_arm[arm]; n = len(rs)
        succ = sum(r["repaired_hidden_pass"] for r in rs)
        solved = len({r["pid"] for r in rs if r["repaired_hidden_pass"]})
        per_cat = {}
        for cat in catdist:
            cr = [r for r in rs if r["orig_pub_cat"] == cat]
            per_cat[cat] = {"n": len(cr), "repaired": sum(x["repaired_hidden_pass"] for x in cr),
                            "rate": round(sum(x["repaired_hidden_pass"] for x in cr) / max(1, len(cr)), 4)}
        pt = sum(r["ptok"] for r in rs); ct = sum(r["ctok"] for r in rs)
        summary["arms"][arm] = {"attempts": n, "repair_success": succ,
                                "repair_success_rate": round(succ / max(1, n), 4),
                                "solved_problems": solved, "code_valid": sum(r["code_valid"] for r in rs),
                                "per_error_type": per_cat, "ptok": pt, "ctok": ct,
                                "tok_per_success": round((pt + ct) / max(1, succ), 1)}
    (args.outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({"arms": {a: {k: summary["arms"][a][k] for k in ("repair_success", "attempts", "repair_success_rate", "solved_problems")} for a in ARMS}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
