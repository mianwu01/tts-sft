# NODE4 status — 16k / loop=10 SE on AIME + HMMT (verifier-free, strip=false)

**Owner:** node4 session (8×A100-80GB, shared /mnt/cpfs). Assignment confirmed by Harman
(2026-06-09): run verifier-free SqueezeEvolve `max_tokens=16384, loops=10, strip_think=false`
on **AIME + HMMT** non_saturated subsets. node3 owns LCBV6 separately (not run here).

Settings (from `scripts/run_se_16k_loop10.sh node4 false aime hmmt`):
`population=16, loops=10 → N_i=160 gen/problem`, `update=replace`, `fitness=diversity`,
`selection=uniform`, `evaluation=none` (verifier-free), `temp=1.0, top_p=0.95, top_k=20`,
recombination `{aime25,hmmt25}-aggregate`, `max_model_len=131072`, TP8.

## Timeline / progress

- **2026-06-09 02:41** — vLLM served: TP8 @ max-model-len 131072, port 8000, Qwen3-4B-Thinking-2507
  (explicit snapshot path, `VLLM_USE_MODELSCOPE=False`, `HF_HUB_OFFLINE=1`, proxies unset).
  `/health == 200` after ~210s. Model id confirmed `Qwen/Qwen3-4B-Thinking-2507`.
- **2026-06-09 02:44** — Run launched detached: `nohup bash scripts/run_se_16k_loop10.sh node4 false
  aime hmmt > /tmp/node4_run.log 2>&1 &`. AIME (18 problems) loop 0 generating 288 candidates.
- **2026-06-09 02:47** — Generation healthy: 48 concurrent reqs, ~3500 tok/s, KV cache ~12%,
  no proxy/SOCKS/errors. Run order: AIME first, then HMMT.

## Outputs (expected)

- `outputs/node4_loop10_16k_stripfalse_aime_non_saturated/` (se.jsonl, raw.json, checkpoints/loops0-9,
  loop_candidates.jsonl)
- `outputs/node4_loop10_16k_stripfalse_hmmt_non_saturated/`
- Run log: `/tmp/node4_run.log`; vLLM log: `/tmp/<HOSTNAME>_vllm.log`.

## Grading (offline, after each dataset) — task=math

See NODE34_HANDOFF.md §5: `scripts/score_se_subset.py --task math` against
`data/filtered/<ds>_non_saturated.jsonl`, metrics from
`external/squeeze-evolve/outputs/.../metrics.json`.

## Caveats baked in

- 16k truncates ~half of long math reasoning → expect **high cap-hit on AIME/HMMT**. Intended
  budget point, not a bug. loop10 supersedes the earlier ≤loop-5 ceiling.
- On any non-zero exit (e.g. context overflow): STOP that dataset, report exact problem/prompt_tokens,
  no silent retry.

## Results

### AIME (18 problems) — DONE 2026-06-09 04:18, graded `task=math`

`RESULT-DEPENDENT` (from `outputs/node4_loop10_16k_stripfalse_aime_non_saturated/summary.json`):

| metric | value |
|---|---|
| `se_all_solved` (any-of-160, all loops) | **15 / 18** |
| `se_final_solved` (loop-9 final pop) | 10 / 18 |
| `total_correct_traces` | 1479 |
| N_i nominal | 160 (16 pop × 10 loops) |

- **Frontier matches the 32k/loop5 result (15/18 SE-all).** 16k/loop10 reaches the *same* AIME
  set — no new problems reached, and `update=replace` again erodes the final pop (15→10).
- **Cap-hit (re-graded with `--max-tokens 16384`)** concentrated at **loop 0 = 93.75%**, then
  ~0% for loops 1–9 (1:0, 2:0, 3:1.0%, 4:0, 5:0.35%, 6:0.35%, 7:0, 8:0, 9:0). I.e. fresh-reasoning
  loop-0 traces truncate heavily at 16k as predicted, but strip=false recombination loops emit
  shorter aggregated traces that fit — so reachability survives the tight cap.
- Runtime ~1h33m (loop 0 slowest at 1307s; later loops 300–470s as outputs shorten).
- **Grading caveat fixed:** first grading pass used the script's default `--max-tokens 32768`,
  which mis-derives cap-hit for a 16k run; re-graded with `--max-tokens 16384` (solve counts are
  exact-match and were unaffected). `summary.json`/`genlog.jsonl`/`per_problem.jsonl` now reflect 16384.

### HMMT (21 problems) — DONE 2026-06-09 06:05, graded `task=math` (`--max-tokens 16384`)

`RESULT-DEPENDENT` (from `outputs/node4_loop10_16k_stripfalse_hmmt_non_saturated/summary.json`):

| metric | value |
|---|---|
| `se_all_solved` (any-of-160, all loops) | **12 / 21** |
| `se_final_solved` (loop-9 final pop) | 10 / 21 |
| `total_correct_traces` | 1126 |
| N_i nominal | 160 (16 pop × 10 loops) |

- Cap-hit: **loop 0 = 96.13%**, ~0% loops 1–9 (same shape as AIME).
- Runtime ~1h47m. Whole node4 run (AIME+HMMT) finished 06:05:44, exit clean, no retries.

## Cross-run comparison (16k/loop10 here vs prior 32k/loop5, SE-all reachability)

| dataset | 32k / loop5 (N=80) SE-all | **16k / loop10 (N=160) SE-all** | Δ |
|---|---|---|---|
| AIME | 15 / 18 | **15 / 18** | 0 (frontier held) |
| HMMT | 14 / 21 | **12 / 21** | **−2 (frontier lost)** |

(32k/loop5 numbers: persistent memory `se-formal-temp1-results.md` / `NODE1_SE_NON_SATURATED_RESULTS.md`.)

**Reading (`RESULT-DEPENDENT`):** doubling loops (10 vs 5) at the tighter **16k** budget did **not**
expand reachability — AIME stayed at 15, and HMMT actually *dropped* 14→12. The 16k cap truncates
~96% of fresh loop-0 reasoning; for some HMMT problems the long single-trace reasoning that a 32k
budget admits is never produced, and strip=false recombination over truncated parents does not
reconstruct it. `update=replace` again erodes the final population below SE-all (AIME 15→10,
HMMT 12→10). Consistent with the standing finding that this single-model/diversity setting buys
**depth, not reach** — and at 16k the lost loop-0 depth even costs reach on HMMT.

## Run complete

Both assigned datasets done, graded, no failures. vLLM (pid 515090, TP8 on this box) is **still
running** — leave for any re-grade/strip=true follow-up, or kill to free the 8×A100
(`kill 515090`). No further node4 generation queued.
