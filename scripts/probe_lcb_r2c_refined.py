#!/usr/bin/env python3
"""Refined R2c confirmation: cleaner V2-concise (no per-candidate CHECK; one-line all_pass note;
safety instruction moved to the top of the prompt once). Reuses the EXACT 560 confirmation groups +
per-group seeds from outputs/node1_lcb_r2c_confirm/, so R0_stayclose and old-R2c results are reused
for pairing (only the refined arm is generated). Baseline/orchestrator untouched. No V3/V4, no SFT.
"""
from __future__ import annotations
import argparse, json, subprocess, sys, tempfile, threading, time
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))
from eval_lcbv6_calibration import extract_code, HARNESS  # noqa: E402
PUB = _REPO / "scripts/lcb_public_probe_harness.py"

REFINED_PROMPT = """You are given a competitive programming problem, several candidate solutions, and visible execution feedback for the candidates.

Some candidate solutions may be incorrect. Visible execution feedback is based only on public/sample execution and may be incomplete. It does not include hidden tests. Use visible failures as evidence of bugs, but do not overfit only to the shown tests. A candidate with no visible failure is not guaranteed to be correct; it only means no public/sample failure was observed.

Your task is to synthesize one correct Python solution.

Correctness is the primary goal. However, to the extent possible, keep the final solution close to the candidate attempts. Prefer repairing, combining, and minimally modifying useful parts of the candidate solutions over writing a completely different solution from scratch. Only deviate substantially from the candidate attempts if their approaches are clearly flawed.

Do not blindly trust any single candidate or any single feedback item. Reason about the full problem constraints.

Return only one complete Python code block enclosed with triple backticks. Do not include explanation outside the code block.

Problem:
{problem}

Candidate solutions and visible feedback:
{blocks}
Now write one improved solution. Return only a single Python code block enclosed with triple backticks."""


def trunc(s, n=400):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[:n] + " …[truncated]"


def refined_v2(pub):
    """Refined V2-concise: concrete facts only for visible failures; one-line note for all_pass. No CHECK."""
    cat = pub.get("category"); ff = pub.get("first_fail")
    if cat == "all_pass":
        return "Visible execution feedback:\nSTATUS: visible_passed — public/sample tests passed; no visible failure observed."
    if cat == "wrong_answer" and ff:
        return ("Visible execution feedback:\nSTATUS: wrong_answer\nA shown public/sample test failed.\n\n"
                f"Input:\n{trunc(ff['input'])}\n\nExpected output:\n{trunc(ff['expected'])}\n\n"
                f"Actual output:\n{trunc(ff['actual'])}")
    if cat == "runtime_error" and ff:
        return ("Visible execution feedback:\nSTATUS: runtime_error\nThe program raised an error on a shown "
                f"public/sample test.\n\nError:\n{trunc(ff.get('error'),300)}")
    if cat in ("compile_error", "no_callable") and ff:
        return ("Visible execution feedback:\nSTATUS: compile_error\nThe program failed to compile/parse.\n\n"
                f"Error:\n{trunc(ff.get('error'),300)}")
    if cat == "timeout":
        return "Visible execution feedback:\nSTATUS: timeout\nThe program timed out on a shown public/sample test."
    # no extractable code / unknown
    return ("Visible execution feedback:\nSTATUS: compile_error\nThe program failed to compile/parse.\n\n"
            "Error:\nNo extractable Python code block.")


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
    ap.add_argument("--confirm-dir", type=Path, default=Path("outputs/node1_lcb_r2c_confirm"))
    ap.add_argument("--outdir", type=Path, default=Path("outputs/node1_lcb_r2c_refined_confirm"))
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Thinking-2507")
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--max-tokens", type=int, default=32768)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--concurrency", type=int, default=24)
    args = ap.parse_args()

    hidden = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_non_saturated.jsonl").open()}
    public = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_public_tests.jsonl").open()}
    loop0 = defaultdict(dict); groups = defaultdict(list)
    for line in (_REPO / "outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/se.jsonl.loop_candidates.jsonl").open():
        r = json.loads(line)
        if r["loop_index"] == 0:
            loop0[r["id"]][int(r["candidate_id"].rsplit("cand", 1)[-1])] = r["full_response"] or ""
        elif r["loop_index"] == 1 and r.get("parent_ids") is not None:
            groups[r["id"]].append(list(r["parent_ids"]))

    # exact groups + paired baseline results from the confirmation run
    confirm = [json.loads(l) for l in (args.confirm_dir / "recomb_records.jsonl").open()]
    base = defaultdict(dict)  # (pid,gi)->arm->correct
    for r in confirm: base[(r["pid"], r["group"])][r["arm"]] = r["correct"]
    sel = sorted(base.keys())
    print(f"reusing {len(sel)} confirmation groups (paired baselines: {sorted({a for k in base for a in base[k]})})", flush=True)

    # public exec -> refined V2 + category per parent candidate
    needed = {(pid, idx) for (pid, gi) in sel for idx in groups[pid][gi]}
    print(f"public-exec on {len(needed)} parent candidates ...", flush=True)
    v2 = {}; cat_of = {}
    def build(k):
        pid, idx = k; code = extract_code(loop0[pid][idx])
        if not code:
            return k, refined_v2({"category": "no_code"}), "no_code"
        pj = public[pid]["public_tests"]; n = len(json.loads(pj)["inputs"])
        pub = run_harness(PUB, code, pj, n) or {"category": "unknown", "first_fail": None}
        return k, refined_v2(pub), pub["category"]
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for k, block, cat in ex.map(build, needed):
            v2[k] = block; cat_of[k] = cat

    from openai import OpenAI
    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=7200)
    sem = threading.Semaphore(args.concurrency)
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

    def vis_failed(pid, grp): return any(cat_of.get((pid, i)) not in ("all_pass",) for i in grp)
    def do(item):
        pid, gi = item; grp = groups[pid][gi]
        blocks = []
        for j, idx in enumerate(grp, 1):
            blocks.append(f"\n---- Solution {j} ----\n{(loop0[pid][idx] or '').strip()}\n")
            blocks.append(f"---- Visible feedback on Solution {j} ----\n{v2[(pid, idx)]}\n")
        prompt = REFINED_PROMPT.format(problem=hidden[pid]["problem"], blocks="".join(blocks))
        res = call(prompt, args.seed + gi)
        rc = extract_code(res["text"])
        h = hidden[pid]["tests"]; nt = len(json.loads(h)["inputs"])
        ok = bool(rc) and bool((run_harness(HARNESS, rc, h, nt) or {}).get("passed"))
        return {"pid": pid, "group": gi, "arm": "R2c_refined_stayclose_v2_concise", "code_valid": bool(rc),
                "correct": ok, "visible_failed_group": vis_failed(pid, grp),
                "ptok": res["ptok"], "ctok": res["ctok"], "finish": res["finish"]}
    print(f"refined recombination calls: {len(sel)}", flush=True)
    recs = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        done = 0
        for r in ex.map(do, sel):
            recs.append(r); done += 1
            if done % 60 == 0: print(f"  {done}/{len(sel)}", flush=True)

    args.outdir.mkdir(parents=True, exist_ok=True)
    with (args.outdir / "recomb_records.jsonl").open("w") as f:
        for r in recs: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (args.outdir / "feedback_records.jsonl").open("w") as f:
        for (pid, idx), block in v2.items():
            f.write(json.dumps({"pid": pid, "cand_idx": idx, "pub_cat": cat_of[(pid, idx)], "v2_refined": block}, ensure_ascii=False) + "\n")

    ref = {(r["pid"], r["group"]): r for r in recs}
    def density(pred):
        c = sum(pred(k) for k in sel); return c, round(c / len(sel), 4)
    S = "R0_stayclose_no_feedback"; OLD = "R2c_stayclose_v2_concise"
    vf = [k for k in sel if ref[k]["visible_failed_group"]]; vp = [k for k in sel if not ref[k]["visible_failed_group"]]
    def subset(keys, get): return f"{sum(get(k) for k in keys)}/{len(keys)}"
    def flips(akeys, aget, bget):
        up = sum(1 for k in akeys if not aget(k) and bget(k)); dn = sum(1 for k in akeys if aget(k) and not bget(k))
        return up, dn
    refget = lambda k: ref[k]["correct"]; sget = lambda k: base[k].get(S, False); oget = lambda k: base[k].get(OLD, False)
    cR, dR = density(refget)
    summ = {"n_groups": len(sel), "parent_cat_dist": dict(Counter(cat_of.values())),
            "decoding": {"temperature": args.temperature, "max_tokens": args.max_tokens},
            "R2c_refined": {"correct": cR, "density": dR, "code_valid": sum(ref[k]["code_valid"] for k in sel),
                            "visible_failed": subset(vf, refget), "visible_passed": subset(vp, refget),
                            "ptok": sum(ref[k]["ptok"] for k in sel), "ctok": sum(ref[k]["ctok"] for k in sel)},
            "paired_baselines": {
                "R0_stayclose": {"correct": sum(sget(k) for k in sel), "visible_failed": subset(vf, sget), "visible_passed": subset(vp, sget)},
                "old_R2c": {"correct": sum(oget(k) for k in sel), "visible_failed": subset(vf, oget), "visible_passed": subset(vp, oget)}},
            "flips_refined_vs_R0_stayclose": dict(zip(("wins", "losses"), flips(sel, sget, refget))),
            "flips_refined_vs_R0_stayclose_visible_failed": dict(zip(("wins", "losses"), flips(vf, sget, refget))),
            "flips_refined_vs_R0_stayclose_visible_passed": dict(zip(("wins", "losses"), flips(vp, sget, refget))),
            "flips_refined_vs_old_R2c": dict(zip(("wins", "losses"), flips(sel, oget, refget)))}
    (args.outdir / "summary.json").write_text(json.dumps(summ, indent=2))
    print(json.dumps(summ, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
