#!/usr/bin/env python3
"""P1 step 3: offline DISAGREEMENT-feedback probe (the M4-analog for code) on the vfonly blind spot.

Target: loop-1 parent groups whose 4 parents ALL pass the public tests (all_pass) — under the frozen
vfonly config these groups receive ZERO feedback. We manufacture label-free signal via differential
testing: run the 4 parents on model-proposed probe inputs (NO expected outputs) and report only facts
("Solutions 1 and 3 produce different outputs on input X; at most one can be correct").

Arms (paired: same groups, same per-group seed, temp 1.0 SE-matched):
  D0_no_feedback     — the vfonly operator's exact behavior on these groups (stay-close top, no blocks).
  D1_disagreement    — same + one group-level 'Cross-candidate execution comparison' section.
Only groups WITH detected disagreement get both arms (others contribute to the incidence stat).
Hidden tests: post-hoc grading + analysis-only stratification (all-parents-hidden-wrong = true blind spot).

Writes outputs/node1_lcb_disagreement_probe/{group_records.jsonl, summary.json}.
"""
from __future__ import annotations
import argparse, json, sys, threading, time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))
from eval_lcbv6_calibration import extract_code, HARNESS  # noqa: E402
from lcb_grading import GradingCache, run_harness_cached  # noqa: E402
PUB = _REPO / "scripts/lcb_public_probe_harness.py"
PROBE = _REPO / "scripts/lcb_probe_exec.py"

# D0 = the vfonly operator's _STAYCLOSE_TOP verbatim (what arm C emits when no parent has a visible failure)
D0_TOP = """You are given a competitive programming problem, several candidate solutions, and visible execution feedback for the candidates that failed public/sample execution.

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

D1_TOP = """You are given a competitive programming problem, several candidate solutions, and a cross-candidate execution comparison.

Some candidate solutions may be incorrect. All candidates pass the shown public/sample tests, but they DISAGREE with each other on additional probe inputs. The correct outputs for these probe inputs are unknown — where candidates disagree, at most one behavior can be correct. Use the disagreements as evidence of latent bugs, but determine which logic is correct by reasoning about the problem statement; do not assume the majority behavior is correct. Hidden tests are not available.

Your task is to synthesize one correct Python solution.

Correctness is the primary goal. However, to the extent possible, keep the final solution close to the candidate attempts. Prefer repairing, combining, and minimally modifying useful parts of the candidate solutions over writing a completely different solution from scratch. Only deviate substantially from the candidate attempts if their approaches are clearly flawed.

Do not blindly trust any single candidate or any single feedback item. Reason about the full problem constraints.

Return only one complete Python code block enclosed with triple backticks. Do not include explanation outside the code block.

Problem:
{problem}

Candidate solutions:
{blocks}
---- Cross-candidate execution comparison ----
{comparison}

Now write one improved solution. Return only a single Python code block enclosed with triple backticks."""


def kindval(r):
    return (r["kind"], r["value"] if r["kind"] == "output" else r["kind"])


def build_comparison(probe_inputs, per_parent_results, max_shown=2):
    """Pick the most informative disagreeing inputs and render a factual comparison. Returns (text, n_disagreeing)."""
    rows = []
    for ii, inp in enumerate(probe_inputs):
        beh = [kindval(per_parent_results[p][ii]) for p in range(len(per_parent_results))]
        clusters = defaultdict(list)
        for p, b in enumerate(beh):
            clusters[b].append(p + 1)
        if len(clusters) < 2:
            continue
        n_err = sum(1 for b in clusters if b[0] != "output")
        rows.append((len(clusters), -n_err, ii, inp, clusters))
    if not rows:
        return None, 0
    rows.sort(key=lambda r: (-r[0], r[1]))
    parts = []
    for _, _, ii, inp, clusters in rows[:max_shown]:
        seg = [f"Probe input:\n{inp[:400]}"]
        for beh, members in sorted(clusters.items(), key=lambda kv: kv[1][0]):
            who = ", ".join(f"Solution {m}" for m in members)
            if beh[0] == "output":
                seg.append(f"{who} output:\n{beh[1][:300]}")
            elif beh[0] == "timeout":
                seg.append(f"{who}: exceeded the time limit on this input")
            else:
                seg.append(f"{who}: raised an error on this input")
        parts.append("\n".join(seg))
    return "\n\n".join(parts), len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", type=Path, default=Path("outputs/node1_lcb_disagreement_probe"))
    ap.add_argument("--probe-inputs", type=Path, default=_REPO / "data/filtered/lcbv6_probe_inputs.jsonl")
    ap.add_argument("--max-groups", type=int, default=None, help="cap disagreement groups (smoke)")
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Thinking-2507")
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--max-tokens", type=int, default=32768)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--concurrency", type=int, default=24)
    args = ap.parse_args()

    hidden = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_non_saturated.jsonl").open()}
    public = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_public_tests.jsonl").open()}
    probes = {json.loads(l)["id"]: json.loads(l)["probe_inputs"] for l in args.probe_inputs.open()}
    cache = GradingCache(_REPO / "outputs/grading_cache/lcb_verdicts.jsonl")

    # loop-0 candidates + loop-1 parent groups from the formal strip=false run (the pinned anchor)
    loop0 = defaultdict(dict); groups = defaultdict(list)
    for line in (_REPO / "outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/se.jsonl.loop_candidates.jsonl").open():
        r = json.loads(line)
        if r["loop_index"] == 0:
            loop0[r["id"]][int(r["candidate_id"].rsplit("cand", 1)[-1])] = r["full_response"] or ""
        elif r["loop_index"] == 1 and r.get("parent_ids") is not None:
            groups[r["id"]].append(list(r["parent_ids"]))

    # public category + hidden verdict per unique parent (cached)
    def pub_cat(pid, idx):
        code = extract_code(loop0[pid][idx]) or ""
        if not code:
            return "no_code"
        pj = public[pid]["public_tests"]; n = len(json.loads(pj)["inputs"])
        v = run_harness_cached(PUB, code, pj, n, cache=cache) or {}
        return v.get("category", "unknown")
    def hid_ok(pid, idx):
        code = extract_code(loop0[pid][idx]) or ""
        h = hidden[pid]["tests"]; n = len(json.loads(h)["inputs"])
        v = run_harness_cached(HARNESS, code, h, n, cache=cache) or {}
        return bool(v.get("passed"))

    parents = sorted({(pid, idx) for pid in groups for grp in groups[pid] for idx in grp})
    print(f"classifying {len(parents)} unique parents (public, cached) ...", flush=True)
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        cats = dict(zip(parents, ex.map(lambda k: pub_cat(*k), parents)))

    allpass_groups = [(pid, gi, grp) for pid in sorted(groups) for gi, grp in enumerate(groups[pid])
                      if all(cats[(pid, idx)] == "all_pass" for idx in grp)]
    print(f"all-all_pass loop-1 groups: {len(allpass_groups)} / {sum(len(v) for v in groups.values())}", flush=True)

    # differential exec: unique parent x probe inputs
    import hashlib, subprocess, tempfile
    exec_cache = {}
    def probe_run(pid, idx):
        key = (pid, idx)
        if key in exec_cache:
            return exec_cache[key]
        code = extract_code(loop0[pid][idx]) or ""
        seed_rec = hidden[pid]
        spec = json.dumps({"inputs": probes.get(pid, []), "testtype": seed_rec.get("testtype") or "stdin",
                           "fn_name": seed_rec.get("fn_name") or "", "time_limit": 6})
        if not probes.get(pid) or not code:
            exec_cache[key] = None; return None
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as cf:
            cf.write(code); cp = cf.name
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write(spec); tp = tf.name
        try:
            p = subprocess.run([sys.executable, str(PROBE), cp, tp], capture_output=True, text=True,
                               timeout=len(probes[pid]) * 6 + 20)
            out = p.stdout.strip().splitlines()
            res = json.loads(out[-1])["results"] if out else None
        except Exception:  # noqa: BLE001
            res = None
        finally:
            Path(cp).unlink(missing_ok=True); Path(tp).unlink(missing_ok=True)
        exec_cache[key] = res
        return res

    ap_parents = sorted({(pid, idx) for pid, gi, grp in allpass_groups for idx in grp})
    print(f"differential exec on {len(ap_parents)} unique all_pass parents ...", flush=True)
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        list(ex.map(lambda k: probe_run(*k), ap_parents))

    # build comparison per group; keep groups with detected disagreement
    sel = []
    for pid, gi, grp in allpass_groups:
        res = [probe_run(pid, idx) for idx in grp]
        if any(r is None for r in res):
            continue
        comparison, n_dis = build_comparison(probes[pid], res)
        if comparison:
            sel.append({"pid": pid, "gi": gi, "grp": grp, "comparison": comparison, "n_disagreeing_inputs": n_dis})
    incidence = len(sel) / max(1, len(allpass_groups))
    print(f"groups WITH disagreement: {len(sel)} / {len(allpass_groups)} (incidence {incidence:.1%})", flush=True)
    if args.max_groups:
        sel = sel[: args.max_groups]

    from openai import OpenAI
    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=7200)
    sem = threading.Semaphore(args.concurrency)
    def call(prompt, seed):
        for attempt in range(4):
            try:
                with sem:
                    r = client.chat.completions.create(model=args.model,
                        messages=[{"role": "user", "content": prompt}], temperature=args.temperature,
                        top_p=0.95, max_tokens=args.max_tokens, seed=seed, extra_body={"top_k": 20})
                u = r.usage
                return {"text": r.choices[0].message.content or "",
                        "ptok": getattr(u, "prompt_tokens", 0), "ctok": getattr(u, "completion_tokens", 0)}
            except Exception:  # noqa: BLE001
                time.sleep(min(20, 2 ** attempt))
        return {"text": "", "ptok": 0, "ctok": 0}

    jobs = [(g, arm) for g in sel for arm in ("D0_no_feedback", "D1_disagreement")]
    print(f"recombination calls: {len(jobs)} ({len(sel)} groups x 2 arms)", flush=True)
    def do(job):
        g, arm = job; pid = g["pid"]
        cand_blocks = "".join(f"\n---- Solution {j} ----\n{(loop0[pid][idx] or '').strip()}\n"
                              for j, idx in enumerate(g["grp"], 1))
        if arm == "D0_no_feedback":
            prompt = D0_TOP.format(problem=hidden[pid]["problem"], blocks=cand_blocks)
        else:
            prompt = D1_TOP.format(problem=hidden[pid]["problem"], blocks=cand_blocks, comparison=g["comparison"])
        res = call(prompt, args.seed + g["gi"])
        code = extract_code(res["text"]) or ""
        h = hidden[pid]["tests"]; n = len(json.loads(h)["inputs"])
        v = run_harness_cached(HARNESS, code, h, n, cache=cache) if code else None
        return {"pid": pid, "gi": g["gi"], "arm": arm, "code_valid": bool(code),
                "correct": bool(v and v.get("passed")), "ptok": res["ptok"], "ctok": res["ctok"]}
    recs = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        done = 0
        for r in ex.map(do, jobs):
            recs.append(r); done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(jobs)}", flush=True)

    # hidden stratification (ANALYSIS ONLY): groups whose 4 parents are all hidden-wrong = true blind spot
    print("hidden-stratifying parents (analysis only, cached) ...", flush=True)
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        hids = dict(zip(ap_parents, ex.map(lambda k: hid_ok(*k), ap_parents)))
    strat = {(g["pid"], g["gi"]): ("all_parents_hidden_wrong" if not any(hids[(g["pid"], i)] for i in g["grp"])
                                   else "some_parent_hidden_correct") for g in sel}

    args.outdir.mkdir(parents=True, exist_ok=True)
    by = defaultdict(dict)
    for r in recs:
        by[(r["pid"], r["gi"])][r["arm"]] = r
    with (args.outdir / "group_records.jsonl").open("w") as f:
        for g in sel:
            k = (g["pid"], g["gi"])
            f.write(json.dumps({**{x: g[x] for x in ("pid", "gi", "grp", "n_disagreeing_inputs")},
                                "stratum": strat[k],
                                "D0_correct": by[k].get("D0_no_feedback", {}).get("correct"),
                                "D1_correct": by[k].get("D1_disagreement", {}).get("correct"),
                                "comparison": g["comparison"]}, ensure_ascii=False) + "\n")

    def agg(keys):
        d0 = sum(by[k]["D0_no_feedback"]["correct"] for k in keys)
        d1 = sum(by[k]["D1_disagreement"]["correct"] for k in keys)
        up = sum(1 for k in keys if not by[k]["D0_no_feedback"]["correct"] and by[k]["D1_disagreement"]["correct"])
        dn = sum(1 for k in keys if by[k]["D0_no_feedback"]["correct"] and not by[k]["D1_disagreement"]["correct"])
        return {"n": len(keys), "D0_correct": d0, "D1_correct": d1, "wins": up, "losses": dn}
    keys = [(g["pid"], g["gi"]) for g in sel]
    summary = {
        "allpass_groups": len(allpass_groups), "groups_with_disagreement": len(sel),
        "disagreement_incidence": round(incidence, 4),
        "overall": agg(keys),
        "all_parents_hidden_wrong": agg([k for k in keys if strat[k] == "all_parents_hidden_wrong"]),
        "some_parent_hidden_correct": agg([k for k in keys if strat[k] == "some_parent_hidden_correct"]),
        "code_valid": {arm: sum(r["code_valid"] for r in recs if r["arm"] == arm) for arm in ("D0_no_feedback", "D1_disagreement")},
        "tokens": {arm: {"ptok": sum(r["ptok"] for r in recs if r["arm"] == arm),
                         "ctok": sum(r["ctok"] for r in recs if r["arm"] == arm)} for arm in ("D0_no_feedback", "D1_disagreement")},
    }
    (args.outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
