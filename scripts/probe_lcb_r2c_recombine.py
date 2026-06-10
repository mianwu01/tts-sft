#!/usr/bin/env python3
"""LCB loop0->loop1 feedback recombination probe (unit = group of k=4 loop0 parents).

Arms (same parent groups + same per-group seed; only the prompt differs):
  R0_original              : exact livecodebench-aggregate prompt, no feedback, no stay-close.
  R0_stayclose_no_feedback : stay-close prompt, no feedback.
  R2c_stayclose_v2_concise : stay-close + deterministic V2-concise visible-execution feedback/candidate.

Candidates inserted = FULL loop0 text (strip=false baseline, fair). Code extracted ONLY to build
V2-concise from PUBLIC tests. Hidden tests used ONLY for final grading. No V3/V4, no SFT.
Does not modify the baseline loop. Writes outputs/node1_lcb_r2c_recombine_probe/.
"""
from __future__ import annotations
import argparse, json, subprocess, sys, tempfile, threading, time
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))
sys.path.insert(0, str(_REPO / "external/squeeze-evolve/src"))
from eval_lcbv6_calibration import extract_code, HARNESS  # noqa: E402
PUB = _REPO / "scripts/lcb_public_probe_harness.py"
import importlib.util, glob, pathlib
for reg in sorted(glob.glob(str(_REPO / "external/squeeze-evolve/benchmarks/*/register.py"))):
    s = importlib.util.spec_from_file_location("r_" + pathlib.Path(reg).parent.name, reg)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
from squeeze_evolve import recombination  # noqa: E402
R0_ORIGINAL_FN = recombination.get("livecodebench-aggregate")

STAYCLOSE_NOFB = """You are given a competitive programming problem and several candidate solutions.

Some candidate solutions may be incorrect.

Your task is to synthesize one correct Python solution.

Correctness is the primary goal. However, to the extent possible, keep the final solution close to the candidate attempts. Prefer repairing, combining, and minimally modifying useful parts of the candidate solutions over writing a completely different solution from scratch. Only deviate substantially from the candidate attempts if their approaches are clearly flawed.

Do not blindly trust any single candidate. Reason about the full problem constraints.

Return only one complete Python code block enclosed with triple backticks. Do not include explanation outside the code block.

Problem:
{problem}

Candidate solutions:
{candidates}
Now write one improved solution. Return only a single Python code block enclosed with triple backticks."""

R2C = """You are given a competitive programming problem, several candidate solutions, and visible execution feedback for each candidate.

Some candidate solutions may be incorrect. The feedback is based only on public/sample execution and may be incomplete. It does not include hidden tests.

Your task is to synthesize one correct Python solution.

Correctness is the primary goal. However, to the extent possible, keep the final solution close to the candidate attempts. Prefer repairing, combining, and minimally modifying useful parts of the candidate solutions over writing a completely different solution from scratch. Only deviate substantially from the candidate attempts if their approaches are clearly flawed.

Use the visible execution feedback to avoid known bugs, but do not blindly trust any single candidate or any single feedback item. Do not overfit only to the shown public/sample tests. Reason about the full problem constraints.

Return only one complete Python code block enclosed with triple backticks. Do not include explanation outside the code block.

Problem:
{problem}

Candidate solutions and visible feedback:
{candidates}
Now write one improved solution. Return only a single Python code block enclosed with triple backticks."""


def trunc(s, n=400):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[:n] + " …[truncated]"


def v2_concise_block(pub):
    cat = pub["category"]; ff = pub.get("first_fail")
    if cat == "all_pass":
        return ("Visible execution feedback:\nSTATUS: visible_passed\n\nOBSERVED:\nVisible tests passed; "
                "no visible failure observed.\n\nDETAIL:\nNo visible failure is available.\n\nCHECK:\n"
                "Still verify edge cases, constraints, and algorithmic complexity.")
    head = "Visible execution feedback:\nSTATUS: {st}\n\nOBSERVED:\n{ob}\n\nDETAIL:\n{dt}\n\nCHECK:\n" \
           "Use this visible execution result to identify possible bugs, but do not overfit only to the " \
           "shown public/sample test. Hidden tests are not available."
    if cat == "wrong_answer" and ff:
        return head.format(st="visible_failed_wrong_answer", ob="Wrong answer on a shown public/sample test.",
                           dt=f"Input:\n{trunc(ff['input'])}\nExpected output:\n{trunc(ff['expected'])}\n"
                              f"Actual output:\n{trunc(ff['actual'])}")
    if cat in ("runtime_error", "no_callable") and ff:
        return head.format(st="runtime_error", ob="The program raised an error on a shown test.",
                           dt=f"Error:\n{trunc(ff.get('error'),300)}")
    if cat == "compile_error" and ff:
        return head.format(st="compile_error", ob="The program failed to compile/parse.",
                           dt=f"Error:\n{trunc(ff.get('error'),300)}")
    if cat == "timeout":
        return head.format(st="timeout", ob=f"Time limit exceeded on shown test {(ff['idx']+1) if ff else '?'}.",
                           dt="The program did not finish within the time limit on a shown test.")
    return ("Visible execution feedback:\nSTATUS: no_visible_tests\n\nOBSERVED:\nNo public/sample execution "
            "signal available.\n\nDETAIL:\nNone.\n\nCHECK:\nReason about the problem constraints directly.")


def run_harness(harness, code, tests_json, n, tl=6.0):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as cf: cf.write(code); cp = cf.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf: tf.write(tests_json); tp = tf.name
    try:
        p = subprocess.run([sys.executable, str(harness), cp, tp], capture_output=True, text=True,
                           timeout=min(n * tl + 20, 240))
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return None
    finally:
        Path(cp).unlink(missing_ok=True); Path(tp).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-problems", type=int, default=30)
    ap.add_argument("--groups-per-problem", type=int, default=4)
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Thinking-2507")
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--max-tokens", type=int, default=32768)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--concurrency", type=int, default=24)
    ap.add_argument("--outdir", type=Path, default=Path("outputs/node1_lcb_r2c_recombine_probe"))
    ap.add_argument("--arms", default="R0_original,R0_stayclose_no_feedback,R2c_stayclose_v2_concise",
                    help="comma-separated subset of the 3 arms to run.")
    args = ap.parse_args()

    hidden = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_non_saturated.jsonl").open()}
    public = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_public_tests.jsonl").open()}
    lc = _REPO / "outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/se.jsonl.loop_candidates.jsonl"
    loop0 = defaultdict(dict); groups = defaultdict(list)
    for line in lc.open():
        r = json.loads(line)
        if r["loop_index"] == 0:
            loop0[r["id"]][int(r["candidate_id"].rsplit("cand", 1)[-1])] = r["full_response"] or ""
        elif r["loop_index"] == 1 and r.get("parent_ids") is not None:
            groups[r["id"]].append(list(r["parent_ids"]))

    sem = threading.Semaphore(args.concurrency)
    def hidden_pass(code, pid):
        h = hidden[pid]["tests"]; n = len(json.loads(h)["inputs"])
        v = run_harness(HARNESS, code, h, n); return bool(v and v.get("passed"))
    def pub_exec(code, pid):
        pj = public[pid]["public_tests"]; n = len(json.loads(pj)["inputs"])
        return run_harness(PUB, code, pj, n)

    # ---- select problems with MIXED loop-0 correctness (informative for recombination) ----
    print("grading loop-0 (hidden) for selection ...", flush=True)
    def loop0_correct(pid):
        c = sum(hidden_pass(extract_code(t) or "x", pid) for t in loop0[pid].values()); return pid, c
    mixed = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for pid, c in ex.map(loop0_correct, sorted(loop0)):
            if 1 <= c <= len(loop0[pid]) - 1:
                mixed.append((pid, c))
    mixed.sort(key=lambda x: abs(x[1] - len(loop0[x[0]]) / 2))  # most-mixed first
    chosen = [pid for pid, _ in mixed[: args.n_problems]]
    sel_groups = [(pid, gi, groups[pid][gi]) for pid in chosen for gi in range(min(args.groups_per_problem, len(groups[pid])))]
    print(f"selected {len(chosen)} mixed problems, {len(sel_groups)} groups", flush=True)

    # ---- V2-concise per candidate (public exec on extracted code) ----
    needed = {(pid, idx) for pid, gi, grp in sel_groups for idx in grp}
    print(f"public-exec on {len(needed)} candidates for V2-concise ...", flush=True)
    v2 = {}; codes = {}
    def build_v2(k):
        pid, idx = k; code = extract_code(loop0[pid][idx])
        codes[k] = code
        if not code:
            return k, ("Visible execution feedback:\nSTATUS: no_visible_tests\n\nOBSERVED:\nCandidate has no "
                       "extractable code.\n\nDETAIL:\nNone.\n\nCHECK:\nReason about the problem directly."), "no_code"
        pub = pub_exec(code, pid) or {"category": "unknown", "first_fail": None}
        return k, v2_concise_block(pub), pub["category"]
    cat_of = {}
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for k, block, cat in ex.map(build_v2, needed):
            v2[k] = block; cat_of[k] = cat

    # ---- model client ----
    from openai import OpenAI
    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=7200)
    def call(prompt, seed):
        for attempt in range(4):
            try:
                with sem:
                    r = client.chat.completions.create(model=args.model,
                        messages=[{"role": "user", "content": prompt}], temperature=args.temperature,
                        top_p=args.top_p, max_tokens=args.max_tokens, seed=seed, extra_body={"top_k": args.top_k})
                ch = r.choices[0]; u = r.usage
                return {"text": ch.message.content or "", "ptok": getattr(u, "prompt_tokens", 0),
                        "ctok": getattr(u, "completion_tokens", 0), "finish": ch.finish_reason}
            except Exception as e:  # noqa: BLE001
                time.sleep(min(20, 2 ** attempt)); last = e
        return {"text": "", "ptok": 0, "ctok": 0, "finish": "error", "err": str(last)}

    def build_prompt(arm, pid, grp):
        problem = hidden[pid]["problem"]
        cand_texts = [(loop0[pid][idx] or "").strip() for idx in grp]
        if arm == "R0_original":
            return R0_ORIGINAL_FN(problem, cand_texts, task="code", temperature=1.0)
        if arm == "R0_stayclose_no_feedback":
            blocks = "".join(f"\n---- Solution {j} ----\n{c}\n" for j, c in enumerate(cand_texts, 1))
            return STAYCLOSE_NOFB.format(problem=problem, candidates=blocks)
        # R2c
        parts = []
        for j, idx in enumerate(grp, 1):
            parts.append(f"\n---- Solution {j} ----\n{(loop0[pid][idx] or '').strip()}\n")
            parts.append(f"---- Visible feedback on Solution {j} ----\n{v2[(pid, idx)]}\n")
        return R2C.format(problem=problem, candidates="".join(parts))

    ARMS = [a for a in args.arms.split(",") if a.strip()]
    jobs = [(pid, gi, grp, arm) for (pid, gi, grp) in sel_groups for arm in ARMS]
    print(f"recombination calls: {len(jobs)} ({len(sel_groups)} groups x 3 arms)", flush=True)

    # group-level "has visible failure" = any parent candidate not all_pass/no_code-passing
    def group_visible_failed(grp, pid):
        return any(cat_of.get((pid, idx)) not in ("all_pass",) for idx in grp)

    def do(job):
        pid, gi, grp, arm = job
        res = call(build_prompt(arm, pid, grp), args.seed + gi)
        rc = extract_code(res["text"])
        ok = bool(rc) and hidden_pass(rc, pid)
        rpub = pub_exec(rc, pid) if rc else None
        return {"pid": pid, "group": gi, "arm": arm, "code_valid": bool(rc), "correct": ok,
                "repaired_pub_cat": (rpub or {}).get("category"),
                "visible_failed_group": group_visible_failed(grp, pid),
                "ptok": res["ptok"], "ctok": res["ctok"], "finish": res["finish"]}
    recs = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        done = 0
        for r in ex.map(do, jobs):
            recs.append(r); done += 1
            if done % 60 == 0: print(f"  {done}/{len(jobs)}", flush=True)

    args.outdir.mkdir(parents=True, exist_ok=True)
    with (args.outdir / "recomb_records.jsonl").open("w") as f:
        for r in recs: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # also save the V2-concise feedback used (audit)
    with (args.outdir / "feedback_records.jsonl").open("w") as f:
        for (pid, idx), block in v2.items():
            f.write(json.dumps({"pid": pid, "cand_idx": idx, "pub_cat": cat_of[(pid, idx)], "v2_concise": block}, ensure_ascii=False) + "\n")

    by = defaultdict(list)
    for r in recs: by[r["arm"]].append(r)
    summ = {"n_problems": len(chosen), "n_groups": len(sel_groups),
            "feedback_candidate_cat_dist": dict(Counter(cat_of.values())),
            "decoding": {"temperature": args.temperature, "top_p": args.top_p, "top_k": args.top_k, "max_tokens": args.max_tokens},
            "arms": {}}
    for arm in ARMS:
        rs = by[arm]; n = len(rs)
        vf = [r for r in rs if r["visible_failed_group"]]; vp = [r for r in rs if not r["visible_failed_group"]]
        summ["arms"][arm] = {
            "groups": n, "correct": sum(r["correct"] for r in rs), "density": round(sum(r["correct"] for r in rs) / max(1, n), 4),
            "solved_problems": len({r["pid"] for r in rs if r["correct"]}),
            "code_valid": sum(r["code_valid"] for r in rs), "code_valid_rate": round(sum(r["code_valid"] for r in rs) / max(1, n), 4),
            "visible_failed_groups": {"n": len(vf), "correct": sum(r["correct"] for r in vf)},
            "visible_passed_groups": {"n": len(vp), "correct": sum(r["correct"] for r in vp)},
            "ptok": sum(r["ptok"] for r in rs), "ctok": sum(r["ctok"] for r in rs)}
    (args.outdir / "summary.json").write_text(json.dumps(summ, indent=2))
    print(json.dumps(summ["arms"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
