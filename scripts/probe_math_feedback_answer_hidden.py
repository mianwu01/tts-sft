#!/usr/bin/env python3
"""OFFLINE diagnostic: answer-hidden MATH feedback for SqueezeEvolve recombination (Node 2).

Focused probe. Reuses existing AIME/HMMT loop-0 strip=false candidates. Does NOT touch the SE
orchestrator or any baseline output. Generates structured critic feedback under several arms,
recombines (candidates ALWAYS stripped), grades with the existing math verifier, writes per-record
JSONL + a summary. Diagnostic only — NOT a full in-loop run. No SFT.

Coverage (per dataset):
  - ALL mixed-eligible problems (loop0 has >=1 correct AND >=1 wrong candidate) — the informative set.
    Sub-tier by loop0 correctness: 'hard' (<=4) vs 'mid' (>=5).
  - Optional 'reach_floor' tier = pure-0 problems (no correct loop0 candidate). Recombination cannot
    reach correct from no correct ingredient, so M0/M1/M2 score 0 by construction; only the oracle (M3)
    can — this tier quantifies the answer-hidden-vs-oracle gap on capability-limited problems.

Arms (recombination scaffold is identical across arms — stay-close prompt + interleaved
"---- Solution i ----" blocks; arms differ ONLY by the feedback block content):
  M0_no_feedback                : stay-close recombination, no feedback blocks (clean control).
  M1_gold_free_structured       : critic sees problem + stripped candidate ONLY (no gold, no verdict).
  M2_verifier_aware_answer_hidden: code checks candidate FINAL ANSWER vs gold; critic sees problem +
                                  stripped candidate + verdict TEXT (accepted/rejected/no-final-answer)
                                  but NOT the gold string. Deployable (uses only the final-answer label).
  M3_gold_aware_oracle          : OPTIONAL upper bound. Critic sees the gold final answer. Leaky /
                                  oracle / NON-DEPLOYABLE. Leakage detected.

Per-group multi-sampling: each (problem, group, arm) is drawn --n-samples-per-group times with distinct
seeds to shrink the per-group flip noise floor (groups are the real loop-1 parent sets, capped/problem).

Outputs: outputs/node2_math_feedback_answer_hidden_probe/{feedback_records.jsonl,
         recomb_records.jsonl, summary.json}
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

FEEDBACK_ARMS = ["M1_gold_free_structured", "M2_verifier_aware_answer_hidden",
                 "M4_consistency_aware", "M3_gold_aware_oracle"]
ALL_ARMS = ["M0_no_feedback"] + FEEDBACK_ARMS

STRUCT_TAIL = (
    "Respond in EXACTLY this format and nothing else:\n"
    "STATUS: <one label>\n"
    "PRESERVE:\n- <point>\nISSUE:\n- <point>\nCHECK:\n- <point>\n")

M1_CRITIC = (
    "You are reviewing ONE candidate solution to a competition math problem. You do NOT know the "
    "correct answer and you have NO verifier result.\n\n"
    "Rules:\n"
    "- Do NOT solve the problem from scratch.\n"
    "- Do NOT introduce a new final answer.\n"
    "- Do NOT write 'the correct answer is ...'.\n"
    "- Focus on local reasoning issues, missing cases, unjustified transitions, arithmetic "
    "inconsistencies, or useful partial reasoning that should be kept.\n\n"
    "STATUS must be one of: likely_correct, likely_wrong, partially_useful, uncertain.\n" + STRUCT_TAIL +
    "\nProblem:\n{problem}\n\nCandidate solution:\n{view}")

M2_CRITIC = (
    "You are reviewing ONE candidate solution to a competition math problem. An external verifier has "
    "checked ONLY the candidate's FINAL ANSWER against the reference. You are given the verifier verdict "
    "but NOT the reference answer.\n\n"
    "External verifier result: {verdict_text}\n\n"
    "Rules:\n"
    "- Do NOT infer or reveal the correct final answer.\n"
    "- Do NOT provide a replacement final answer.\n"
    "- If REJECTED, use the verdict only to conclude that something is wrong, and identify the "
    "suspicious reasoning steps from the candidate itself.\n"
    "- If ACCEPTED, say what should be preserved, but do NOT overclaim that the whole derivation is "
    "correct (only the final answer was checked).\n\n"
    "STATUS must be one of: verifier_accepted, verifier_rejected, no_final_answer, uncertain.\n" + STRUCT_TAIL +
    "\nProblem:\n{problem}\n\nCandidate solution:\n{view}")

M4_CRITIC = (
    "You are reviewing ONE candidate solution to a competition math problem. You do NOT know the "
    "correct answer and you have NO external verifier. You ARE given the distribution of final "
    "answers produced by {n} independent attempts at this problem by the same model (this candidate "
    "is one of them). Attempts are fallible: the most common answer is NOT guaranteed correct.\n\n"
    "Final-answer distribution across the {n} attempts:\n{dist}\n"
    "This candidate's final answer: {own} — {agree_text}.\n\n"
    "Rules:\n"
    "- Do NOT assume the majority answer is correct; treat agreement/disagreement only as a hint.\n"
    "- Do NOT reveal, assert, or invent a correct final answer.\n"
    "- If this candidate disagrees with most attempts, scrutinize ITS reasoning for the step most "
    "likely to be wrong (case analysis, arithmetic, unjustified transition).\n"
    "- If this candidate agrees with most attempts, say what should be preserved, but still flag "
    "any step that several attempts could plausibly have gotten wrong together.\n\n"
    "STATUS must be one of: matches_majority, minority_answer, no_final_answer, uncertain.\n" + STRUCT_TAIL +
    "\nProblem:\n{problem}\n\nCandidate solution:\n{view}")

M3_CRITIC = (
    "[ORACLE — NON-DEPLOYABLE DIAGNOSTIC] You are reviewing ONE candidate solution to a competition "
    "math problem. You are given the correct final answer to inform your judgement.\n\n"
    "Correct final answer: {gold}\n\n"
    "Give structured repair feedback that would help synthesize a correct solution. Do not solve from "
    "scratch; point at what to preserve and what to fix in THIS candidate.\n\n"
    "STATUS must be one of: likely_correct, likely_wrong, uncertain.\n" + STRUCT_TAIL +
    "\nProblem:\n{problem}\n\nCandidate solution:\n{view}")

STAYCLOSE = (
    "Correctness is the primary goal. However, to the extent possible, keep the final solution close to "
    "the candidate attempts. Prefer repairing, combining, and clarifying useful parts of the candidate "
    "solutions over writing a completely different solution from scratch. Only deviate substantially "
    "from the candidate attempts if their approaches are clearly flawed.")
RECOMB_TAIL = ("\nNow synthesize a single improved solution. End with the final answer in \\boxed{}.")

POS_VERDICTS = {"likely_correct", "verifier_accepted", "matches_majority"}
NEG_VERDICTS = {"likely_wrong", "verifier_rejected", "no_final_answer", "minority_answer"}
UNUSABLE_FB = ("STATUS: uncertain\nPRESERVE:\n- (none)\nISSUE:\n- (no structured feedback available "
               "for this candidate)\nCHECK:\n- (review this candidate independently)")


def parse_status(feedback: str) -> str:
    m = re.search(r"status\s*:\s*([a-z_]+)", (feedback or "").lower())
    return m.group(1) if m else "unparsed"


def leakage_flags(feedback: str, gold: str) -> dict:
    fb = feedback or ""
    low = fb.lower()
    g = (gold or "").strip()
    gnorm = normalize_math_answer(g)
    exact = bool(g) and (g in fb)
    norm_hit = bool(gnorm) and len(gnorm) >= 2 and gnorm in re.sub(r"\s+", "", fb)
    phrase = any(p in low for p in [
        "the correct answer is", "the answer is", "correct final answer is",
        "the final answer is", "reference answer", "gold answer"])
    return {"leak_exact_gold": exact, "leak_norm_gold": norm_hit, "leak_phrase": phrase,
            "leak_any": bool(exact or norm_hit or phrase)}


def tier_of(ncorr: int) -> str:
    if ncorr == 0: return "reach_floor"
    return "hard" if ncorr <= 4 else "mid"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", default="aime,hmmt")
    ap.add_argument("--max-mixed-per-ds", type=int, default=999, help="cap on mixed-eligible problems/ds.")
    ap.add_argument("--include-pure0", action="store_true", default=True, help="add pure-0 reach-floor tier.")
    ap.add_argument("--no-pure0", dest="include_pure0", action="store_false")
    ap.add_argument("--n-groups", type=int, default=16, help="groups/problem (reuse real loop1 parent_ids).")
    ap.add_argument("--n-samples-per-group", type=int, default=3)
    ap.add_argument("--n-samples-reach-floor", type=int, default=1,
                    help="samples/group on the pure-0 tier (flip noise matters less at ~0 density).")
    ap.add_argument("--run-m3", action="store_true", default=True)
    ap.add_argument("--no-m3", dest="run_m3", action="store_false")
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Thinking-2507")
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--max-tokens-feedback", type=int, default=10240)
    ap.add_argument("--max-tokens-recomb", type=int, default=16384)
    ap.add_argument("--temperature", type=float, default=1.0, help="recombination temp (match SE sampling).")
    ap.add_argument("--temperature-feedback", type=float, default=0.1,
                    help="critic/feedback temp — low so feedback is careful/near-deterministic.")
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--concurrency", type=int, default=80)
    ap.add_argument("--outdir", type=Path, default=Path("outputs/node2_math_feedback_answer_hidden_probe"))
    args = ap.parse_args()

    arms = ALL_ARMS if args.run_m3 else [a for a in ALL_ARMS if a != "M3_gold_aware_oracle"]
    fb_arms = [a for a in FEEDBACK_ARMS if a in arms]
    S = args.n_samples_per_group

    from openai import OpenAI
    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=7200)
    sem = threading.Semaphore(args.concurrency)

    def call(prompt, max_tokens, seed, temperature=None):
        last = None
        temp = args.temperature if temperature is None else temperature
        for attempt in range(4):
            try:
                with sem:
                    r = client.chat.completions.create(
                        model=args.model, messages=[{"role": "user", "content": prompt}],
                        temperature=temp, top_p=args.top_p, max_tokens=max_tokens,
                        seed=seed, extra_body={"top_k": args.top_k})
                ch = r.choices[0]; u = r.usage
                return {"text": ch.message.content or "", "finish": ch.finish_reason,
                        "ptok": getattr(u, "prompt_tokens", 0), "ctok": getattr(u, "completion_tokens", 0)}
            except Exception as e:  # noqa: BLE001
                last = e; time.sleep(min(20, 2 ** attempt))
        return {"text": "", "finish": "error", "ptok": 0, "ctok": 0, "err": str(last)}

    # ---- load loop0 candidates, grade, build STRIPPED views, pick problems ----
    problems = {}
    for ds in args.datasets.split(","):
        f = _REPO / f"outputs/node1_se_loop5_32k_temp1_{ds}_non_saturated/se.jsonl.loop_candidates.jsonl"
        l0 = defaultdict(dict); groups = defaultdict(list); meta = {}
        for line in f.open():
            r = json.loads(line)
            pid = r["id"]
            if r["loop_index"] == 0:
                c = int(r["candidate_id"].rsplit("cand", 1)[-1])
                l0[pid][c] = r["full_response"] or ""
                meta[pid] = {"problem": r["question"], "gold": str(r["answer"])}
            elif r["loop_index"] == 1 and r.get("parent_ids") is not None:
                groups[pid].append(list(r["parent_ids"]))
        scored = []
        for pid, cmap in l0.items():
            gold = meta[pid]["gold"]
            corr = {c: is_exact_match(extract_final_answer(t), gold) for c, t in cmap.items()}
            scored.append((pid, sum(corr.values()), len(cmap), cmap, corr, gold))
        mixed = sorted([s for s in scored if 1 <= s[1] <= s[2] - 1], key=lambda x: x[1])[: args.max_mixed_per_ds]
        pick = list(mixed)
        if args.include_pure0:
            pick += [s for s in scored if s[1] == 0]
        for pid, ncorr, n, cmap, corr, gold in pick:
            cands = {c: {"idx": c, "stripped": strip_think_blocks(cmap[c]),
                         "pred": extract_final_answer(cmap[c]), "correct": bool(corr[c])} for c in cmap}
            # Gold-free population signal for M4: cluster the loop-0 final answers using the SAME
            # equivalence as the grader (is_exact_match merges e.g. \dfrac vs \frac; a plain
            # normalize key would not). Greedy pairwise clustering, n=16 so O(n^2) is trivial.
            clusters = []  # [{"rep": raw_pred, "n": count}]
            no_ans = 0
            for c in cands.values():
                p = c["pred"]
                if not p:
                    no_ans += 1
                    continue
                for cl in clusters:
                    if is_exact_match(p, cl["rep"]) or is_exact_match(cl["rep"], p):
                        cl["n"] += 1
                        break
                else:
                    clusters.append({"rep": p, "n": 1})
            clusters.sort(key=lambda cl: -cl["n"])
            for c in cands.values():  # annotate each candidate with its agreement count / mode flag
                c["n_match"], c["is_mode"] = 0, False
                if c["pred"]:
                    for ci, cl in enumerate(clusters):
                        if is_exact_match(c["pred"], cl["rep"]) or is_exact_match(cl["rep"], c["pred"]):
                            c["n_match"], c["is_mode"] = cl["n"], ci == 0
                            break
            dist_lines = [f"- answer {cl['rep']} — {cl['n']} attempt(s)" for cl in clusters]
            if no_ans:
                dist_lines.append(f"- no final answer extracted — {no_ans} attempt(s)")
            mode_rep = clusters[0]["rep"] if clusters else None
            problems[pid] = {"ds": ds, "problem": meta[pid]["problem"], "gold": gold, "cands": cands,
                             "groups": groups[pid][: args.n_groups], "loop0_correct": ncorr,
                             "loop0_n": n, "tier": tier_of(ncorr),
                             "dist_text": "\n".join(dist_lines),
                             "mode_count": clusters[0]["n"] if clusters else 0,
                             "mode_equals_gold": bool(mode_rep) and is_exact_match(mode_rep, gold)}
    by_tier = defaultdict(int)
    for d in problems.values(): by_tier[d["tier"]] += 1
    print(f"selected {len(problems)} problems  tiers={dict(by_tier)}  samples/group={S}", flush=True)
    for p, d in sorted(problems.items(), key=lambda kv: (kv[1]["ds"], kv[1]["loop0_correct"])):
        print(f"  {p} ({d['ds']}, {d['tier']}, loop0 {d['loop0_correct']}/{d['loop0_n']}, {len(d['groups'])} groups)", flush=True)

    # ---- feedback for every candidate used in a selected group ----
    fb_jobs = [(pid, idx, arm) for pid, d in problems.items()
               for idx in sorted({i for g in d["groups"] for i in g}) for arm in fb_arms]
    print(f"feedback calls: {len(fb_jobs)}", flush=True)
    feedback = defaultdict(dict)

    def do_fb(job):
        pid, idx, arm = job
        d = problems[pid]; c = d["cands"][idx]; view = c["stripped"]
        extra = {}
        if arm == "M1_gold_free_structured":
            prompt = M1_CRITIC.format(problem=d["problem"], view=view)
        elif arm == "M2_verifier_aware_answer_hidden":
            vt = ("final answer accepted" if c["correct"]
                  else ("no final answer extracted" if not c["pred"] else "final answer rejected"))
            prompt = M2_CRITIC.format(problem=d["problem"], view=view, verdict_text=vt)
        elif arm == "M4_consistency_aware":
            if not c["pred"]:
                agree_text = "no final answer was extracted from this candidate"
            elif c["is_mode"]:
                agree_text = f"matches {c['n_match']} of {d['loop0_n']} attempts (the most common answer)"
            else:
                agree_text = (f"matches {c['n_match']} of {d['loop0_n']} attempts (a minority answer; "
                              f"the most common answer appears {d['mode_count']} times)")
            prompt = M4_CRITIC.format(n=d["loop0_n"], dist=d["dist_text"],
                                      own=c["pred"] or "(none extracted)", agree_text=agree_text,
                                      problem=d["problem"], view=view)
            extra = {"own_matches_mode": c["is_mode"], "mode_equals_gold": d["mode_equals_gold"]}
        else:
            prompt = M3_CRITIC.format(problem=d["problem"], gold=d["gold"], view=view)
        res = call(prompt, args.max_tokens_feedback, args.seed, temperature=args.temperature_feedback)
        res.update(extra)
        res["raw_chars"] = len(res["text"])
        clean = strip_think_blocks(res["text"]).strip()
        res["status"] = parse_status(clean)
        if res["status"] == "unparsed":   # unusable -> uniform placeholder (don't pollute recomb prompt)
            clean = UNUSABLE_FB
        res["clean"] = clean
        res["leak"] = leakage_flags(clean, d["gold"])
        return (pid, idx, arm, res)

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        done = 0
        for pid, idx, arm, res in ex.map(do_fb, fb_jobs):
            feedback[(pid, idx)][arm] = res
            done += 1
            if done % 200 == 0: print(f"  feedback {done}/{len(fb_jobs)}", flush=True)

    # ---- recombination: identical stay-close scaffold; arms differ only by feedback blocks ----
    rc_jobs = [(pid, gi, s, arm) for pid, d in problems.items()
               for gi in range(len(d["groups"]))
               for s in range(S if d["tier"] != "reach_floor" else args.n_samples_reach_floor)
               for arm in arms]
    print(f"recombination calls: {len(rc_jobs)}", flush=True)

    def do_rc(job):
        pid, gi, s, arm = job
        d = problems[pid]; grp = d["groups"][gi]
        parts = [STAYCLOSE, "", f"Problem:\n{d['problem']}", ""]
        for j, idx in enumerate(grp, 1):
            parts.append(f"---- Solution {j} ----\n{d['cands'][idx]['stripped']}")
            if arm != "M0_no_feedback":
                parts.append(f"---- Feedback on Solution {j} ----\n{feedback[(pid, idx)][arm]['clean']}")
            parts.append("")
        parts.append(RECOMB_TAIL)
        res = call("\n".join(parts), args.max_tokens_recomb, args.seed + gi * 131 + s * 7919)
        res["pred"] = extract_final_answer(res["text"])
        res["correct"] = bool(is_exact_match(res["pred"], d["gold"]))
        return (pid, gi, s, arm, res)

    recomb = defaultdict(lambda: defaultdict(dict))  # pid -> arm -> (gi,s) -> res
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        done = 0
        for pid, gi, s, arm, res in ex.map(do_rc, rc_jobs):
            recomb[pid][arm][(gi, s)] = res
            done += 1
            if done % 200 == 0: print(f"  recomb {done}/{len(rc_jobs)}", flush=True)

    # ---- write per-record outputs ----
    args.outdir.mkdir(parents=True, exist_ok=True)
    with (args.outdir / "feedback_records.jsonl").open("w") as f:
        for (pid, idx), a in feedback.items():
            for arm, res in a.items():
                f.write(json.dumps({
                    "pid": pid, "ds": problems[pid]["ds"], "tier": problems[pid]["tier"], "cand_idx": idx,
                    "arm": arm, "candidate_correct": problems[pid]["cands"][idx]["correct"],
                    "candidate_pred": problems[pid]["cands"][idx]["pred"], "feedback": res["clean"],
                    "status": res["status"], "leak": res["leak"], "fb_chars": len(res["clean"]),
                    "raw_chars": res["raw_chars"], "finish": res["finish"],
                    "own_matches_mode": res.get("own_matches_mode"),
                    "mode_equals_gold": res.get("mode_equals_gold"),
                    "ptok": res["ptok"], "ctok": res["ctok"]}, ensure_ascii=False) + "\n")
    with (args.outdir / "recomb_records.jsonl").open("w") as f:
        for pid, a in recomb.items():
            for arm, cells in a.items():
                for (gi, s), res in cells.items():
                    f.write(json.dumps({
                        "pid": pid, "ds": problems[pid]["ds"], "tier": problems[pid]["tier"],
                        "group": gi, "sample": s, "arm": arm, "pred": res["pred"], "correct": res["correct"],
                        "finish": res["finish"], "text": res["text"],
                        "ptok": res["ptok"], "ctok": res["ctok"]}, ensure_ascii=False) + "\n")

    # ---- aggregate ----
    def cells(pid, arm): return recomb[pid][arm]
    pids_all = list(problems)
    summary = {"n_problems": len(problems), "n_groups": args.n_groups, "n_samples_per_group": S,
               "n_samples_reach_floor": args.n_samples_reach_floor,
               "tiers": dict(by_tier), "arms_run": arms,
               "params": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
               "problems": {p: {"ds": d["ds"], "tier": d["tier"], "loop0_correct": d["loop0_correct"],
                                "loop0_n": d["loop0_n"], "n_groups": len(d["groups"]),
                                "mode_count": d["mode_count"],
                                "mode_equals_gold": d["mode_equals_gold"]}
                            for p, d in problems.items()},
               "arms": {}, "by_tier": {}, "flips_vs_M0": {}, "flips_vs_M0_by_tier": {},
               "feedback_quality": {}}

    def agg(pids, arm):
        trials = [r for pid in pids for r in cells(pid, arm).values()]
        cor = sum(r["correct"] for r in trials)
        solved = sum(1 for pid in pids if any(r["correct"] for r in cells(pid, arm).values()))
        return {"solved_problems": solved, "n_problems": len(pids), "correct_traces": cor,
                "total_trials": len(trials), "density": round(cor / max(1, len(trials)), 4),
                "recomb_ctok": sum(r["ctok"] for r in trials), "recomb_ptok": sum(r["ptok"] for r in trials)}

    for arm in arms:
        summary["arms"][arm] = agg(pids_all, arm)
    for t in ["mid", "hard", "reach_floor"]:
        pids = [p for p in pids_all if problems[p]["tier"] == t]
        if pids:
            summary["by_tier"][t] = {arm: agg(pids, arm) for arm in arms}

    def flips(pids, arm):
        win = loss = same = 0
        for pid in pids:
            for key in cells(pid, "M0_no_feedback"):
                a = cells(pid, arm)[key]["correct"]; b = cells(pid, "M0_no_feedback")[key]["correct"]
                if a and not b: win += 1
                elif b and not a: loss += 1
                else: same += 1
        return {"win": win, "loss": loss, "net": win - loss, "same": same}

    for arm in arms:
        if arm == "M0_no_feedback": continue
        summary["flips_vs_M0"][arm] = flips(pids_all, arm)
        summary["flips_vs_M0_by_tier"][arm] = {
            t: flips([p for p in pids_all if problems[p]["tier"] == t], arm)
            for t in ["mid", "hard", "reach_floor"] if any(problems[p]["tier"] == t for p in pids_all)}

    for arm in fb_arms:
        rows = [a[arm] for a in feedback.values() if arm in a]
        n = len(rows); agree = known = 0
        for (pid, idx), a in feedback.items():
            if arm not in a: continue
            st = a[arm]["status"]
            if st in POS_VERDICTS: pred = True
            elif st in NEG_VERDICTS: pred = False
            else: continue
            known += 1
            if pred == problems[pid]["cands"][idx]["correct"]: agree += 1
        summary["feedback_quality"][arm] = {
            "n": n, "avg_chars": round(sum(len(r["clean"]) for r in rows) / max(1, n), 1),
            "unparsed_status": sum(r["status"] == "unparsed" for r in rows),
            "leak_rate": round(sum(r["leak"]["leak_any"] for r in rows) / max(1, n), 4),
            "phrase_leak": sum(r["leak"]["leak_phrase"] for r in rows),
            "status_dist": dict(sorted(((s, sum(r["status"] == s for r in rows)) for s in
                                        {r["status"] for r in rows}), key=lambda x: -x[1])),
            "verdict_vs_actual_agreement": round(agree / max(1, known), 4) if known else None,
            "fb_ptok": sum(r["ptok"] for r in rows), "fb_ctok": sum(r["ctok"] for r in rows)}
    (args.outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("arms", "by_tier", "flips_vs_M0", "flips_vs_M0_by_tier",
                                              "feedback_quality")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
