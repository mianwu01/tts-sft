#!/usr/bin/env python3
"""Build a PINNED loop-0 checkpoint for the Feedback-SE pilot by subsetting the strip=false rerun #1
loop-0 population (outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated) to a chosen problem subset,
preserving seed order. Writes the SE-format loop-0 checkpoint + anchor metadata so future A/B pairing
can reuse the identical anchor. Reuses #1's loop-0 candidates verbatim — NO new generation.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-checkpoint", required=True, type=Path,
                    help="#1 loop-0 checkpoint json (problems[] with candidates[], metrics.loop=0).")
    ap.add_argument("--source-run", default="tts_sft_se_loop5_32k_temp1_lcbv6_non_saturated_node1")
    ap.add_argument("--subset-seed", required=True, type=Path, help="JSONL {id, question, ...} in desired order.")
    ap.add_argument("--checkpoint-out", required=True, type=Path, help="Where to write <run>_loop0.json (the pin).")
    ap.add_argument("--metadata-dir", required=True, type=Path, help="Dir for anchor metadata files.")
    args = ap.parse_args()

    src = json.loads(args.source_checkpoint.read_text())
    by_q = {}
    for p in src["problems"]:
        q = p.get("question") or p.get("orig_prompt")
        if q is not None:
            by_q[q] = p
    seed = [json.loads(l) for l in args.subset_seed.open()]

    picked, missing, pop = [], [], []
    for s in seed:
        q = s["question"]
        p = by_q.get(q)
        if p is None:
            missing.append(s.get("id")); continue
        # sanity: loop-0 problem must carry a candidate population and empty groups
        assert p.get("candidates"), f"no candidates for {s.get('id')}"
        picked.append(p)
        pop.append({"id": s.get("id"), "n_candidates": len(p["candidates"]), "candidates": p["candidates"]})
    if missing:
        raise SystemExit(f"ERROR: {len(missing)} subset problems not found in source checkpoint: {missing}")

    # SE-format loop-0 checkpoint (metrics.loop=0 -> resume continues from loop 1)
    ck = {"problems": picked, "metrics": dict(src.get("metrics", {})), }
    ck["metrics"]["loop"] = 0
    args.checkpoint_out.parent.mkdir(parents=True, exist_ok=True)
    args.checkpoint_out.write_text(json.dumps(ck, ensure_ascii=False))

    md = args.metadata_dir; md.mkdir(parents=True, exist_ok=True)
    (md / "pinned_subset.jsonl").write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in seed))
    (md / "loop0_population.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in pop))
    src_sha = hashlib.sha256(args.source_checkpoint.read_bytes()).hexdigest()[:16]
    (md / "loop0_source_manifest.json").write_text(json.dumps({
        "loop0_reused_from": str(args.source_checkpoint),
        "source_run": args.source_run,
        "source_run_dir": "outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated",
        "source_strip_think": False, "source_loops": 5, "source_max_tokens": 32768,
        "source_se_all_solved": 90, "source_checkpoint_sha256_16": src_sha,
        "n_subset_problems": len(picked), "subset_seed": str(args.subset_seed),
        "pinned_checkpoint": str(args.checkpoint_out),
        "candidates_per_problem": [len(p["candidates"]) for p in picked],
        "note": "Loop-0 reused verbatim from strip=false rerun #1; NO new loop-0 generation. "
                "Feedback-SE (vfonly) starts at loop 1.",
    }, indent=2))
    print(f"pinned {len(picked)} problems -> {args.checkpoint_out}")
    print(f"  candidates/problem: min {min(len(p['candidates']) for p in picked)} "
          f"max {max(len(p['candidates']) for p in picked)} | metrics.loop={ck['metrics']['loop']}")
    print(f"  metadata -> {md}/ (pinned_subset.jsonl, loop0_population.jsonl, loop0_source_manifest.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
