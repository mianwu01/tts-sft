# NODE3 status — LCBV6, verifier-free SE, 16k / loop10, strip=false

**Run complete + graded (2026-06-09).** Confirmed assignment (Harman): node3 → LCBV6, strip_think=false.

## What ran
- `bash scripts/run_se_16k_loop10.sh node3 false lcbv6` — official squeeze-evolve, single model
  Qwen3-4B-Thinking-2507 via vLLM TP8 @ max_model_len 131072.
- Config: loops=10, population=16, k=4, groups=16, max_tokens=16384, temp=1.0, top_p=0.95,
  top_k=20, fitness=diversity, selection=uniform, **update=replace**, verifier-free
  (`livecodebench-none`), recombination=`livecodebench-aggregate`, strip_think=false.
- N_i nominal = 16 × 10 = 160 generations/problem. 126 non_saturated problems.
- Timing: started 02:15, all 10 loops done 13:14 (~11h wall). Loop 0 = 2h05m (cold), later
  loops ~3.4–4.3k s. No failures.
- Outputs: `outputs/node3_loop10_16k_stripfalse_lcbv6_non_saturated/`
  (se.jsonl, se.jsonl.raw.json, se.jsonl.checkpoints/loop0-9, se.jsonl.loop_candidates.jsonl=20160 recs,
  genlog.jsonl, per_problem.jsonl, summary.json). metrics.json under
  `external/squeeze-evolve/outputs/node3_loop10_16k_stripfalse_lcbv6_non_saturated/`.

## Grading (offline, code harness, --max-tokens 16384)
`scripts/score_se_subset.py --task code --dataset lcbv6_node3_16k_loop10 --max-tokens 16384`

| Metric | Value |
|---|---|
| SE-all solved (union over loops 0–9) | **86 / 126** |
| SE-final solved (loop 9 population)  | **71 / 126** |
| total correct traces | 9295 |

Per-loop solved: 74, 84, 78, 77, 75, 74, 74, 72, 71, 71 (peak loop 1, monotonic erosion after).
Cap-hit rate: loop 0 = 0.435 (extraction 0.60); loops 1–9 ≈ 0 (extraction ~0.98–0.99).

## Findings vs priors
- vs 32k/loop5 (node1): SE-all 90→**86**, SE-final 80→**71**. Halving the token budget loses reach
  on code that doubling loops does NOT recover.
- 16k truncation hits hardest at loop 0 with strip=false (43.5% cap-hit) — full-reasoning code
  traces overflow 16k; handoff's "near-0 cap-hit on code" did not hold for strip=false loop 0.
- `update=replace` erosion worse than 32k (peak 84 → final 71, −13) vs 32k's 90→80 (−10).
- Consistent with the project's negative result: SE does not widen the reachable set; the SE-all
  union just preserves the loop-1 peak that replace later discards.
