#!/usr/bin/env python3
"""R2c-math OFFLINE probe: does EXECUTABLE-CLAIM feedback (the math analog of public tests)
beat M5 where it matters — the reach floor?

M6 = M5 + "EXECUTABLE CHECKS": per candidate, a claim-extractor model call writes up to 3
self-contained Python snippets that verify the candidate's load-bearing intermediate claims
WITHOUT the gold answer (brute-force a small instance, verify a recurrence/identity/count,
substitute back into constraints). A sandbox runs them; SUPPORTED/REFUTED verdicts (+detail)
are appended deterministically to the candidate's existing M5 feedback block. The paired
M6-vs-M5 delta therefore isolates exactly the executable-check ingredient.

Scope: the 17 hard + reach_floor problems from the canonical probe; 16 real loop-1 groups;
3 samples/group BOTH tiers; same per-trial seeds as the canonical/M5 runs.
Reuse: M5 feedback text from outputs/node2_math_feedback_m5_combined/feedback_records.jsonl;
M5 recomb trials that already exist (hard s0-2, reach_floor s0); only missing M5 trials
(reach_floor s1,s2) and all M6 trials are generated.

Offline diagnostic only — no orchestrator change, no SFT. Outputs:
outputs/node2_math_r2c_exec_probe/{claims.jsonl, feedback_records.jsonl, recomb_records.jsonl, summary.json}
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys, tempfile, threading, time, os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "external/squeeze-evolve/src"))
from tts_sft.answer_extraction import extract_final_answer, is_exact_match  # noqa: E402
from squeeze_evolve.common import strip_think_blocks  # noqa: E402

CANON = _REPO / "outputs/node2_math_feedback_answer_hidden_probe"
M5DIR = _REPO / "outputs/node2_math_feedback_m5_combined"

EXTRACTOR = (
    "You are analyzing ONE candidate solution to a competition math problem. Extract up to 3 of the "
    "candidate's most LOAD-BEARING intermediate claims that can be CHECKED BY COMPUTATION without "
    "knowing the official answer. Good checks: brute-force a small instance of the problem and compare "
    "against the candidate's formula/count for that instance; verify a claimed recurrence, identity, "
    "or numeric equality; substitute the candidate's constructed values back into the problem's "
    "constraints.\n\n"
    "For each claim output EXACTLY this format:\n"
    "CLAIM <i>: <one-sentence statement of what the candidate asserts>\n"
    "```python\n"
    "# self-contained python3 (stdlib + math/itertools/fractions/sympy only), must finish in <8s.\n"
    "# MUST end by printing exactly one line: either\n"
    "#   VERDICT: SUPPORTED — <short detail>\n"
    "# or\n"
    "#   VERDICT: REFUTED — expected <what the candidate claims>, computed <what the code found>\n"
    "...\n"
    "```\n\n"
    "Rules:\n"
    "- The code must NOT assume or hardcode the official answer (it may compute things from scratch).\n"
    "- The code MUST actually COMPARE the computed value against the candidate's claimed value with an "
    "if/else and print SUPPORTED only when they match (within a small tolerance for simulations); "
    "NEVER print an unconditional verdict.\n"
    "- Prefer claims whose failure would invalidate the candidate's final answer.\n"
    "- Each snippet independent and deterministic; no input(), no network, no files.\n"
    "- If nothing in the candidate is computationally checkable, output exactly: NO_CHECKABLE_CLAIMS\n\n"
    "Problem:\n{problem}\n\nCandidate solution:\n{view}")

STAYCLOSE = (
    "Correctness is the primary goal. However, to the extent possible, keep the final solution close to "
    "the candidate attempts. Prefer repairing, combining, and clarifying useful parts of the candidate "
    "solutions over writing a completely different solution from scratch. Only deviate substantially "
    "from the candidate attempts if their approaches are clearly flawed.")
RECOMB_TAIL = (
    "\nNow synthesize a single improved solution. Do NOT mention the feedback, the verifier, or the "
    "other attempts in your solution — write a self-contained derivation. End with the final answer "
    "in \\boxed{}.")


def run_snippet(code: str, timeout: int = 10) -> tuple[str, str]:
    """Execute one claim-check snippet in a subprocess. Returns (status, detail)."""
    path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(code)
            path = f.name
        env = {k: v for k, v in os.environ.items()
               if not k.lower().endswith("_proxy") and k != "ALL_PROXY"}
        p = subprocess.run([sys.executable, path], capture_output=True, text=True,
                           timeout=timeout, env=env)
        out = (p.stdout or "").strip().splitlines()
        last = next((l for l in reversed(out) if l.strip().upper().startswith("VERDICT:")), None)
        if last is None:
            err = (p.stderr or "").strip().splitlines()
            return ("exec_failed", (err[-1] if err else "no VERDICT line printed")[:200])
        body = last.split(":", 1)[1].strip()
        up = body.upper()
        if up.startswith("SUPPORTED"):
            return ("supported", body[:300])
        if up.startswith("REFUTED"):
            return ("refuted", body[:300])
        return ("exec_failed", f"unrecognized verdict: {body[:150]}")
    except subprocess.TimeoutExpired:
        return ("timeout", f"exceeded {timeout}s")
    except Exception as e:  # noqa: BLE001
        return ("exec_failed", f"{type(e).__name__}: {e}"[:200])
    finally:
        if path:
            try: os.unlink(path)
            except OSError: pass


def parse_claims(text: str) -> list[dict]:
    clean = strip_think_blocks(text or "").strip()
    if "NO_CHECKABLE_CLAIMS" in clean:
        return []
    out = []
    # pair each "CLAIM i: ..." with the code block that follows it
    pattern = re.compile(r"CLAIM\s*\d*\s*:\s*(.+?)\n```python\s*\n(.*?)```", re.DOTALL)
    for stmt, code in pattern.findall(clean):
        out.append({"claim": " ".join(stmt.split())[:400], "code": code.strip()})
        if len(out) == 3:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Thinking-2507")
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--max-tokens-extract", type=int, default=10240)
    ap.add_argument("--max-tokens-recomb", type=int, default=16384)
    ap.add_argument("--temperature-extract", type=float, default=0.1)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--n-samples", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--concurrency", type=int, default=80)
    ap.add_argument("--smoke", type=int, default=0, help="limit to N problems (0=all 17)")
    ap.add_argument("--outdir", type=Path, default=Path("outputs/node2_math_r2c_exec_probe"))
    args = ap.parse_args()

    canon = json.load((CANON / "summary.json").open())
    targets = sorted(p for p, m in canon["problems"].items() if m["tier"] in ("hard", "reach_floor"))
    if args.smoke:
        targets = (sorted([p for p in targets if canon["problems"][p]["tier"] == "hard"])[:1] +
                   sorted([p for p in targets if canon["problems"][p]["tier"] == "reach_floor"])[:args.smoke - 1])
    tier = {p: canon["problems"][p]["tier"] for p in targets}

    # ---- rebuild problems/groups (same as canonical) ----
    problems = {}
    for ds in ["aime", "hmmt"]:
        f = _REPO / f"outputs/node1_se_loop5_32k_temp1_{ds}_non_saturated/se.jsonl.loop_candidates.jsonl"
        l0 = defaultdict(dict); groups = defaultdict(list); meta = {}
        for line in f.open():
            r = json.loads(line)
            pid = r["id"]
            if pid not in tier:
                continue
            if r["loop_index"] == 0:
                c = int(r["candidate_id"].rsplit("cand", 1)[-1])
                l0[pid][c] = r["full_response"] or ""
                meta[pid] = {"problem": r["question"], "gold": str(r["answer"])}
            elif r["loop_index"] == 1 and r.get("parent_ids") is not None:
                groups[pid].append(list(r["parent_ids"]))
        for pid, cmap in l0.items():
            problems[pid] = {"ds": ds, "problem": meta[pid]["problem"], "gold": meta[pid]["gold"],
                             "tier": tier[pid], "groups": groups[pid][:16],
                             "cands": {c: {"stripped": strip_think_blocks(t),
                                           "pred": extract_final_answer(t)} for c, t in cmap.items()}}
    print(f"{len(problems)} problems ({sum(1 for p in problems.values() if p['tier']=='hard')} hard / "
          f"{sum(1 for p in problems.values() if p['tier']=='reach_floor')} reach_floor)", flush=True)

    # ---- M5 feedback text (reused verbatim from the M5 combined run) ----
    m5fb = {}
    for line in (M5DIR / "feedback_records.jsonl").open():
        r = json.loads(line)
        if r["pid"] in problems:
            m5fb[(r["pid"], r["cand_idx"])] = r["feedback"]

    # ---- existing M5 recomb trials (reuse; only generate the missing ones) ----
    m5_have = {}
    for line in (M5DIR / "recomb_records.jsonl").open():
        r = json.loads(line)
        if r["pid"] in problems and r["sample"] < args.n_samples:
            m5_have[(r["pid"], r["group"], r["sample"])] = {"pred": r["pred"], "correct": r["correct"],
                                                            "finish": r["finish"], "text": r["text"],
                                                            "ptok": r["ptok"], "ctok": r["ctok"],
                                                            "reused": True}

    from openai import OpenAI
    client = OpenAI(base_url=args.base_url, api_key="EMPTY", timeout=7200)
    sem = threading.Semaphore(args.concurrency)

    def call(prompt, max_tokens, seed, temperature):
        last = None
        for attempt in range(4):
            try:
                with sem:
                    r = client.chat.completions.create(
                        model=args.model, messages=[{"role": "user", "content": prompt}],
                        temperature=temperature, top_p=0.95, max_tokens=max_tokens,
                        seed=seed, extra_body={"top_k": 20})
                ch = r.choices[0]; u = r.usage
                return {"text": ch.message.content or "", "finish": ch.finish_reason,
                        "ptok": getattr(u, "prompt_tokens", 0), "ctok": getattr(u, "completion_tokens", 0)}
            except Exception as e:  # noqa: BLE001
                last = e; time.sleep(min(20, 2 ** attempt))
        return {"text": "", "finish": "error", "ptok": 0, "ctok": 0, "err": str(last)}

    # ---- stage 1+2: claim extraction + sandbox per candidate ----
    cand_jobs = [(pid, c) for pid, d in problems.items()
                 for c in sorted({i for g in d["groups"] for i in g})]
    print(f"claim-extraction calls: {len(cand_jobs)}", flush=True)
    checks = {}  # (pid,c) -> list of {claim, code, status, detail}

    def do_extract(job):
        pid, c = job
        d = problems[pid]
        res = call(EXTRACTOR.format(problem=d["problem"], view=d["cands"][c]["stripped"]),
                   args.max_tokens_extract, args.seed, args.temperature_extract)
        claims = parse_claims(res["text"])
        for cl in claims:
            cl["status"], cl["detail"] = run_snippet(cl["code"])
        return pid, c, claims, res["ptok"], res["ctok"], res["finish"]

    ex_p = ex_c = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        done = 0
        for pid, c, claims, p_, c_, fin in ex.map(do_extract, cand_jobs):
            checks[(pid, c)] = claims
            ex_p += p_; ex_c += c_
            done += 1
            if done % 50 == 0: print(f"  extract {done}/{len(cand_jobs)}", flush=True)

    # ---- stage 3: M6 feedback = M5 feedback + EXECUTABLE CHECKS section ----
    def m6_feedback(pid, c):
        base = m5fb[(pid, c)]
        cls = checks.get((pid, c)) or []
        if not cls:
            return base + "\n\nEXECUTABLE CHECKS:\n- (no computationally checkable claims found)"
        lines = ["", "", "EXECUTABLE CHECKS (the candidate's key claims were verified by running code):"]
        for cl in cls:
            tag = {"supported": "SUPPORTED", "refuted": "REFUTED",
                   "timeout": "INCONCLUSIVE (timeout)", "exec_failed": "INCONCLUSIVE (check failed)"}[cl["status"]]
            det = f" — {cl['detail']}" if cl["status"] in ("supported", "refuted") else ""
            lines.append(f"- CLAIM: {cl['claim']}\n  RESULT: {tag}{det}")
        return base + "\n".join(lines)

    # ---- stage 4: recombination (paired seeds; M5 missing trials + all M6) ----
    trials = [(pid, gi, s) for pid, d in problems.items()
              for gi in range(len(d["groups"])) for s in range(args.n_samples)]
    rc_jobs = [(pid, gi, s, arm) for (pid, gi, s) in trials for arm in ("M5", "M6")
               if not (arm == "M5" and (pid, gi, s) in m5_have)]
    print(f"recomb trials {len(trials)}/arm; new generation calls: {len(rc_jobs)} "
          f"(M5 reused: {len(m5_have)})", flush=True)

    def do_rc(job):
        pid, gi, s, arm = job
        d = problems[pid]; grp = d["groups"][gi]
        parts = [STAYCLOSE, "", f"Problem:\n{d['problem']}", ""]
        for j, c in enumerate(grp, 1):
            fb = m5fb[(pid, c)] if arm == "M5" else m6_feedback(pid, c)
            parts.append(f"---- Solution {j} ----\n{d['cands'][c]['stripped']}")
            parts.append(f"---- Feedback on Solution {j} ----\n{fb}")
            parts.append("")
        parts.append(RECOMB_TAIL)
        res = call("\n".join(parts), args.max_tokens_recomb, args.seed + gi * 131 + s * 7919,
                   args.temperature)
        res["pred"] = extract_final_answer(res["text"])
        res["correct"] = bool(is_exact_match(res["pred"], d["gold"]))
        return pid, gi, s, arm, res

    recomb = {("M5", k[0], k[1], k[2]): v for k, v in m5_have.items()}
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        done = 0
        for pid, gi, s, arm, res in ex.map(do_rc, rc_jobs):
            recomb[(arm, pid, gi, s)] = res
            done += 1
            if done % 100 == 0: print(f"  recomb {done}/{len(rc_jobs)}", flush=True)

    # ---- write ----
    args.outdir.mkdir(parents=True, exist_ok=True)
    with (args.outdir / "claims.jsonl").open("w") as f:
        for (pid, c), cls in checks.items():
            f.write(json.dumps({"pid": pid, "tier": problems[pid]["tier"], "cand_idx": c,
                                "cand_pred": problems[pid]["cands"][c]["pred"],
                                "n_claims": len(cls), "claims": cls}, ensure_ascii=False) + "\n")
    with (args.outdir / "feedback_records.jsonl").open("w") as f:
        for (pid, c) in checks:
            f.write(json.dumps({"pid": pid, "cand_idx": c, "arm": "M6_exec_claims",
                                "feedback": m6_feedback(pid, c)}, ensure_ascii=False) + "\n")
    with (args.outdir / "recomb_records.jsonl").open("w") as f:
        for (arm, pid, gi, s), r in recomb.items():
            f.write(json.dumps({"pid": pid, "tier": problems[pid]["tier"], "group": gi, "sample": s,
                                "arm": arm, "pred": r.get("pred"), "correct": r["correct"],
                                "finish": r.get("finish"), "reused": r.get("reused", False),
                                "text": r.get("text", ""), "ptok": r.get("ptok", 0),
                                "ctok": r.get("ctok", 0)}, ensure_ascii=False) + "\n")

    # ---- aggregate ----
    summary = {"n_problems": len(problems), "n_trials_per_arm": len(trials),
               "params": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
               "extract_tokens": {"ptok": ex_p, "ctok": ex_c}, "arms": {}, "by_tier": {},
               "flips_M6_vs_M5": {}, "claims_stats": {}}
    for arm in ("M5", "M6"):
        cor = sum(recomb[(arm, *t)]["correct"] for t in trials)
        solved = {p: any(recomb[(arm, p, gi, s)]["correct"] for gi in range(16)
                         for s in range(args.n_samples)) for p in problems}
        summary["arms"][arm] = {"correct_traces": cor, "total": len(trials),
                                "density": round(cor / len(trials), 4),
                                "solved_problems": sum(solved.values())}
    for t in ("hard", "reach_floor"):
        sel = [tr for tr in trials if problems[tr[0]]["tier"] == t]
        summary["by_tier"][t] = {}
        for arm in ("M5", "M6"):
            cor = sum(recomb[(arm, *tr)]["correct"] for tr in sel)
            sp = len({tr[0] for tr in sel if recomb[(arm, *tr)]["correct"]})
            summary["by_tier"][t][arm] = {"correct": cor, "total": len(sel),
                                          "density": round(cor / max(1, len(sel)), 4),
                                          "solved_problems": sp}
        w = sum(1 for tr in sel if recomb[("M6", *tr)]["correct"] and not recomb[("M5", *tr)]["correct"])
        l = sum(1 for tr in sel if recomb[("M5", *tr)]["correct"] and not recomb[("M6", *tr)]["correct"])
        summary["flips_M6_vs_M5"][t] = {"win": w, "loss": l, "net": w - l}
    ncl = [len(v) for v in checks.values()]
    st = defaultdict(int)
    for cls in checks.values():
        for cl in cls: st[cl["status"]] += 1
    summary["claims_stats"] = {"candidates": len(checks), "no_claims": sum(1 for n in ncl if n == 0),
                               "avg_claims": round(sum(ncl) / max(1, len(ncl)), 2),
                               "verdicts": dict(st)}
    (args.outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("arms", "by_tier", "flips_M6_vs_M5", "claims_stats")},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
