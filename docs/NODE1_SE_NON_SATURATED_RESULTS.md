# Node 1 — Formal SqueezeEvolve (verifier-free) on non_saturated subsets

First formal SE arm of the SE-vs-BoN comparison, run **2026-06-07** on the calibration-derived
`non_saturated` subsets. **Verifier-free**: `fitness=diversity`, `evaluation=none`, and for LCBV6
`gt=None` — **no test/verifier feedback ever entered SE selection or recombination**. Tests/golds
were used **only** for offline scoring after generation.

## Settings (identical across all three datasets)
- Model `Qwen/Qwen3-4B-Thinking-2507`; SE official client + `scripts/run_squeeze_evolve.py`.
- `population=16, loops=5, groups=16, k=4, update=replace, strip_think=false`.
- Sampling **temperature=1.0, top_p=0.95, top_k=20** (forced via `extra_body`; confirmed in vLLM
  `SamplingParams`), `max_tokens=32768`.
- Serving **vLLM tensor-parallel-size=8 @ max_model_len 262144**, `request_timeout=7200`.
- Nominal budget **N_i = population × loops = 80 candidates/problem** (verified: 80 per problem in
  every run's `loop_candidates.jsonl`).
- Recombination: math = `aime25-aggregate` / `hmmt25-aggregate`; code = `livecodebench-aggregate`
  (new code-aware operator, `is_code=True`, "Return your final code in a single Python code block").
- Grading (offline): math = repo LaTeX-aware exact-match; code = hidden private test suite via
  `scripts/lcb_exec_harness.py` (same method as calibration). **SE-all** = any of the 80 candidates
  (all loops) correct; **SE-final** = any of the 16 final-loop (loop 4) candidates correct.

**No context-length overflow, no failed requests, no truncated/skipped problems** in any run.
Per-candidate token counts / `finish_reason` in the gen-logs are **derived offline** (tokenized
`full_response`; cap_hit = output ≥ max_tokens−8); authoritative per-loop token totals are from each
run's `metrics.json` (`metrics_json_per_loop_tokens` in the summaries; derived sums match within
rounding — e.g. AIME loop-1 input 31,071,734 identical).

---

## AIME non_saturated (18 problems)
- **SE-all 15/18 · SE-final 14/18** · total correct traces **1,006 / 1,440**.
- Per-loop solved: **15 · 15 · 15 · 14 · 14** (loops 0–4). **No reachability gain** — every solved
  problem was already solved at loop 0; recombination added density, not reach. The 3 unsolved stayed
  unsolved at every loop.
- cap-hit by loop: 0.40 · 0.004 · 0 · 0 · 0. extraction (boxed): 0.78 · 1.0 · 1.0 · 1.0 · 1.0.
- Tokens (metrics.json): **38.3M in / 10.0M out / 48.3M total**. Wall ~107 min.

## HMMT non_saturated (21 problems)
- **SE-all 14/21 · SE-final 12/21** · total correct traces **657 / 1,680**.
- Per-loop solved: **12 · 14 · 13 · 12 · 12**. **loop-1 recombination reached 2 problems loop-0
  missed** (12→14) — a small genuine reachability signal — but `update=replace` then dropped them, so
  the final population is back to 12 (SE-all retains the 14).
- cap-hit by loop: 0.42 · 0 · 0 · 0 · 0. extraction: 0.82 · 1.0 · 1.0 · 1.0 · 1.0.
- Tokens: **45.8M in / 11.9M out / 57.7M total**. Wall ~120 min.

## LCBV6 non_saturated (126 problems)
- **SE-all 90/126 · SE-final 80/126** · total correct traces **4,473 / 10,080**.
- Per-loop solved: **90 · 84 · 83 · 82 · 80**. **SE-all (90) == loop-0 count → recombination reached
  ZERO new problems**, and the final population strictly **degraded** (90 → 80) as `update=replace`
  discarded correct loop-0 programs that later loops failed to reproduce.
- cap-hit by loop: 0.003 · 0 · 0 · 0 · 0 (code generations rarely hit the 32k cap). code-extraction
  by loop: 0.999 · 1.0 · 0.977 · 0.995 · 0.974.
- Tokens: **176.4M in / 51.0M out / 227.5M total** (k=4 full-trace code recombination is very
  input-heavy: loop-1 alone = 114.6M input tokens). Wall ~490 min (8h10m).

---

## Combined non_saturated total
| dataset | problems | SE-all | SE-final | correct traces | per-loop solved (0→4) | tokens in / out |
|---|---|---|---|---|---|---|
| AIME  | 18  | **15** | 14 | 1,006 | 15·15·15·14·14 | 38.3M / 10.0M |
| HMMT  | 21  | **14** | 12 | 657   | 12·14·13·12·12 | 45.8M / 11.9M |
| LCBV6 | 126 | **90** | 80 | 4,473 | 90·84·83·82·80 | 176.4M / 51.0M |
| **Total** | **165** | **119** | **106** | **6,136** | — | **260.6M / 73.0M (333.5M)** |

Total wall ~12 h (11:11→23:10). Grand total tokens **333.5M** (260.6M in / 73.0M out).

## Headline reading (SE arm only; the BoN comparison is Node 2's)
1. **Recombination did not expand reach in any dataset.** SE-all == loop-0 solved count for AIME
   (15) and LCBV6 (90); HMMT is the only exception, where loop 1 reached **+2** problems (12→14).
2. **`update=replace` erodes the final population**, most visibly on code (LCBV6 90→80) and AIME/HMMT
   (final < SE-all). The best loop for *reach* is loop 0–1; later loops add density on already-solved
   problems and lose some solved ones from the surviving population.
3. **This is the SE arm in isolation** — whether SE beats matched-compute independent BoN (N=80) is
   decided by Node 2's arm; nothing here is a compute-matched comparison.

## Exact output paths
- `outputs/node1_se_loop5_32k_temp1_aime_non_saturated/`  — `se.jsonl`, `se.jsonl.raw.json`,
  `se.jsonl.checkpoints/` (loops 0–4), `se.jsonl.loop_candidates.jsonl` (1,440), `genlog.jsonl`,
  `per_problem.jsonl`, `summary.json`.
- `outputs/node1_se_loop5_32k_temp1_hmmt_non_saturated/`  — same layout (1,680 candidates).
- `outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/` — same layout (10,080 candidates).
- Per-loop token metrics: `external/squeeze-evolve/outputs/node1_se_loop5_32k_temp1_<ds>_non_saturated/metrics.json`.
- Configs: `configs/squeeze_evolve_loop5_32k_temp1_{aime,hmmt,lcbv6}_non_saturated.yaml`.
- Seeds: `data/filtered/{aime,hmmt,lcbv6}_non_saturated.jsonl`.

**Verifier/test note (explicit):** tests and gold answers were **not** used inside SqueezeEvolve at
any point (fitness=diversity, evaluation=none, LCBV6 gt=None). They were applied only in the offline
scoring step (`scripts/score_se_subset.py`).
