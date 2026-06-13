#!/usr/bin/env python3
"""Stay-close (Harman constraint) ablation for the offline Feedback-SE probe.

Reuses the EXISTING feedback records (no feedback regeneration) and the SAME 10 problems,
50 groups, stripped candidate views, and recombination seeds as outputs/node1_feedback_probe/.
Only the recombination prompt changes: append Harman's "stay close to the candidate attempts"
constraint. 3 arms only: no_feedback_stayclose, gold_free_stripped_stayclose,
gold_aware_stripped_stayclose. Recombination candidates always stripped. Gold-aware = oracle/leaky.

Does NOT touch the orchestrator, baseline outputs, or rerun feedback. Writes to
outputs/node1_feedback_probe_stayclose/.
"""
from __future__ import annotations
import argparse, json, sys, threading, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "external/squeeze-evolve/src"))
from tts_sft.answer_extraction import extract_final_answer, is_exact_match  # noqa: E402
from squeeze_evolve.common import strip_think_blocks  # noqa: E402

HARMAN = ("Correctness is the primary goal. However, to the extent possible, keep the final "
          "solution close to the candidate attempts. Prefer repairing, combining, and clarifying "
          "the candidates' reasoning over introducing a completely different solution path. Only "
          "deviate substantially from the candidates if their approaches are clearly flawed.")
TAIL_NOFB = "Please synthesize a single improved solution. " + HARMAN + " End with the final answer in \\boxed{}."
TAIL_FB = ("Please synthesize a single improved solution. Use the feedback to avoid mistakes and "
           "preserve correct reasoning. " + HARMAN + " End with the final answer in \\boxed{}.")
ARMS = ["no_feedback_stayclose", "gold_free_stripped_stayclose", "gold_aware_stripped_stayclose"]
FB_SRC = {"gold_free_stripped_stayclose": "gold_free_stripped",
          "gold_aware_stripped_stayclose": "gold_aware_stripped"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe-dir", type=Path, default=Path("outputs/node1_feedback_probe"))
    ap.add_argument("--outdir", type=Path, default=Path("outputs/node1_feedback_probe_stayclose"))
    ap.add_argument("--n-groups", type=int, default=5)
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Thinking-2507")
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--max-tokens-recomb", type=int, default=16384)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--concurrency", type=int, default=24)
    args = ap.parse_args()

    # --- reuse existing feedback (stripped arms only) ---
    fb = {}  # (pid, cand_idx, src_arm) -> feedback text
    pids = set()
    for line in (args.probe_dir / "feedback_records.jsonl").open():
        r = json.loads(line)
        if r["arm"] in ("gold_free_stripped", "gold_aware_stripped"):
            fb[(r["pid"], r["cand_idx"], r["arm"])] = r["feedback"]
        pids.add(r["pid"])
    pids = sorted(pids)
    ds_of = {p: ("aime" if p.startswith("aime") else "hmmt") for p in pids}

    # --- reconstruct the SAME problems/groups/stripped candidates from loop_candidates ---
    problems = {}
    for ds in ("aime", "hmmt"):
        f = _REPO / f"outputs/node1_se_loop5_32k_temp1_{ds}_non_saturated/se.jsonl.loop_candidates.jsonl"
        l0 = defaultdict(dict); groups = defaultdict(list); meta = {}
        for line in f.open():
            r = json.loads(line)
            pid = r["id"]
            if pid not in pids:
                continue
            if r["loop_index"] == 0:
                c = int(r["candidate_id"].rsplit("cand", 1)[-1])
                l0[pid][c] = r["full_response"] or ""
                meta[pid] = {"problem": r["question"], "gold": str(r["answer"])}
            elif r["loop_index"] == 1 and r.get("parent_ids") is not None:
                groups[pid].append(list(r["parent_ids"]))
        for pid in l0:
            problems[pid] = {"ds": ds, "problem": meta[pid]["problem"], "gold": meta[pid]["gold"],
                             "stripped": {c: strip_think_blocks(t) for c, t in l0[pid].items()},
                             "groups": groups[pid][: args.n_groups]}
    # integrity checks: same pids, same candidate set as feedback file
    assert set(problems) == set(pids), (set(problems) ^ set(pids))
    for pid, d in problems.items():
        used = {i for g in d["groups"] for i in g}
        have = {idx for (p, idx, a) in fb if p == pid and a == "gold_free_stripped"}
        assert used <= have, f"{pid}: group candidates {used-have} missing feedback"
    print(f"reconstructed {len(problems)} problems, {sum(len(d['groups']) for d in problems.values())} groups; "
          f"feedback reused for {len({(p,i) for (p,i,a) in fb})} candidates", flush=True)

    # --- recombination (3 stay-close arms), same seeds (seed+gi) ---
    from openai import OpenAI
    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=7200)
    sem = threading.Semaphore(args.concurrency)

    def call(prompt, seed):
        for attempt in range(4):
            try:
                with sem:
                    r = client.chat.completions.create(
                        model=args.model, messages=[{"role": "user", "content": prompt}],
                        temperature=args.temperature, top_p=args.top_p,
                        max_tokens=args.max_tokens_recomb, seed=seed, extra_body={"top_k": args.top_k})
                ch = r.choices[0]; u = r.usage
                return {"text": ch.message.content or "", "finish": ch.finish_reason,
                        "ptok": getattr(u, "prompt_tokens", 0), "ctok": getattr(u, "completion_tokens", 0)}
            except Exception as e:  # noqa: BLE001
                time.sleep(min(20, 2 ** attempt)); last = e
        return {"text": "", "finish": "error", "ptok": 0, "ctok": 0, "err": str(last)}

    jobs = [(pid, gi, arm) for pid, d in problems.items() for gi in range(len(d["groups"])) for arm in ARMS]
    print(f"recombination calls: {len(jobs)}", flush=True)

    def do(job):
        pid, gi, arm = job
        d = problems[pid]; grp = d["groups"][gi]
        parts = [f"Problem:\n{d['problem']}\n"]
        for j, idx in enumerate(grp, 1):
            parts.append(f"Candidate solution {j}:\n{d['stripped'][idx]}\n")
            if arm != "no_feedback_stayclose":
                parts.append(f"Feedback on candidate solution {j}:\n{fb[(pid, idx, FB_SRC[arm])]}\n")
        parts.append(TAIL_NOFB if arm == "no_feedback_stayclose" else TAIL_FB)
        res = call("\n".join(parts), args.seed + gi)
        res["correct"] = bool(is_exact_match(extract_final_answer(res["text"]), d["gold"]))
        return pid, gi, arm, res

    recomb = defaultdict(lambda: defaultdict(dict))
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        done = 0
        for pid, gi, arm, res in ex.map(do, jobs):
            recomb[pid][arm][gi] = res
            done += 1
            if done % 30 == 0:
                print(f"  recomb {done}/{len(jobs)}", flush=True)

    # --- write + aggregate ---
    args.outdir.mkdir(parents=True, exist_ok=True)
    with (args.outdir / "recomb_records.jsonl").open("w") as f:
        for pid, arms in recomb.items():
            for arm, gis in arms.items():
                for gi, res in gis.items():
                    f.write(json.dumps({"pid": pid, "ds": problems[pid]["ds"], "group": gi, "arm": arm,
                                        "pred": extract_final_answer(res["text"]), "correct": res["correct"],
                                        "ptok": res["ptok"], "ctok": res["ctok"], "finish": res["finish"]},
                                       ensure_ascii=False) + "\n")
    summary = {"n_problems": len(problems), "n_groups": args.n_groups, "arms": {}}
    for arm in ARMS:
        solved = sum(1 for pid in problems if any(recomb[pid][arm][gi]["correct"] for gi in recomb[pid][arm]))
        tr = sum(recomb[pid][arm][gi]["correct"] for pid in problems for gi in recomb[pid][arm])
        tot = sum(len(recomb[pid][arm]) for pid in problems)
        pt = sum(recomb[pid][arm][gi]["ptok"] for pid in problems for gi in recomb[pid][arm])
        ct = sum(recomb[pid][arm][gi]["ctok"] for pid in problems for gi in recomb[pid][arm])
        summary["arms"][arm] = {"solved": solved, "correct_traces": tr, "total_groups": tot,
                                "density": round(tr / max(1, tot), 4), "recomb_ptok": pt, "recomb_ctok": ct}
    (args.outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
