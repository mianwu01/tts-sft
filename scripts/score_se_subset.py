#!/usr/bin/env python3
"""Score a verifier-free SqueezeEvolve run (math or code) over its per-loop candidates.

Reads:
  --loop-candidates  <out>.loop_candidates.jsonl   (from se_loop_candidates.py)
  --seed             the subset file (gt for math / hidden tests for code)
  --metrics-json     external/squeeze-evolve/.../metrics.json   (authoritative per-loop tokens)
  --task             math | code

Per-candidate metadata SE checkpoints do NOT store token counts / finish_reason, so those are
DERIVED offline: output_tokens = tokenized len(full_response); input_tokens = tokenized len of the
reconstructed prompt (loop0 = chat-templated question; loop>=1 = chat-templated aggregate(question,
parent_texts) using the SAME operator SE used); cap_hit / finish_reason inferred from output_tokens
vs max_tokens. The authoritative per-loop input/output token TOTALS come from metrics.json.

Grading (OFFLINE only; never used inside SE):
  math: is_exact_match(extract_final_answer(full_response), gt)   (LaTeX-aware, repo grader)
  code: extract last ```python``` block -> run vs hidden tests via lcb_exec_harness.py

Writes: --out-genlog (flat per-generation), --out-perproblem, --out-summary (json).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "external/squeeze-evolve/src"))
sys.path.insert(0, str(_REPO / "scripts"))

from tts_sft.answer_extraction import extract_final_answer, is_exact_match  # noqa: E402
from squeeze_evolve.common import make_aggregate_prompt  # noqa: E402
from eval_lcbv6_calibration import extract_code, HARNESS  # noqa: E402

_AGG = {
    "math": make_aggregate_prompt("math problem", "\\boxed{}"),
    "code": make_aggregate_prompt(
        "competitive programming problem",
        "a single Python code block enclosed with ```",
        is_code=True,
    ),
}


def grade_code(code, tests_path, n_tests, tl):
    if code is None:
        return False, "no_code"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as cf:
        cf.write(code); code_path = cf.name
    try:
        proc = subprocess.run([sys.executable, str(HARNESS), code_path, tests_path],
                              capture_output=True, text=True,
                              timeout=min(n_tests * tl + 20, 300))
    except subprocess.TimeoutExpired:
        Path(code_path).unlink(missing_ok=True); return False, "harness_timeout"
    Path(code_path).unlink(missing_ok=True)
    out = proc.stdout.strip().splitlines()
    if not out:
        return False, "harness_no_output"
    try:
        v = json.loads(out[-1])
    except json.JSONDecodeError:
        return False, "harness_bad_output"
    return bool(v["passed"]), v.get("error", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop-candidates", required=True, type=Path)
    ap.add_argument("--seed", required=True, type=Path)
    ap.add_argument("--metrics-json", type=Path, default=None)
    ap.add_argument("--task", required=True, choices=["math", "code"])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--model-path", default=(
        "/mnt/cpfs/yangboxue/opsd/TTS/hf_cache/hub/models--Qwen--Qwen3-4B-Thinking-2507"
        "/snapshots/768f209d9ea81521153ed38c47d515654e938aea"))
    ap.add_argument("--max-tokens", type=int, default=32768)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--out-genlog", required=True, type=Path)
    ap.add_argument("--out-perproblem", required=True, type=Path)
    ap.add_argument("--out-summary", required=True, type=Path)
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--accumulate", action="store_true",
                    help="update=accumulate run: keep only the NEW candidates per loop "
                         "(the last `--groups` of each checkpoint) so the 80 unique generations "
                         "are graded once, not the accumulated duplicates.")
    ap.add_argument("--groups", type=int, default=16,
                    help="new candidates generated per loop (= routing.groups); for --accumulate.")
    args = ap.parse_args()

    seed = {r["id"]: r for r in (json.loads(l) for l in args.seed.open())}
    cands = [json.loads(l) for l in args.loop_candidates.open()]
    if args.accumulate:
        # accumulate appends `groups` new candidates at the END of each checkpoint
        # (update_accumulate = old + new). The new-at-loop-t are within-checkpoint
        # indices [groups*t, groups*t+groups). Parse the index from candidate_id
        # ("...::cand{c}") and keep only those -> 80 unique generations, origin loop = loop_index.
        def _cand_idx(cid):
            try:
                return int(str(cid).rsplit("cand", 1)[-1])
            except ValueError:
                return -1
        kept = [c for c in cands if _cand_idx(c["candidate_id"]) >= args.groups * c["loop_index"]]
        print(f"[accumulate] kept {len(kept)} new-per-loop candidates of {len(cands)} flattened "
              f"(deduped accumulated population)", flush=True)
        cands = kept
    loops = sorted({c["loop_index"] for c in cands})
    final_loop = max(loops)

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    agg = _AGG[args.task]

    # tests temp files per problem (code only)
    tmpdir = Path(tempfile.mkdtemp(prefix="se_score_"))
    tests_files, n_tests_map = {}, {}
    if args.task == "code":
        for pid, r in seed.items():
            (tmpdir / f"{pid}.json").write_text(r["tests"])
            tests_files[pid] = str(tmpdir / f"{pid}.json")
            n_tests_map[pid] = len(json.loads(r["tests"])["inputs"])

    def reconstruct_prompt(c):
        s = seed.get(c["id"])
        q = s["question"] if s else ""
        if c["loop_index"] == 0 or not c.get("parent_texts"):
            text = q
        else:
            text = agg(q, c["parent_texts"])
        return tok.apply_chat_template([{"role": "user", "content": text}],
                                       tokenize=False, add_generation_prompt=True)

    # Build rows + token derivation (batch tokenization).
    print(f"[{args.dataset}] {len(cands)} candidates; tokenizing ...", flush=True)
    prompts = [reconstruct_prompt(c) for c in cands]
    responses = [c.get("full_response") or "" for c in cands]
    in_tok = [len(x) for x in tok(prompts, add_special_tokens=False)["input_ids"]]
    out_tok = [len(x) for x in tok(responses, add_special_tokens=False)["input_ids"]]

    rows = []
    code_jobs = []
    for i, c in enumerate(cands):
        pid = c["id"]
        cap = out_tok[i] >= args.max_tokens - 8
        if args.task == "math":
            extracted = extract_final_answer(responses[i])
        else:
            extracted = extract_code(responses[i])
        row = {
            "dataset": args.dataset, "problem_id": pid,
            "loop_index": c["loop_index"], "candidate_id": c["candidate_id"],
            "parent_ids": c.get("parent_ids"),
            "input_tokens": in_tok[i], "output_tokens": out_tok[i],
            "total_tokens": in_tok[i] + out_tok[i],
            "finish_reason": "length" if cap else "stop", "cap_hit": cap,
            "extracted": (extracted if args.task == "math"
                          else (f"<code:{len(extracted)}chars>" if extracted else None)),
            "code_extracted": (extracted is not None) if args.task == "code" else None,
            "correct": False, "error_type": "",
            "temperature": args.temperature, "top_p": args.top_p, "top_k": args.top_k,
            "max_tokens": args.max_tokens, "raw_text_chars": len(responses[i]),
        }
        idx = len(rows); rows.append(row)
        if args.task == "math":
            gt = seed.get(pid, {}).get("answer")
            row["correct"] = bool(gt is not None and extracted is not None
                                  and is_exact_match(extracted, str(gt)))
        else:
            code_jobs.append((idx, extract_code(responses[i]), pid))

    if args.task == "code":
        print(f"[{args.dataset}] grading {len(code_jobs)} code candidates ...", flush=True)
        def _run(job):
            idx, code, pid = job
            ok, err = grade_code(code, tests_files[pid], n_tests_map[pid], 6.0)
            return idx, ok, err
        done = 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for idx, ok, err in ex.map(_run, code_jobs):
                rows[idx]["correct"] = ok
                if not ok:
                    rows[idx]["error_type"] = err
                done += 1
                if done % 500 == 0:
                    print(f"  graded {done}/{len(code_jobs)}", flush=True)

    # ---- aggregates ----
    by_pid = {}
    for r in rows:
        by_pid.setdefault(r["problem_id"], []).append(r)

    per_problem = []
    se_all_solved = se_final_solved = 0
    total_correct = 0
    for pid in sorted(by_pid):
        rs = by_pid[pid]
        correct = sum(r["correct"] for r in rs)
        total_correct += correct
        any_all = correct >= 1
        any_final = any(r["correct"] for r in rs if r["loop_index"] == final_loop)
        se_all_solved += any_all
        se_final_solved += any_final
        per_problem.append({
            "problem_id": pid, "n_candidates": len(rs), "correct_count": correct,
            "se_all_solved": any_all, "se_final_solved": any_final,
            "per_loop_correct": {str(L): sum(r["correct"] for r in rs if r["loop_index"] == L)
                                 for L in loops},
        })

    # per-loop stats (derived token sums + cap/extract rates)
    per_loop = {}
    for L in loops:
        lr = [r for r in rows if r["loop_index"] == L]
        n = len(lr)
        ext = sum((r["code_extracted"] if args.task == "code" else bool(r["extracted"])) for r in lr)
        per_loop[str(L)] = {
            "n_candidates": n,
            "solved_problems": sum(1 for pid in by_pid
                                   if any(r["correct"] for r in by_pid[pid] if r["loop_index"] == L)),
            "correct_candidates": sum(r["correct"] for r in lr),
            "cap_hit": sum(r["cap_hit"] for r in lr),
            "cap_hit_rate": round(sum(r["cap_hit"] for r in lr) / max(1, n), 4),
            "extraction_rate": round(ext / max(1, n), 4),
            "derived_input_tokens": sum(r["input_tokens"] for r in lr),
            "derived_output_tokens": sum(r["output_tokens"] for r in lr),
        }

    # authoritative per-loop tokens from metrics.json (a JSON list of per-loop dicts)
    metrics_by_loop = {}
    if args.metrics_json and args.metrics_json.exists():
        try:
            payload = json.load(args.metrics_json.open())
        except json.JSONDecodeError:
            payload = []
        entries = payload if isinstance(payload, list) else [payload]
        for m in entries:
            if not isinstance(m, dict) or m.get("loop") is None:
                continue
            metrics_by_loop[str(m["loop"])] = {
                "input_tokens": m.get("total_input_tokens"),
                "output_tokens": m.get("total_output_tokens"),
            }

    summary = {
        "dataset": args.dataset, "task": args.task,
        "n_problems": len(by_pid), "loops": loops, "final_loop": final_loop,
        "n_candidates_per_problem_nominal": 16 * len(loops),
        "se_all_solved": se_all_solved, "se_final_solved": se_final_solved,
        "total_correct_traces": total_correct,
        "per_loop": per_loop,
        "metrics_json_per_loop_tokens": metrics_by_loop,
        "verifier_free": True,
        "generation_params": {"temperature": args.temperature, "top_p": args.top_p,
                              "top_k": args.top_k, "max_tokens": args.max_tokens},
        "note": "token counts/finish_reason per candidate are DERIVED offline; "
                "authoritative per-loop totals in metrics_json_per_loop_tokens",
    }

    args.out_genlog.parent.mkdir(parents=True, exist_ok=True)
    with args.out_genlog.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with args.out_perproblem.open("w") as f:
        for r in per_problem:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    args.out_summary.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
