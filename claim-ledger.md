# claim-ledger.md

Status of every load-bearing claim for the reachability diagnostic.
Labels: `CODE-SUPPORTED` (source we read/ran) · `RESULT-DEPENDENT` (needs generated logs) ·
`PAPER-ONLY` (docs only) · `HUMAN-VERIFY` (needs human confirmation). Updated 2026-06-04,
**after prep, before any generation run** (no model was called).

| # | Claim | Label | Evidence | Notes / what would change it |
|---|---|---|---|---|
| 1 | Independent N-rollout infrastructure exists | `CODE-SUPPORTED` | `scripts/run_independent_rollouts.py`; `--help` exit 0; `tests/test_independent_rollouts.py` green (record schema, null-answer, copy-safety) | Backward-compatible: `run_raw_generation.py` untouched. Emits `responses[]`, `source:"independent_rollouts"` |
| 2 | Reachability evaluator categorizes correctly | `CODE-SUPPORTED` | `scripts/eval_reachability.py`; `tests/test_eval_reachability.py` green; end-to-end on fixtures → `total=4 both=1 only_se=1 only_independent=1 neither=1` | Any-of-N on both arms via the repo's exact-match grader |
| 3 | SE per-problem budget extractor exists | `CODE-SUPPORTED` | `scripts/se_budget.py`; `tests/test_se_budget.py` green; ran on fixtures (4 records) | The tool exists; the *number* it needs is not yet recoverable — see #4 |
| 4 | True compute-matching between arms is possible **now** | `HUMAN-VERIFY` (**blocked**) | `se_budget.py` returns `budget_status:"UNKNOWN"`, `estimated_total_generations:null` for all fixtures; `n_candidates` = final population ≠ total rollouts | Unblocks only after a real SqueezeEvolve smoke run exposes per-problem total generations in `metrics`/`routing_details`, then `_extract_total_generations()` is updated |
| 5 | We use the **official** SqueezeEvolve (wrapper path + CLI + config + input loader) | `CODE-SUPPORTED` | Cloned `external/squeeze-evolve/`; `pyproject.toml` `[project.scripts] squeeze-evolve-client = squeeze_evolve.api.cli:client`; `core/config.py` `RunConfig` (`population`/`loops`/`fitness`/`recombination`); `core/data.py` loads JSONL→`{orig_prompt, gt}` | End-to-end has NOT run (no model). Output fields beyond `candidates` remain `PAPER-ONLY` until a smoke run |
| 6 | SqueezeEvolve reaches solution space matched independent sampling does not | `RESULT-DEPENDENT` | none — zero generation has run | The whole point of the diagnostic; needs Arm A + Arm B logs |
| 7 | Grading = exact-match only (no symbolic equivalence) | `CODE-SUPPORTED` (+ limitation) | `src/tts_sft/answer_extraction.py:1-5,128-140` | May undercount equivalent LaTeX → can bias a *reachability count*; consider adding `math_verify` for the diagnostic |
| 8 | SqueezeEvolve full-run hyperparameters | `HUMAN-VERIFY` | `configs/squeeze_evolve_generation.yaml` values are DEFAULTS (`population 4`, `loops 4`, `fitness diversity`) | Placeholders → await Harman's friend; treat as `TODO_HARMAN_CONFIRM` |
| 9 | Base model `Qwen/Qwen3-4B-Thinking-2507` available | `HUMAN-VERIFY` | not on disk (no HF cache, not in `wujunyi/models/`) | `hf download` once approved |
| 10 | Independent rollouts match SqueezeEvolve sampling | `CODE-SUPPORTED` (params) / `HUMAN-VERIFY` (N) | `run_independent_rollouts.py` defaults `temp 0.7 / top_p 0.95 / max_tokens 8192` = SE config | Per-problem `N=N_i` matching still blocked by #4 |
| 11 | Test suite green after changes | `CODE-SUPPORTED` | `python -m pytest -q` → **97 passed in 0.67s** (re-verified 2026-06-04 session 2 on this box; 87 → 97 after `test_run_squeeze_evolve.py` + `test_se_loop_candidates.py`); 13× `--help` exit 0 | Re-run after any edit |

## 2026-06-04 — session 2 (verification + Node 1 safe prep on this box; no model called)

Env on this machine: system Python 3.11.11 already had the full ML stack (torch 2.6.0+cu124, transformers 4.55, trl 0.20, peft 0.16, accelerate 1.10, bitsandbytes 0.47, …); **only `pytest` was missing** → installed. 8× A100-80GB visible. No venv needed.

New / upgraded evidence (all `CODE-SUPPORTED`, no model):
- **Official SE now INSTALLED** (was clone-only) → upgrades claim #5. `pip install hatchling editables` then `pip install -e ".[dev]" --no-build-isolation` (the Aliyun PyPI mirror SSL-flakes inside pip's build-isolation subprocess). `squeeze-evolve-client` → `/usr/local/bin/squeeze-evolve-client`; `import squeeze_evolve` OK. SE `pyproject.toml` has **no dependency on the `external/vllm` fork** (only for `fitness: confidence`), so the unfetched submodule is a non-issue for our `diversity` config.
- **Real CLI flags match the wrapper**: `--config/--input/--output/--n-problems` (+ optional `--include-path`). Wrapper `--dry-run` builds the correct command against the real client.
- **Config validates under live `RunConfig` + operator registry**: `_discover_benchmarks()` + `load_run_config()` succeed; `aime25-aggregate`/`aime25-none` register; parsed `loops=4, population=4, groups=4, k=4, fitness=diversity, strip_think=False`, 1 model.
- **Full MATH500 seed built**: `data/seeds/math500_seed.jsonl` (500× `{id,question,answer}`, all valid).

Still blocked (unchanged): `loops=4` must become Harman's "loop 2" — **count-vs-index unconfirmed** (SE: `loops` is a count, `range(loops)` → t=0..loops-1, t=0=init, t≥1=evolution); base model not downloaded; vLLM not serving; per-problem budget `N_i` still UNKNOWN (claim #4) until a smoke run; Harman hyperparameters + go for the gated loop=2 smoke.

## 2026-06-04 — session 3 (authorized 1-problem loop=2 smoke; first real generation)

Model downloaded + vLLM serving (GPU 0, :8000). Loop interpretation **confirmed by Harman: loops=2 = count → loop_index 0,1**; separate config `configs/squeeze_evolve_loop2_smoke.yaml` (defaults untouched). Ran official SE, `--n-problems 1`, 2 loops. Status flips:
- **Claim #4 (compute-matching possible now) → `CODE-SUPPORTED` / UNBLOCKED.** `se_budget.py` recovers per-problem `N_i = 8` (`budget_status=FROM_RAW_METRICS`) from per-loop `metrics.model_0_count` (4+4); final population (4) ≠ budget. `se_budget._total_generations_from_metrics()` added (minimal update).
- **Claim #5 (official SE end-to-end) → observed/`CODE-SUPPORTED`.** raw.json schema confirmed: `{run_id, metrics:[per-loop with model_0_count/*_tokens], problems:[{candidates, candidate_groups, routing_details(dict)}]}`; per-loop checkpoints `<run_name>_loop{0,1}.json` preserved to `<output>.checkpoints/`.
- **Every-loop saving observed:** 8 flattened candidates (loop0×4+loop1×4) with full_response, thinking_trace, final_answer, parent lineage (loop1 `[3,0,2,1]`), fitness (loop1 `1.0`), routing_metadata; score null under diversity (honest).
- **Bug fixes (pytest 99 passed):** `run_squeeze_evolve.py` raw-output path resolved to absolute (relative path was written inside the clone → rc=4); `se_loop_candidates.split_thinking` handles Qwen3-Thinking closing-tag-only output.
- **Claim #7 (exact-match undercounts) confirmed live:** model solved the problem (`(3,\frac{\pi}{2})`) but SE eval scored 0.0 vs gold `\left( 3, \frac{\pi}{2} \right)` — LaTeX `\left(\right)` mismatch → consider `math_verify` before reachability counts.
- Still gated: 5-problem / full generation / loop>2 (await explicit go).

## 2026-06-04 — session 4 (formal reachability pilot: AIME25 ×5, authorized)

Official SE, loops=2/pop=16/groups=16/k=4/diversity/temp=**0.6**/max_tokens=32768/**strip_think=false** (full-reasoning recombination), served via **vLLM TP=8 @ max_model_len 131072** (all 8 GPUs). Config `configs/squeeze_evolve_loop2_reachability_pilot.yaml`; seed `data/seeds/aime25_seed_pilot5.jsonl`. rc=0, ~15.6 min, **no overflow/timeouts**.
- **Claim #4 confirmed at scale:** `N_i = 32` uniform for all 5 (`FROM_RAW_METRICS`; metrics `model_0_count` 80+80=160/5). se_budget recovers it directly.
- **Every-loop saving at scale:** 160 candidates (80+80); full_response 160/160; thinking_trace 117/160 (43 short/no-`</think>` direct answers, full text still saved); loop1 lineage/fitness/routing 80/80; score null (diversity).
- **Grading (any-of-N over 32/problem):** 5/5 solved; exact-match == lenient-integer → **NO AIME exact-match false negatives** (contrast MATH500 polar-coords). SE's logged `0.0` eval = disabled `aime25-none` placeholder, not accuracy.
- **No code changes this session** (config+seed only); pytest 107 passed.
- **Node 2:** matched independent rollouts use **N=32, temperature 0.6** (NOT 0.7) — command in docs/NODE1_STATUS.md §11.
- Still gated: loops>2, 30-problem scale-up, Node 2 generation, SFT, strip_think=true ablation.

## 2026-06-05 — session 5 (AIME25 hard-tail mini-pilot: 7 non-easy ids)

strip_think=false @ max_model_len **131072 OVERFLOWED at loop 1** (hard problems max loop-0 traces → k=4 recomb = 158,419 > 131,072; SE doesn't skip over-length, `resume` can't continue past loop 0). **Re-ran at vLLM TP8 @ 262144** (native max): rc=0, ~50 min, no overflow. Config `configs/squeeze_evolve_loop2_aime25_hardtail7.yaml`; seed `data/seeds/aime25_seed_hardtail7.jsonl`. N_i=32 uniform (FROM_RAW_METRICS). 224 candidates saved (full_response 224/224; final_answer 173/224 — 51 hit the 32768 cap; thinking_trace 125/224).
- **SE-all 4/7, SE-final 4/7.** Solved 000009/000019/000027/000029; UNSOLVED 000012/000013/000014 (hardest 0/8, no correct parent).
- **1 of four 0/8 problems (000027) solved by SE.** Loop-1 recombination CONCENTRATED correct solutions (000019 7→16, 000009 4→10) but reached no problem loop-0 had 0 on (loop0-alone == loop1-alone == 4/7) at loops=2.
- ⚠️ 4/7 (N=32) vs ~3/7 (indep N=8) is NOT matched — needs independent **N=32** (Node 2).
- No code changes. Confirms claim #4 at scale again (N_i=32). Still gated: loops>2, Node 2 generation, SFT.

## 2026-06-05 — session 6 (overnight: Stage A HMMT13 loops=2, Stage B full20 loops=3)

vLLM TP8 @ max_model_len 262144 (pre-flight health-checked). Both stages rc=0, **no overflow/timeout/schema errors**. N_i: Stage A 32 (all 13), Stage B 48 (all 20), FROM_RAW_METRICS — budget rule holds at scale.
- **Stage A** (HMMT13 loops=2, ~87 min): SE-all 6/13. Loop-1 recombination reached 2 problems loop-0 missed (hmmt000012, hmmt000028); **hmmt000028 (hard, indep 0/8) reached ONLY by recombination**.
- **Stage B** (full20 loops=3, ~158 min): SE-all 10/20 (AIME 4/7, HMMT 6/13; medium 8/9, hard 2/11). **new-at-loop2 = 0 — loops=3 gave NO reachability gain over loops=2**, only deeper density (same 10/20 solved set, reproducible). Both solved hard problems (aime000027, hmmt000028; indep 0/8) first reached at loop 1.
- **Reachability signal (claim #6):** evolutionary recombination reached 2 hard problems that initial sampling (pop-16) and indep N=8 missed — but vs indep N=8, NOT compute-matched. Matched test = independent N=32 (Stage A) / N=48 (Stage B), Node 2. RESULT-DEPENDENT until that runs.
- No code changes. Still gated: loops>3, Node 2 generation, SFT.
