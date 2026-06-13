#!/usr/bin/env python3
"""Grade LCBV6 calibration generations, bucket problems, write filtered benchmarks.

Input: raw generation JSONL (one record/problem) from gen_lcbv6_calibration.py:
  {"id","question_id","dataset","samples":[{"sample_id","text","finish_reason",
   "prompt_tokens","completion_tokens"},...], "generation_params":{...}}
Seed (for tests + filtered-file content): data/seeds/lcbv6_seed.jsonl

Grading is OFFLINE and uses the HIDDEN (private) test suite. Each sample's last
```python``` block is extracted and run via scripts/lcb_exec_harness.py in its own
subprocess (overall timeout per sample). No test feedback ever touches generation.

Outputs:
  --gen-log     flat per-generation log (one row per (problem,sample))
  --per-problem per-problem aggregates + bucket
  data/filtered/lcbv6_full.jsonl          (all 131)
  data/filtered/lcbv6_non_saturated.jsonl (drop saturated_easy)
  data/filtered/lcbv6_informative.jsonl   (correct in [1,15])
  data/filtered/lcbv6_hard_zero_clean.jsonl (correct==0 & clean)
  --report      markdown report ; --summary-json  machine summary
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HARNESS = Path(__file__).resolve().parent / "lcb_exec_harness.py"
_CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n?(.*?)```", re.DOTALL)


def extract_code(response: str):
    blocks = _CODE_BLOCK.findall(response or "")
    return blocks[-1].strip() if blocks else None


def grade_sample(code: str, tests_path: str, n_tests: int, time_limit: float):
    """Run one candidate via the harness subprocess. Returns (passed, error)."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as cf:
        cf.write(code)
        code_path = cf.name
    overall = min(n_tests * time_limit + 20.0, 300.0)
    try:
        proc = subprocess.run(
            [sys.executable, str(HARNESS), code_path, tests_path],
            capture_output=True, text=True, timeout=overall,
        )
    except subprocess.TimeoutExpired:
        return False, "harness_timeout"
    finally:
        Path(code_path).unlink(missing_ok=True)
    out = proc.stdout.strip().splitlines()
    if not out:
        return False, f"harness_no_output: {proc.stderr.strip()[:120]}"
    try:
        v = json.loads(out[-1])
    except json.JSONDecodeError:
        return False, f"harness_bad_output: {out[-1][:120]}"
    return bool(v["passed"]), v.get("error", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", required=True, type=Path, help="raw generation JSONL")
    ap.add_argument("--seed", type=Path, default=Path("data/seeds/lcbv6_seed.jsonl"))
    ap.add_argument("--gen-log", type=Path,
                    default=Path("outputs/node1_calibration_lcbv6_N16_32k_temp1.jsonl"))
    ap.add_argument("--per-problem", type=Path,
                    default=Path("outputs/node1_calibration_lcbv6_per_problem.jsonl"))
    ap.add_argument("--filtered-dir", type=Path, default=Path("data/filtered"))
    ap.add_argument("--report", type=Path, default=Path("docs/NODE1_LCBV6_CALIBRATION.md"))
    ap.add_argument("--summary-json", type=Path,
                    default=Path("outputs/node1_calibration_lcbv6_summary.json"))
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--code-rate-high", type=float, default=0.5)
    ap.add_argument("--cap-rate-low", type=float, default=0.5)
    args = ap.parse_args()

    seed = {r["id"]: r for r in (json.loads(l) for l in args.seed.open())}
    gen = [json.loads(l) for l in args.gen.open()]
    gp = gen[0].get("generation_params", {}) if gen else {}
    temperature = gp.get("temperature"); top_p = gp.get("top_p")
    top_k = gp.get("top_k"); max_tokens = gp.get("max_tokens")

    # Pre-write each problem's tests to a temp file (shared across its samples).
    tests_files: dict[str, str] = {}
    tmpdir = Path(tempfile.mkdtemp(prefix="lcbv6_tests_"))
    for pid, rec in seed.items():
        p = tmpdir / f"{pid}.json"
        p.write_text(rec["tests"])
        tests_files[pid] = str(p)

    # Build the work list: (pid, sample) -> grade.
    flat_rows = []
    jobs = []  # (row_index, code, tests_path, n_tests, time_limit)
    for rec in gen:
        pid = rec["id"]
        s = seed.get(pid)
        if s is None:
            continue
        tests = json.loads(s["tests"])
        n_tests = len(tests["inputs"])
        tl = float(tests.get("time_limit", 6))
        for smp in rec["samples"]:
            text = smp.get("text") or ""
            code = extract_code(text)
            finish = smp.get("finish_reason")
            row = {
                "dataset": "LCBV6",
                "problem_id": pid,
                "question_id": rec.get("question_id"),
                "sample_id": smp["sample_id"],
                "input_tokens": smp.get("prompt_tokens"),
                "output_tokens": smp.get("completion_tokens"),
                "total_tokens": (smp.get("prompt_tokens") or 0) + (smp.get("completion_tokens") or 0),
                "finish_reason": finish,
                "cap_hit": finish == "length",
                "code_extracted": code is not None,
                "extracted_code_chars": len(code) if code else 0,
                "raw_text_chars": len(text),
                "pass_tests": False,
                "error_type": "",
                "testtype": tests["testtype"],
                "temperature": temperature, "top_p": top_p,
                "top_k": top_k, "max_tokens": max_tokens,
            }
            idx = len(flat_rows)
            flat_rows.append(row)
            if code is None:
                row["error_type"] = "no_code"
            else:
                jobs.append((idx, code, tests_files[pid], n_tests, tl))

    print(f"grading {len(jobs)} code candidates ({len(flat_rows)} total samples) "
          f"with {args.workers} workers ...", flush=True)

    def _run(job):
        idx, code, tp, nt, tl = job
        passed, err = grade_sample(code, tp, nt, tl)
        return idx, passed, err

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for idx, passed, err in ex.map(_run, jobs):
            flat_rows[idx]["pass_tests"] = passed
            if not passed:
                flat_rows[idx]["error_type"] = err
            done += 1
            if done % 200 == 0:
                print(f"  graded {done}/{len(jobs)}", flush=True)

    # Per-problem aggregation.
    by_pid: dict[str, list] = {}
    for row in flat_rows:
        by_pid.setdefault(row["problem_id"], []).append(row)

    per_problem = []
    buckets = {"saturated_easy": [], "informative": [], "hard_zero": [],
               "bad_truncated_or_bad_format": []}
    tot_in = tot_out = 0
    for pid in sorted(by_pid):
        rows = by_pid[pid]
        n = len(rows)
        correct = sum(r["pass_tests"] for r in rows)
        code_ok = sum(r["code_extracted"] for r in rows)
        cap = sum(r["cap_hit"] for r in rows)
        outs = [r["output_tokens"] or 0 for r in rows]
        ins = [r["input_tokens"] or 0 for r in rows]
        p_in, p_out = sum(ins), sum(outs)
        tot_in += p_in; tot_out += p_out
        code_rate = code_ok / n
        cap_rate = cap / n
        rec = {
            "problem_id": pid,
            "question_id": seed[pid]["question_id"],
            "difficulty": seed[pid]["difficulty"],
            "testtype": seed[pid]["testtype"],
            "n_samples": n,
            "correct_count": correct,
            "code_extraction_count": code_ok,
            "code_extraction_rate": round(code_rate, 4),
            "cap_hit_count": cap,
            "cap_hit_rate": round(cap_rate, 4),
            "avg_output_tokens": round(p_out / n, 1),
            "max_output_tokens": max(outs) if outs else 0,
            "total_input_tokens": p_in,
            "total_output_tokens": p_out,
            "total_tokens": p_in + p_out,
        }
        if correct == n:
            b = "saturated_easy"
        elif correct >= 1:
            b = "informative"
        elif code_rate >= args.code_rate_high and cap_rate <= args.cap_rate_low:
            b = "hard_zero"
        else:
            b = "bad_truncated_or_bad_format"
        rec["bucket"] = b
        buckets[b].append(pid)
        per_problem.append(rec)

    # Write flat per-generation log + per-problem.
    args.gen_log.parent.mkdir(parents=True, exist_ok=True)
    with args.gen_log.open("w") as f:
        for row in flat_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with args.per_problem.open("w") as f:
        for rec in per_problem:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Filtered benchmark files (carry full seed records so they are runnable).
    args.filtered_dir.mkdir(parents=True, exist_ok=True)

    def write_subset(name, pids):
        pset = set(pids)
        with (args.filtered_dir / name).open("w") as f:
            for pid in sorted(pset):
                f.write(json.dumps(seed[pid], ensure_ascii=False) + "\n")

    all_ids = [r["problem_id"] for r in per_problem]
    non_saturated = [p for p in all_ids if p not in set(buckets["saturated_easy"])]
    informative = buckets["informative"]
    hard_zero_clean = buckets["hard_zero"]
    write_subset("lcbv6_full.jsonl", all_ids)
    write_subset("lcbv6_non_saturated.jsonl", non_saturated)
    write_subset("lcbv6_informative.jsonl", informative)
    write_subset("lcbv6_hard_zero_clean.jsonl", hard_zero_clean)

    # Summaries.
    n_total = len(per_problem)
    code_rows = sum(r["code_extracted"] for r in flat_rows)
    cap_rows = sum(r["cap_hit"] for r in flat_rows)
    summary = {
        "dataset": "LCBV6",
        "n_problems": n_total,
        "n_samples_per_problem": gp.get("n_samples"),
        "generation_params": gp,
        "buckets": {k: len(v) for k, v in buckets.items()},
        "ids": {
            "saturated_easy": sorted(buckets["saturated_easy"]),
            "informative": sorted(informative),
            "hard_zero_clean": sorted(hard_zero_clean),
            "bad_truncated_or_bad_format": sorted(buckets["bad_truncated_or_bad_format"]),
        },
        "code_extraction": {
            "rows_with_code": code_rows, "rows_total": len(flat_rows),
            "rate": round(code_rows / max(1, len(flat_rows)), 4),
        },
        "cap_hit": {
            "rows_cap_hit": cap_rows, "rows_total": len(flat_rows),
            "rate": round(cap_rows / max(1, len(flat_rows)), 4),
        },
        "tokens": {
            "total_input_tokens": tot_in, "total_output_tokens": tot_out,
            "total_tokens": tot_in + tot_out,
        },
        "filtered_files": {
            "lcbv6_full.jsonl": len(all_ids),
            "lcbv6_non_saturated.jsonl": len(non_saturated),
            "lcbv6_informative.jsonl": len(informative),
            "lcbv6_hard_zero_clean.jsonl": len(hard_zero_clean),
        },
        "recommended_default_subset": "lcbv6_non_saturated",
        "thresholds": {"code_rate_high": args.code_rate_high, "cap_rate_low": args.cap_rate_low},
    }
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(json.dumps(summary, indent=2))

    # Markdown report.
    lines = [
        "# Node 1 — LCBV6 BoN Calibration", "",
        f"Independent BoN, N={gp.get('n_samples')}, temperature={temperature}, top_p={top_p}, "
        f"top_k={top_k}, max_tokens={max_tokens}. Model: {gp.get('model')}.",
        "Hidden (private) test suite; tests used for OFFLINE evaluation only "
        "(no test feedback during generation).", "",
        f"- **Total LCBV6 problems:** {n_total}",
        f"- **saturated_easy** (16/16): {len(buckets['saturated_easy'])}",
        f"- **informative** (1–15/16): {len(informative)}",
        f"- **hard_zero** (0/16, clean): {len(buckets['hard_zero'])}",
        f"- **bad_truncated_or_bad_format** (0/16, capped/no-code): "
        f"{len(buckets['bad_truncated_or_bad_format'])}", "",
        f"- **Code-extraction:** {code_rows}/{len(flat_rows)} rows "
        f"({summary['code_extraction']['rate']:.1%})",
        f"- **Cap-hit (finish_reason=length):** {cap_rows}/{len(flat_rows)} rows "
        f"({summary['cap_hit']['rate']:.1%})",
        f"- **Tokens:** input {tot_in:,} + output {tot_out:,} = {tot_in + tot_out:,}", "",
        f"- **Recommended default subset for SE/BoN comparison:** `lcbv6_non_saturated` "
        f"({len(non_saturated)} problems)", "",
        "## IDs removed as saturated_easy",
        "  " + (", ".join(sorted(buckets["saturated_easy"])) or "(none)"), "",
        "## informative IDs",
        "  " + (", ".join(sorted(informative)) or "(none)"), "",
        "## hard_zero_clean IDs",
        "  " + (", ".join(sorted(hard_zero_clean)) or "(none)"), "",
        "## bad_truncated_or_bad_format IDs",
        "  " + (", ".join(sorted(buckets["bad_truncated_or_bad_format"])) or "(none)"), "",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines))

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
