#!/usr/bin/env python3
"""M5 combined arm: verifier-verdict (M2) + margin-gated population-consistency (M4) feedback,
with mention-suppression in the recombination prompt. OFFLINE diagnostic on the SAME problems,
groups, and paired seeds as the canonical answer-hidden probe — every trial pairs 1:1 against the
existing M0/M1/M2/M4/M3 records in outputs/node2_math_feedback_answer_hidden_probe/.

Design deltas vs the canonical arms (everything else identical):
  - Critic prompt = M2 (verdict text, gold string hidden) + the M4 population final-answer
    distribution, EXCEPT on margin-gated problems: when the top two answer clusters are nearly
    tied AND the runner-up is substantial (margin <= GATE_MARGIN and second >= GATE_SECOND),
    the distribution is OMITTED (ambiguous consensus = harmful attractor; hmmt25-000010 case)
    and the critic sees verdict-only (pure M2).
  - Recombination tail adds mention-suppression: do not reference the feedback/verifier/attempts.

No orchestrator change, no SFT, canonical outputs untouched. New outdir only.
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

CANON = _REPO / "outputs/node2_math_feedback_answer_hidden_probe"
GATE_MARGIN = 1   # mode_count - second_count <= this ...
GATE_SECOND = 4   # ... AND second_count >= this  => omit distribution (ambiguous consensus)

STRUCT_TAIL = (
    "Respond in EXACTLY this format and nothing else:\n"
    "STATUS: <one label>\n"
    "PRESERVE:\n- <point>\nISSUE:\n- <point>\nCHECK:\n- <point>\n")

M5_CRITIC_WITH_DIST = (
    "You are reviewing ONE candidate solution to a competition math problem. An external verifier has "
    "checked ONLY the candidate's FINAL ANSWER against the reference. You are given the verifier verdict "
    "but NOT the reference answer. You are ALSO given the distribution of final answers produced by {n} "
    "independent attempts at this problem by the same model (this candidate is one of them). Attempts "
    "are fallible: the most common answer is NOT guaranteed correct.\n\n"
    "External verifier result: {verdict_text}\n\n"
    "Final-answer distribution across the {n} attempts:\n{dist}\n"
    "This candidate's final answer: {own} — {agree_text}.\n\n"
    "Rules:\n"
    "- Do NOT infer, reveal, or assert the correct final answer.\n"
    "- Do NOT provide a replacement final answer.\n"
    "- If REJECTED, use the verdict only to conclude that something is wrong; identify the suspicious "
    "reasoning steps from the candidate itself, and use disagreement with other attempts as a hint for "
    "WHERE the reasoning diverges.\n"
    "- If ACCEPTED, say what should be preserved, but do NOT overclaim that the whole derivation is "
    "correct (only the final answer was checked).\n"
    "- Do NOT assume the majority answer is correct.\n\n"
    "STATUS must be one of: verifier_accepted, verifier_rejected, no_final_answer, uncertain.\n" + STRUCT_TAIL +
    "\nProblem:\n{problem}\n\nCandidate solution:\n{view}")

M5_CRITIC_GATED = (  # ambiguous consensus -> verdict-only (identical in spirit to M2)
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

STAYCLOSE = (
    "Correctness is the primary goal. However, to the extent possible, keep the final solution close to "
    "the candidate attempts. Prefer repairing, combining, and clarifying useful parts of the candidate "
    "solutions over writing a completely different solution from scratch. Only deviate substantially "
    "from the candidate attempts if their approaches are clearly flawed.")
RECOMB_TAIL = (
    "\nNow synthesize a single improved solution. Do NOT mention the feedback, the verifier, or the "
    "other attempts in your solution — write a self-contained derivation. End with the final answer "
    "in \\boxed{}.")

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Thinking-2507")
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--max-tokens-feedback", type=int, default=10240)
    ap.add_argument("--max-tokens-recomb", type=int, default=16384)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--temperature-feedback", type=float, default=0.1)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--concurrency", type=int, default=80)
    ap.add_argument("--dry-run", action="store_true", help="build everything, print gate stats + a sample prompt, no API calls.")
    ap.add_argument("--outdir", type=Path, default=Path("outputs/node2_math_feedback_m5_combined"))
    args = ap.parse_args()

    # ---- canonical run is the source of truth for problem set / tiers / trial keys ----
    canon = json.load((CANON / "summary.json").open())
    canon_probs = canon["problems"]
    S_mixed, S_floor = canon["n_samples_per_group"], canon["n_samples_reach_floor"]
    canon_rc_keys = set()
    for line in (CANON / "recomb_records.jsonl").open():
        r = json.loads(line)
        if r["arm"] == "M0_no_feedback":
            canon_rc_keys.add((r["pid"], r["group"], r["sample"]))

    # ---- rebuild candidates/groups exactly like the canonical probe; assert agreement ----
    problems = {}
    for ds in ["aime", "hmmt"]:
        f = _REPO / f"outputs/node1_se_loop5_32k_temp1_{ds}_non_saturated/se.jsonl.loop_candidates.jsonl"
        l0 = defaultdict(dict); groups = defaultdict(list); meta = {}
        for line in f.open():
            r = json.loads(line)
            pid = r["id"]
            if pid not in canon_probs:
                continue
            if r["loop_index"] == 0:
                c = int(r["candidate_id"].rsplit("cand", 1)[-1])
                l0[pid][c] = r["full_response"] or ""
                meta[pid] = {"problem": r["question"], "gold": str(r["answer"])}
            elif r["loop_index"] == 1 and r.get("parent_ids") is not None:
                groups[pid].append(list(r["parent_ids"]))
        for pid, cmap in l0.items():
            gold = meta[pid]["gold"]
            cands = {c: {"idx": c, "stripped": strip_think_blocks(t),
                         "pred": extract_final_answer(t),
                         "correct": is_exact_match(extract_final_answer(t), gold)} for c, t in cmap.items()}
            clusters = []
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
            for c in cands.values():
                c["n_match"], c["is_mode"] = 0, False
                if c["pred"]:
                    for ci, cl in enumerate(clusters):
                        if is_exact_match(c["pred"], cl["rep"]) or is_exact_match(cl["rep"], c["pred"]):
                            c["n_match"], c["is_mode"] = cl["n"], ci == 0
                            break
            dist_lines = [f"- answer {cl['rep']} — {cl['n']} attempt(s)" for cl in clusters]
            if no_ans:
                dist_lines.append(f"- no final answer extracted — {no_ans} attempt(s)")
            mode_n = clusters[0]["n"] if clusters else 0
            second_n = clusters[1]["n"] if len(clusters) > 1 else 0
            gated = (mode_n - second_n) <= GATE_MARGIN and second_n >= GATE_SECOND
            ncorr = sum(c["correct"] for c in cands.values())
            problems[pid] = {"ds": ds, "problem": meta[pid]["problem"], "gold": gold, "cands": cands,
                             "groups": groups[pid][:16], "loop0_correct": ncorr, "loop0_n": len(cands),
                             "tier": canon_probs[pid]["tier"], "dist_text": "\n".join(dist_lines),
                             "mode_count": mode_n, "second_count": second_n, "gated": gated,
                             "mode_equals_gold": bool(clusters) and is_exact_match(clusters[0]["rep"], gold)}
    # asserts vs canonical
    assert set(problems) == set(canon_probs), "problem set mismatch vs canonical run"
    for pid, m in canon_probs.items():
        d = problems[pid]
        assert (d["loop0_correct"], d["tier"], d["mode_count"], d["mode_equals_gold"]) == \
               (m["loop0_correct"], m["tier"], m["mode_count"], m["mode_equals_gold"]), f"mismatch on {pid}"
    trial_keys = [(pid, gi, s) for pid, d in problems.items() for gi in range(len(d["groups"]))
                  for s in range(S_mixed if d["tier"] != "reach_floor" else S_floor)]
    assert set(trial_keys) == canon_rc_keys, "trial keys mismatch vs canonical M0 records"
    gated_pids = sorted(p for p, d in problems.items() if d["gated"])
    print(f"rebuild OK: {len(problems)} problems, {len(trial_keys)} trials — pairing verified vs canonical")
    print(f"margin-gated problems (distribution OMITTED; margin<={GATE_MARGIN} & second>={GATE_SECOND}): "
          f"{gated_pids}")
    for p in gated_pids:
        d = problems[p]
        print(f"  {p}: mode {d['mode_count']} vs second {d['second_count']} (tier {d['tier']})")

    def fb_prompt(pid, idx):
        d = problems[pid]; c = d["cands"][idx]
        vt = ("final answer accepted" if c["correct"]
              else ("no final answer extracted" if not c["pred"] else "final answer rejected"))
        if d["gated"]:
            return M5_CRITIC_GATED.format(verdict_text=vt, problem=d["problem"], view=c["stripped"])
        if not c["pred"]:
            agree = "no final answer was extracted from this candidate"
        elif c["is_mode"]:
            agree = f"matches {c['n_match']} of {d['loop0_n']} attempts (the most common answer)"
        else:
            agree = (f"matches {c['n_match']} of {d['loop0_n']} attempts (a minority answer; the most "
                     f"common answer appears {d['mode_count']} times)")
        return M5_CRITIC_WITH_DIST.format(n=d["loop0_n"], verdict_text=vt, dist=d["dist_text"],
                                          own=c["pred"] or "(none extracted)", agree_text=agree,
                                          problem=d["problem"], view=c["stripped"])

    if args.dry_run:
        pid = next(p for p, d in problems.items() if not d["gated"] and d["tier"] == "hard")
        idx = sorted({i for g in problems[pid]["groups"] for i in g})[0]
        print(f"\n--- SAMPLE M5 critic prompt ({pid}, cand {idx}) [first 1600 chars] ---")
        print(fb_prompt(pid, idx)[:1600])
        gp = gated_pids[0] if gated_pids else None
        if gp:
            gidx = sorted({i for g in problems[gp]["groups"] for i in g})[0]
            print(f"\n--- SAMPLE GATED prompt ({gp}, cand {gidx}) [first 700 chars] ---")
            print(fb_prompt(gp, gidx)[:700])
        print("\n--- RECOMB TAIL ---" + RECOMB_TAIL)
        return 0

    from openai import OpenAI
    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=7200)
    sem = threading.Semaphore(args.concurrency)

    def call(prompt, max_tokens, seed, temperature):
        last = None
        for attempt in range(4):
            try:
                with sem:
                    r = client.chat.completions.create(
                        model=args.model, messages=[{"role": "user", "content": prompt}],
                        temperature=temperature, top_p=args.top_p, max_tokens=max_tokens,
                        seed=seed, extra_body={"top_k": args.top_k})
                ch = r.choices[0]; u = r.usage
                return {"text": ch.message.content or "", "finish": ch.finish_reason,
                        "ptok": getattr(u, "prompt_tokens", 0), "ctok": getattr(u, "completion_tokens", 0)}
            except Exception as e:  # noqa: BLE001
                last = e; time.sleep(min(20, 2 ** attempt))
        return {"text": "", "finish": "error", "ptok": 0, "ctok": 0, "err": str(last)}

    # ---- feedback ----
    fb_jobs = [(pid, idx) for pid, d in problems.items()
               for idx in sorted({i for g in d["groups"] for i in g})]
    print(f"feedback calls: {len(fb_jobs)}", flush=True)
    feedback = {}

    def do_fb(job):
        pid, idx = job
        res = call(fb_prompt(pid, idx), args.max_tokens_feedback, args.seed,
                   temperature=args.temperature_feedback)
        res["raw_chars"] = len(res["text"])
        clean = strip_think_blocks(res["text"]).strip()
        res["status"] = parse_status(clean)
        if res["status"] == "unparsed":
            clean = UNUSABLE_FB
        res["clean"] = clean
        res["leak"] = leakage_flags(clean, problems[pid]["gold"])
        return (pid, idx, res)

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        done = 0
        for pid, idx, res in ex.map(do_fb, fb_jobs):
            feedback[(pid, idx)] = res
            done += 1
            if done % 100 == 0: print(f"  feedback {done}/{len(fb_jobs)}", flush=True)

    # ---- recombination (same paired seeds as canonical) ----
    print(f"recombination calls: {len(trial_keys)}", flush=True)

    def do_rc(key):
        pid, gi, s = key
        d = problems[pid]; grp = d["groups"][gi]
        parts = [STAYCLOSE, "", f"Problem:\n{d['problem']}", ""]
        for j, idx in enumerate(grp, 1):
            parts.append(f"---- Solution {j} ----\n{d['cands'][idx]['stripped']}")
            parts.append(f"---- Feedback on Solution {j} ----\n{feedback[(pid, idx)]['clean']}")
            parts.append("")
        parts.append(RECOMB_TAIL)
        res = call("\n".join(parts), args.max_tokens_recomb, args.seed + gi * 131 + s * 7919,
                   temperature=args.temperature)
        res["pred"] = extract_final_answer(res["text"])
        res["correct"] = bool(is_exact_match(res["pred"], d["gold"]))
        return (pid, gi, s, res)

    recomb = {}
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        done = 0
        for pid, gi, s, res in ex.map(do_rc, trial_keys):
            recomb[(pid, gi, s)] = res
            done += 1
            if done % 100 == 0: print(f"  recomb {done}/{len(trial_keys)}", flush=True)

    # ---- write ----
    args.outdir.mkdir(parents=True, exist_ok=True)
    with (args.outdir / "feedback_records.jsonl").open("w") as f:
        for (pid, idx), res in feedback.items():
            f.write(json.dumps({
                "pid": pid, "ds": problems[pid]["ds"], "tier": problems[pid]["tier"], "cand_idx": idx,
                "arm": "M5_combined", "gated": problems[pid]["gated"],
                "candidate_correct": problems[pid]["cands"][idx]["correct"],
                "candidate_pred": problems[pid]["cands"][idx]["pred"], "feedback": res["clean"],
                "status": res["status"], "leak": res["leak"], "fb_chars": len(res["clean"]),
                "raw_chars": res["raw_chars"], "finish": res["finish"],
                "own_matches_mode": problems[pid]["cands"][idx]["is_mode"],
                "mode_equals_gold": problems[pid]["mode_equals_gold"],
                "ptok": res["ptok"], "ctok": res["ctok"]}, ensure_ascii=False) + "\n")
    with (args.outdir / "recomb_records.jsonl").open("w") as f:
        for (pid, gi, s), res in recomb.items():
            f.write(json.dumps({
                "pid": pid, "ds": problems[pid]["ds"], "tier": problems[pid]["tier"],
                "group": gi, "sample": s, "arm": "M5_combined", "pred": res["pred"],
                "correct": res["correct"], "finish": res["finish"], "text": res["text"],
                "ptok": res["ptok"], "ctok": res["ctok"]}, ensure_ascii=False) + "\n")
    summary = {"arm": "M5_combined", "gate_margin": GATE_MARGIN, "gate_second": GATE_SECOND,
               "gated_problems": gated_pids, "n_trials": len(trial_keys),
               "correct_traces": sum(r["correct"] for r in recomb.values()),
               "params": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}}
    summary["density"] = round(summary["correct_traces"] / len(trial_keys), 4)
    (args.outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("density", "correct_traces", "n_trials", "gated_problems")},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
