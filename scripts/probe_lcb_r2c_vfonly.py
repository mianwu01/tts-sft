#!/usr/bin/env python3
"""R2c_old_visible_failed_only: old (CHECK-bearing) V2-concise on visible-failed candidates; NO
feedback block at all on all_pass candidates; top-level note that feedback is shown only for failed
candidates. Same 560 confirmation groups + seeds; reuse R0_stayclose / old-R2c / refined-R2c for flips.
Stay-close kept. No V3/V4, no SFT. Hidden tests only for grading. Baseline/orchestrator untouched.
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
import probe_lcb_r2c_recombine as POLD  # provides the OLD v2_concise_block (STATUS/OBSERVED/DETAIL/CHECK)
PUB = _REPO / "scripts/lcb_public_probe_harness.py"

PROMPT = """You are given a competitive programming problem, several candidate solutions, and visible execution feedback for the candidates that failed public/sample execution.

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


def run_harness(harness, code, tj, n, tl=6.0):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as cf: cf.write(code); cp = cf.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf: tf.write(tj); tp = tf.name
    try:
        p = subprocess.run([sys.executable, str(harness), cp, tp], capture_output=True, text=True, timeout=min(n*tl+20, 240))
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return None
    finally:
        Path(cp).unlink(missing_ok=True); Path(tp).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm-dir", type=Path, default=Path("outputs/node1_lcb_r2c_confirm"))
    ap.add_argument("--refined-dir", type=Path, default=Path("outputs/node1_lcb_r2c_refined_confirm"))
    ap.add_argument("--outdir", type=Path, default=Path("outputs/node1_lcb_r2c_old_visible_failed_only_confirm"))
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Thinking-2507")
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--temperature", type=float, default=1.0); ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=20); ap.add_argument("--max-tokens", type=int, default=32768)
    ap.add_argument("--seed", type=int, default=1234); ap.add_argument("--concurrency", type=int, default=24)
    args = ap.parse_args()

    hidden = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_non_saturated.jsonl").open()}
    public = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_public_tests.jsonl").open()}
    loop0 = defaultdict(dict); groups = defaultdict(list)
    for line in (_REPO / "outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/se.jsonl.loop_candidates.jsonl").open():
        r = json.loads(line)
        if r["loop_index"] == 0: loop0[r["id"]][int(r["candidate_id"].rsplit("cand", 1)[-1])] = r["full_response"] or ""
        elif r["loop_index"] == 1 and r.get("parent_ids") is not None: groups[r["id"]].append(list(r["parent_ids"]))

    base = defaultdict(dict)
    for l in (args.confirm_dir / "recomb_records.jsonl").open():
        r = json.loads(l); base[(r["pid"], r["group"])][r["arm"]] = r["correct"]
    for l in (args.refined_dir / "recomb_records.jsonl").open():
        r = json.loads(l); base[(r["pid"], r["group"])]["R2c_refined"] = r["correct"]
    sel = sorted(base.keys())
    print(f"reusing {len(sel)} groups; paired arms: {sorted({a for k in base for a in base[k]})}", flush=True)

    needed = {(pid, idx) for (pid, gi) in sel for idx in groups[pid][gi]}
    print(f"public-exec on {len(needed)} parents ...", flush=True)
    block = {}; cat_of = {}
    def build(k):
        pid, idx = k; code = extract_code(loop0[pid][idx])
        if not code:
            return k, "compile_error", POLD.v2_concise_block({"category": "compile_error", "first_fail": {"error": "No extractable Python code block."}})
        pj = public[pid]["public_tests"]; n = len(json.loads(pj)["inputs"])
        pub = run_harness(PUB, code, pj, n) or {"category": "unknown", "first_fail": None}
        cat = pub["category"]
        b = None if cat == "all_pass" else POLD.v2_concise_block(pub)  # OMIT feedback for all_pass
        return k, cat, b
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for k, cat, b in ex.map(build, needed):
            cat_of[k] = cat; block[k] = b

    from openai import OpenAI
    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=7200)
    sem = threading.Semaphore(args.concurrency)
    def call(prompt, seed):
        for attempt in range(4):
            try:
                with sem:
                    r = client.chat.completions.create(model=args.model, messages=[{"role": "user", "content": prompt}],
                        temperature=args.temperature, top_p=args.top_p, max_tokens=args.max_tokens, seed=seed, extra_body={"top_k": args.top_k})
                ch = r.choices[0]; u = r.usage
                return {"text": ch.message.content or "", "ptok": getattr(u, "prompt_tokens", 0), "ctok": getattr(u, "completion_tokens", 0)}
            except Exception as e:  # noqa: BLE001
                time.sleep(min(20, 2 ** attempt)); last = e
        return {"text": "", "ptok": 0, "ctok": 0, "err": str(last)}

    def vis_failed(pid, grp): return any(cat_of.get((pid, i)) not in ("all_pass",) for i in grp)
    def do(item):
        pid, gi = item; grp = groups[pid][gi]; parts = []
        for j, idx in enumerate(grp, 1):
            parts.append(f"\n---- Solution {j} ----\n{(loop0[pid][idx] or '').strip()}\n")
            if block[(pid, idx)] is not None:  # only visible-failed candidates get a block
                parts.append(f"---- Visible feedback on Solution {j} ----\n{block[(pid, idx)]}\n")
        res = call(PROMPT.format(problem=hidden[pid]["problem"], blocks="".join(parts)), args.seed + gi)
        rc = extract_code(res["text"]); h = hidden[pid]["tests"]; nt = len(json.loads(h)["inputs"])
        ok = bool(rc) and bool((run_harness(HARNESS, rc, h, nt) or {}).get("passed"))
        return {"pid": pid, "group": gi, "arm": "R2c_old_visible_failed_only", "code_valid": bool(rc),
                "correct": ok, "visible_failed_group": vis_failed(pid, grp), "ptok": res["ptok"], "ctok": res["ctok"]}
    print(f"recombination calls: {len(sel)}", flush=True)
    recs = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        done = 0
        for r in ex.map(do, sel):
            recs.append(r); done += 1
            if done % 60 == 0: print(f"  {done}/{len(sel)}", flush=True)

    args.outdir.mkdir(parents=True, exist_ok=True)
    with (args.outdir / "recomb_records.jsonl").open("w") as f:
        for r in recs: f.write(json.dumps(r, ensure_ascii=False) + "\n")

    ref = {(r["pid"], r["group"]): r for r in recs}
    vf = [k for k in sel if ref[k]["visible_failed_group"]]; vp = [k for k in sel if not ref[k]["visible_failed_group"]]
    g = lambda k: ref[k]["correct"]
    def arm(a): return lambda k: base[k].get(a, False)
    def sub(keys, gg): return f"{sum(gg(k) for k in keys)}/{len(keys)}"
    def flips(keys, agg, bgg): return {"wins": sum(1 for k in keys if not agg(k) and bgg(k)), "losses": sum(1 for k in keys if agg(k) and not bgg(k))}
    S = arm("R0_stayclose_no_feedback"); O = arm("R2c_stayclose_v2_concise"); RF = arm("R2c_refined")
    summ = {"n_groups": len(sel), "parent_cat_dist": dict(Counter(cat_of.values())),
            "this_arm": {"correct": sum(g(k) for k in sel), "density": round(sum(g(k) for k in sel)/len(sel), 4),
                         "code_valid": sum(ref[k]["code_valid"] for k in sel), "visible_failed": sub(vf, g), "visible_passed": sub(vp, g),
                         "ptok": sum(ref[k]["ptok"] for k in sel), "ctok": sum(ref[k]["ctok"] for k in sel)},
            "baselines": {a: {"correct": sum(arm(a)(k) for k in sel), "visible_failed": sub(vf, arm(a)), "visible_passed": sub(vp, arm(a))}
                          for a in ("R0_stayclose_no_feedback", "R2c_stayclose_v2_concise", "R2c_refined")},
            "flips_vs_R0_stayclose": flips(sel, S, g), "flips_vs_R0_stayclose_visible_failed": flips(vf, S, g),
            "flips_vs_R0_stayclose_visible_passed": flips(vp, S, g),
            "flips_vs_old_R2c": flips(sel, O, g), "flips_vs_refined_R2c": flips(sel, RF, g)}
    (args.outdir / "summary.json").write_text(json.dumps(summ, indent=2))
    print(json.dumps(summ, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
