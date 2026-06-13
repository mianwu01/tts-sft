#!/usr/bin/env python3
"""OFFLINE probe for Feedback-Augmented SqueezeEvolve (math: AIME/HMMT).

Reuses existing loop-0 strip=false candidates. Does NOT touch the SE orchestrator or any
baseline output. Generates critic feedback under 4 arms + a no-feedback baseline, recombines
(candidates ALWAYS stripped), grades with the existing math verifier, and writes per-record
JSONL + a summary. Small-scale probe (subsample problems/groups), not a full run.

Arms (feedback view varies; recombination candidate text is ALWAYS stripped_view):
  no_feedback | gold_free_full | gold_free_stripped | gold_aware_full | gold_aware_stripped

Outputs: outputs/node1_feedback_probe/{feedback_records.jsonl, recomb_records.jsonl, summary.json}
"""
from __future__ import annotations
import argparse, json, re, sys, threading, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "external/squeeze-evolve/src"))
from tts_sft.answer_extraction import extract_final_answer, is_exact_match, normalize_math_answer  # noqa: E402
from squeeze_evolve.common import strip_think_blocks  # noqa: E402

ARMS = ["no_feedback", "gold_free_full", "gold_free_stripped", "gold_aware_full", "gold_aware_stripped"]
FEEDBACK_ARMS = ["gold_free_full", "gold_free_stripped", "gold_aware_full", "gold_aware_stripped"]
VIEW = {"gold_free_full": "full", "gold_free_stripped": "stripped",
        "gold_aware_full": "full", "gold_aware_stripped": "stripped"}
GOLD_AWARE = {"gold_aware_full", "gold_aware_stripped"}

GOLD_FREE_CRITIC = (
    "You are reviewing a candidate solution to a competition math problem. Identify likely "
    "reasoning errors, missing steps, or suspicious assumptions. Do NOT provide the correct final "
    "answer. Do NOT solve the problem from scratch. Keep feedback concise (2-5 sentences). If the "
    "candidate appears correct, say so and note what should be preserved. Begin your reply with "
    "exactly 'VERDICT: appears correct' or 'VERDICT: likely has errors'.\n\n"
    "Problem:\n{problem}\n\nCandidate solution:\n{view}"
)
GOLD_AWARE_CRITIC = (
    "You are reviewing a candidate solution to a competition math problem. You are given the correct "
    "final answer ONLY to judge the candidate. You MUST NOT reveal, state, or write the correct answer "
    "anywhere in your feedback. Say whether the candidate's final answer appears consistent with the "
    "correct answer (without printing it) and give concise revision feedback (2-5 sentences). Begin "
    "your reply with exactly 'VERDICT: appears correct' or 'VERDICT: likely has errors'.\n\n"
    "Problem:\n{problem}\n\nCorrect final answer (FOR YOUR JUDGEMENT ONLY — DO NOT REVEAL): {gold}\n\n"
    "Candidate solution:\n{view}"
)
RECOMB_HEADER = "Problem:\n{problem}\n\n"
RECOMB_TAIL_NOFB = ("Please synthesize a single improved solution. End with the final answer in "
                    "\\boxed{}.")
RECOMB_TAIL_FB = ("Please synthesize a single improved solution. Use the feedback to avoid mistakes "
                  "and preserve correct reasoning. End with the final answer in \\boxed{}.")


def leakage_flags(feedback: str, gold: str) -> dict:
    fb = feedback or ""
    low = fb.lower()
    g = (gold or "").strip()
    gnorm = normalize_math_answer(g)
    exact = bool(g) and (g in fb)
    norm_hit = bool(gnorm) and len(gnorm) >= 2 and gnorm in re.sub(r"\s+", "", fb)
    phrase = any(p in low for p in [
        "the correct answer is", "the answer is", "correct final answer is",
        "answer is \\boxed", "the final answer is", "gold answer"])
    boxed = bool(re.search(r"\\boxed\{", fb))
    return {"leak_exact_gold": exact, "leak_norm_gold": norm_hit,
            "leak_phrase": phrase, "leak_boxed": boxed,  # boxed is info-only (critics write math)
            "leak_any": bool(exact or norm_hit or phrase)}


def verdict_of(feedback: str) -> str:
    low = (feedback or "").lower()
    if "verdict: appears correct" in low:
        return "correct"
    if "verdict: likely has errors" in low or "verdict: has error" in low:
        return "error"
    # fallback heuristic
    if "appears correct" in low or "looks correct" in low:
        return "correct"
    if "error" in low or "incorrect" in low or "mistake" in low:
        return "error"
    return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", default="aime,hmmt")
    ap.add_argument("--n-problems-per-ds", type=int, default=3)
    ap.add_argument("--n-groups", type=int, default=4, help="groups/problem (reuse real loop1 parent_ids).")
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Thinking-2507")
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--max-tokens-feedback", type=int, default=2048)
    ap.add_argument("--max-tokens-recomb", type=int, default=16384)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--concurrency", type=int, default=24)
    ap.add_argument("--outdir", type=Path, default=Path("outputs/node1_feedback_probe"))
    args = ap.parse_args()

    from openai import OpenAI
    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=7200)
    sem = threading.Semaphore(args.concurrency)

    def call(prompt, max_tokens, seed):
        for attempt in range(4):
            try:
                with sem:
                    r = client.chat.completions.create(
                        model=args.model, messages=[{"role": "user", "content": prompt}],
                        temperature=args.temperature, top_p=args.top_p, max_tokens=max_tokens,
                        seed=seed, extra_body={"top_k": args.top_k})
                ch = r.choices[0]; u = r.usage
                return {"text": ch.message.content or "", "finish": ch.finish_reason,
                        "ptok": getattr(u, "prompt_tokens", 0), "ctok": getattr(u, "completion_tokens", 0)}
            except Exception as e:  # noqa: BLE001
                time.sleep(min(20, 2 ** attempt)); last = e
        return {"text": "", "finish": "error", "ptok": 0, "ctok": 0, "err": str(last)}

    # ---- Step 1+2: load loop0 candidates, grade, build views, pick problems/groups ----
    problems = {}   # pid -> dict(problem, gold, cands=[{idx,full,stripped,correct}], groups=[[idx...]])
    for ds in args.datasets.split(","):
        f = _REPO / f"outputs/node1_se_loop5_32k_temp1_{ds}_non_saturated/se.jsonl.loop_candidates.jsonl"
        l0 = defaultdict(dict); groups = defaultdict(list); meta = {}
        for line in f.open():
            r = json.loads(line)
            pid = r["id"]
            if r["loop_index"] == 0:
                c = int(r["candidate_id"].rsplit("cand", 1)[-1])
                full = r["full_response"] or ""
                l0[pid][c] = full
                meta[pid] = {"problem": r["question"], "gold": str(r["answer"])}
            elif r["loop_index"] == 1 and r.get("parent_ids") is not None:
                groups[pid].append(list(r["parent_ids"]))
        # pick informative problems: mixed loop0 correctness preferred
        scored = []
        for pid, cmap in l0.items():
            gold = meta[pid]["gold"]
            corr = {c: is_exact_match(extract_final_answer(t), gold) for c, t in cmap.items()}
            ncorr = sum(corr.values())
            scored.append((pid, ncorr, len(cmap), cmap, corr, gold))
        # prefer 1<=ncorr<=15, then by closeness to half
        scored.sort(key=lambda x: (0 if 1 <= x[1] <= x[2] - 1 else 1, abs(x[1] - x[2] / 2)))
        for pid, ncorr, n, cmap, corr, gold in scored[: args.n_problems_per_ds]:
            cands = {c: {"idx": c, "full": cmap[c], "stripped": strip_think_blocks(cmap[c]),
                         "correct": bool(corr[c])} for c in cmap}
            problems[pid] = {"ds": ds, "problem": meta[pid]["problem"], "gold": gold,
                             "cands": cands, "groups": groups[pid][: args.n_groups],
                             "loop0_correct": ncorr, "loop0_n": n}
    print(f"selected {len(problems)} problems: " +
          ", ".join(f"{p}(loop0 {d['loop0_correct']}/{d['loop0_n']})" for p, d in problems.items()), flush=True)

    # ---- Step 3: feedback for every candidate that appears in a selected group ----
    fb_jobs = []  # (pid, idx, arm)
    for pid, d in problems.items():
        used = sorted({i for g in d["groups"] for i in g})
        for idx in used:
            for arm in FEEDBACK_ARMS:
                fb_jobs.append((pid, idx, arm))
    print(f"feedback calls: {len(fb_jobs)} ({len(problems)} problems x candidates x 4 arms)", flush=True)
    feedback = defaultdict(dict)  # (pid,idx) -> arm -> result
    def do_fb(job):
        pid, idx, arm = job
        d = problems[pid]; c = d["cands"][idx]
        view = c["full"] if VIEW[arm] == "full" else c["stripped"]
        if arm in GOLD_AWARE:
            prompt = GOLD_AWARE_CRITIC.format(problem=d["problem"], gold=d["gold"], view=view)
        else:
            prompt = GOLD_FREE_CRITIC.format(problem=d["problem"], view=view)
        res = call(prompt, args.max_tokens_feedback, args.seed)
        res["leak"] = leakage_flags(res["text"], d["gold"])
        res["verdict"] = verdict_of(res["text"])
        return (pid, idx, arm, res)
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for pid, idx, arm, res in ex.map(do_fb, fb_jobs):
            feedback[(pid, idx)][arm] = res

    # ---- Step 4+5: recombination (5 arms) per group; candidates ALWAYS stripped ----
    rc_jobs = []  # (pid, gi, arm)
    for pid, d in problems.items():
        for gi in range(len(d["groups"])):
            for arm in ARMS:
                rc_jobs.append((pid, gi, arm))
    print(f"recombination calls: {len(rc_jobs)} ({len(problems)} problems x {args.n_groups} groups x 5 arms)", flush=True)
    def do_rc(job):
        pid, gi, arm = job
        d = problems[pid]; grp = d["groups"][gi]
        parts = [RECOMB_HEADER.format(problem=d["problem"])]
        for j, idx in enumerate(grp, 1):
            parts.append(f"Candidate solution {j}:\n{d['cands'][idx]['stripped']}\n")
            if arm != "no_feedback":
                fb = feedback[(pid, idx)][arm]["text"]
                parts.append(f"Feedback on candidate solution {j}:\n{fb}\n")
        parts.append(RECOMB_TAIL_NOFB if arm == "no_feedback" else RECOMB_TAIL_FB)
        prompt = "\n".join(parts)
        res = call(prompt, args.max_tokens_recomb, args.seed + gi)
        pred = extract_final_answer(res["text"])
        res["pred"] = pred; res["correct"] = bool(is_exact_match(pred, d["gold"]))
        return (pid, gi, arm, res)
    recomb = defaultdict(lambda: defaultdict(dict))  # pid -> arm -> gi -> res
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        done = 0
        for pid, gi, arm, res in ex.map(do_rc, rc_jobs):
            recomb[pid][arm][gi] = res
            done += 1
            if done % 50 == 0: print(f"  recomb {done}/{len(rc_jobs)}", flush=True)

    # ---- write per-record outputs ----
    args.outdir.mkdir(parents=True, exist_ok=True)
    with (args.outdir / "feedback_records.jsonl").open("w") as f:
        for (pid, idx), arms in feedback.items():
            for arm, res in arms.items():
                f.write(json.dumps({
                    "pid": pid, "ds": problems[pid]["ds"], "cand_idx": idx, "arm": arm,
                    "candidate_correct": problems[pid]["cands"][idx]["correct"],
                    "feedback": res["text"], "verdict": res["verdict"], "leak": res["leak"],
                    "fb_chars": len(res["text"]), "ptok": res["ptok"], "ctok": res["ctok"]}, ensure_ascii=False) + "\n")
    with (args.outdir / "recomb_records.jsonl").open("w") as f:
        for pid, arms in recomb.items():
            for arm, gis in arms.items():
                for gi, res in gis.items():
                    f.write(json.dumps({
                        "pid": pid, "ds": problems[pid]["ds"], "group": gi, "arm": arm,
                        "pred": res["pred"], "correct": res["correct"],
                        "ptok": res["ptok"], "ctok": res["ctok"], "finish": res["finish"]}, ensure_ascii=False) + "\n")

    # ---- Step 5/6: aggregate ----
    summary = {"n_problems": len(problems), "n_groups": args.n_groups, "arms": {},
               "params": vars(args) | {"outdir": str(args.outdir)}}
    summary["params"].pop("outdir", None)
    for arm in ARMS:
        solved = sum(1 for pid in problems if any(recomb[pid][arm][gi]["correct"] for gi in recomb[pid][arm]))
        n_traces = sum(recomb[pid][arm][gi]["correct"] for pid in problems for gi in recomb[pid][arm])
        total = sum(len(recomb[pid][arm]) for pid in problems)
        rtok_p = sum(recomb[pid][arm][gi]["ptok"] for pid in problems for gi in recomb[pid][arm])
        rtok_c = sum(recomb[pid][arm][gi]["ctok"] for pid in problems for gi in recomb[pid][arm])
        summary["arms"][arm] = {"solved": solved, "correct_traces": n_traces, "total_groups": total,
                                "density": round(n_traces / max(1, total), 4),
                                "recomb_ptok": rtok_p, "recomb_ctok": rtok_c}
    # feedback-quality per feedback arm
    summary["feedback_quality"] = {}
    for arm in FEEDBACK_ARMS:
        rows = [r for (pid, idx), arms in feedback.items() for a, r in arms.items() if a == arm]
        n = len(rows)
        leak = sum(r["leak"]["leak_any"] for r in rows)
        says_corr = sum(r["verdict"] == "correct" for r in rows)
        says_err = sum(r["verdict"] == "error" for r in rows)
        # agreement vs actual candidate correctness
        agree = tot_known = 0
        for (pid, idx), arms in feedback.items():
            if arm not in arms: continue
            v = arms[arm]["verdict"]
            if v == "unknown": continue
            actual = problems[pid]["cands"][idx]["correct"]
            tot_known += 1
            if (v == "correct") == actual: agree += 1
        ftok_p = sum(r["ptok"] for r in rows); ftok_c = sum(r["ctok"] for r in rows)
        summary["feedback_quality"][arm] = {
            "n": n, "avg_chars": round(sum(len(r["text"]) for r in rows) / max(1, n), 1),
            "leak_rate": round(leak / max(1, n), 4), "pct_says_correct": round(says_corr / max(1, n), 4),
            "pct_says_error": round(says_err / max(1, n), 4),
            "verdict_vs_actual_agreement": round(agree / max(1, tot_known), 4) if tot_known else None,
            "fb_ptok": ftok_p, "fb_ctok": ftok_c}
    (args.outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
