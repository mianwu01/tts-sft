#!/usr/bin/env python3
"""Post-hoc artifact builder + validator for the node3 pyramid Feedback-SE runs.

From the preserved per-loop checkpoints it deterministically reconstructs, for every loop t >= 1:
  - parent_groups.jsonl    one row per (loop, problem, group): parent indices into the loop t-1
                           population + integrity check that the stored parent texts equal the
                           loop t-1 candidates at those indices (strip_think=false => verbatim).
  - feedback_records.jsonl one row per (loop, problem, group, parent): public-test category and the
                           exact feedback block (or None for all_pass), rebuilt with the OPERATOR'S
                           OWN functions (_feedback_aggregate.py imported by path), so the
                           reconstruction is byte-identical to what the model saw.
  - prompt_samples/        a few fully reconstructed recombination prompts (visible-failed block
                           present + all_pass omitted cases).
  - validation_summary.json the smoke checklist: no fresh loop-0, operator fired from loop 1,
                           all_pass omitted, visible-failed inserted, checkpoints/metadata present,
                           cross-check vs the live feedback_operator_audit.jsonl.

Public/sample tests only (env LCB_FB_SEED/LCB_FB_PUBLIC/LCB_FB_HARNESS); hidden tests are not read.
LCB_FB_LOG is force-unset so reconstruction NEVER appends to the run's audit file.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _sha1(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8", "ignore")).hexdigest()[:12]


def _load_operator_module(se_dir: Path):
    os.environ.pop("LCB_FB_LOG", None)  # never append to the run audit during reconstruction
    p = se_dir / "benchmarks" / "livecodebench" / "_feedback_aggregate.py"
    spec = importlib.util.spec_from_file_location("lcb_feedback_aggregate_posthoc", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outdir", required=True, type=Path, help="Run dir (outputs/node3_..._{smoke,pilot}).")
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--squeeze-evolve-dir", type=Path, default=REPO / "external" / "squeeze-evolve")
    ap.add_argument("--n-prompt-samples", type=int, default=4)
    args = ap.parse_args()

    outdir = args.outdir
    ck_dir = outdir / "se.jsonl.checkpoints"
    report = json.loads((outdir / "pyramid_run_report.json").read_text())
    manifest = json.loads((outdir / "run_manifest.json").read_text())
    schedule: list[int] = report["schedule"]
    seeds = [json.loads(l) for l in open(manifest["subset_seed"])]
    mod = _load_operator_module(args.squeeze_evolve_dir)

    # ---- load checkpoints loop0..S ----
    cks = {}
    for t in range(0, len(schedule) + 1):
        p = ck_dir / f"{args.run_name}_loop{t}.json"
        if not p.exists():
            raise SystemExit(f"missing checkpoint {p}")
        cks[t] = json.loads(p.read_text())

    # ---- parent_groups + feedback_records + prompts ----
    pg_rows, fb_rows, mismatches = [], [], []
    prompts: list[dict] = []
    for t in range(1, len(schedule) + 1):
        prev = cks[t - 1]["problems"]
        cur = cks[t]["problems"]
        for q, (pp, cp) in enumerate(zip(prev, cur)):
            pid = seeds[q]["id"]
            members = (cp.get("routing_details") or {}).get("group_index_members") or []
            groups = cp.get("candidate_groups") or []
            query = cp.get("orig_prompt")
            tests = mod._tests_for(query)
            for g, (idxs, ptexts) in enumerate(zip(members, groups)):
                texts_match = all(
                    0 <= i < len(pp["candidates"]) and pp["candidates"][i] == ptexts[j]
                    for j, i in enumerate(idxs)
                ) and len(idxs) == len(ptexts)
                pg_rows.append({"loop": t, "id": pid, "group": g, "parent_indices_in_prev_loop": idxs,
                                "n_parents": len(ptexts), "parent_sha1s": [_sha1(x) for x in ptexts],
                                "parent_texts_match_prev_candidates": texts_match})
                if not texts_match:
                    mismatches.append({"kind": "parent_text_mismatch", "loop": t, "id": pid, "group": g})
                cats, blocks, parts = [], [], []
                for j, ptxt in enumerate(ptexts, 1):
                    if tests is None:
                        cat, fb = "no_tests", None
                    else:
                        code = mod._extract_code(ptxt)
                        if not code:
                            cat, fb = "no_code", mod._v2_block({"category": "compile_error",
                                       "first_fail": {"error": "No extractable Python code block."}})
                        else:
                            pub = mod._public_result(code, tests)
                            cat, fb = pub.get("category"), mod._v2_block(pub)
                    cats.append(cat)
                    blocks.append(fb)
                    parts.append(f"\n---- Solution {j} ----\n{(ptxt or '').strip()}\n")
                    if fb is not None:
                        parts.append(f"---- Visible feedback on Solution {j} ----\n{fb}\n")
                    fb_rows.append({"loop": t, "id": pid, "group": g, "parent_pos": j - 1,
                                    "parent_idx_in_prev_loop": idxs[j - 1] if j - 1 < len(idxs) else None,
                                    "category": cat, "has_block": fb is not None,
                                    "block_sha1": _sha1(fb) if fb else None, "block": fb})
                prompt = mod._STAYCLOSE_TOP.format(problem=query, blocks="".join(parts))
                child = cp["candidates"][g] if g < len(cp.get("candidates") or []) else None
                prompts.append({"loop": t, "id": pid, "group": g, "categories": cats,
                                "n_blocks": sum(b is not None for b in blocks),
                                "prompt": prompt, "child_sha1": _sha1(child or "")})

    with open(outdir / "parent_groups.jsonl", "w") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in pg_rows)
    with open(outdir / "feedback_records.jsonl", "w") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in fb_rows)

    # prompt samples: cover (a) >=1 visible-failed block, (b) all-all_pass (no blocks), per loop where possible
    sample_dir = outdir / "prompt_samples"
    sample_dir.mkdir(exist_ok=True)
    picked = []
    for t in range(1, len(schedule) + 1):
        loop_ps = [p for p in prompts if p["loop"] == t]
        with_fb = next((p for p in loop_ps if p["n_blocks"] > 0), None)
        no_fb = next((p for p in loop_ps if p["n_blocks"] == 0), None)
        for p in (with_fb, no_fb):
            if p and len(picked) < args.n_prompt_samples:
                picked.append(p)
    for i, p in enumerate(picked):
        name = f"sample{i}_loop{p['loop']}_{p['id']}_g{p['group']}_{p['n_blocks']}blocks.txt"
        (sample_dir / name).write_text(p["prompt"])

    # ---- cross-check against the live audit (sliced per stage via line spans) ----
    audit_path = outdir / "feedback_operator_audit.jsonl"
    audit_checks = {"present": audit_path.exists(), "per_stage": [], "category_mismatches": 0,
                    "block_count_mismatches": 0, "fallbacks": 0, "lookup_misses": 0}
    if audit_path.exists():
        audit = [json.loads(l) for l in open(audit_path)]
        audit_checks["fallbacks"] = sum(1 for r in audit if r.get("fallback"))
        audit_checks["lookup_misses"] = sum(1 for r in audit if r.get("tests_found") is False)
        for st in report["stages"]:
            t = st["loop"]
            lo, hi = st["audit_lines"]
            rows = audit[lo:hi]
            recon = [p for p in prompts if p["loop"] == t]  # built in (problem, group) order = audit order
            n_cat_mm = n_blk_mm = 0
            for a, r in zip(rows, recon):
                if a.get("categories") != r["categories"]:
                    n_cat_mm += 1
                if a.get("n_feedback_blocks") != r["n_blocks"]:
                    n_blk_mm += 1
            audit_checks["per_stage"].append({"loop": t, "n_audit_rows": len(rows), "n_reconstructed": len(recon),
                                              "category_mismatches": n_cat_mm, "block_count_mismatches": n_blk_mm})
            audit_checks["category_mismatches"] += n_cat_mm
            audit_checks["block_count_mismatches"] += n_blk_mm

    # ---- validation summary (the smoke checklist) ----
    metrics_path = args.squeeze_evolve_dir / "outputs" / outdir.name / "metrics.json"
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else []
    loops_in_metrics = sorted({m.get("loop") for m in metrics})
    pin_pop = [json.loads(l) for l in open(outdir / "loop0_population.jsonl")]
    ck0 = cks[0]["problems"]
    pin_ok = (len(pin_pop) == len(ck0) and
              all(r["candidates"] == p["candidates"] for r, p in zip(pin_pop, ck0)))

    cat_counter = Counter(r["category"] for r in fb_rows)
    allpass_no_block = all(not r["has_block"] for r in fb_rows if r["category"] == "all_pass")
    failed_have_block = all(r["has_block"] for r in fb_rows
                            if r["category"] in ("wrong_answer", "runtime_error", "compile_error",
                                                 "timeout", "no_code", "no_callable"))
    required_meta = ["run_manifest.json", "pinned_subset.jsonl", "loop0_population.jsonl",
                     "loop0_source_manifest.json", "pyramid_run_report.json",
                     "parent_groups.jsonl", "feedback_records.jsonl", "feedback_operator_audit.jsonl"]
    summary = {
        "schedule": schedule,
        "population_funnel_verified": [len(p["candidates"]) for p in cks[len(schedule)]["problems"]],
        "no_fresh_loop0_generation": {
            "loop0_pinned_matches_checkpoint": pin_ok,
            "metrics_loops_run": loops_in_metrics,
            "loop0_absent_from_metrics": 0 not in loops_in_metrics,
        },
        "operator_fired_from_loop1": bool(report["stages"]) and report["stages"][0]["audit_lines"][1] > 0,
        "all_pass_blocks_omitted": allpass_no_block,
        "visible_failed_blocks_inserted": failed_have_block,
        "parent_group_integrity_mismatches": len(mismatches),
        "category_distribution": dict(cat_counter),
        "audit_cross_check": audit_checks,
        "checkpoints_present": [f"{args.run_name}_loop{t}.json" for t in range(len(schedule) + 1)],
        "metadata_present": {m: (outdir / m).exists() for m in required_meta},
        "n_parent_groups_rows": len(pg_rows),
        "n_feedback_records": len(fb_rows),
        "n_prompt_samples": len(picked),
    }
    (outdir / "validation_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    hard_ok = (pin_ok and summary["no_fresh_loop0_generation"]["loop0_absent_from_metrics"]
               and allpass_no_block and failed_have_block and not mismatches
               and audit_checks["fallbacks"] == 0)
    print(f"\nVALIDATION {'PASS' if hard_ok else 'FAIL'}")
    return 0 if hard_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
