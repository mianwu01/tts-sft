# NODE2_STATUS.md — Independent-rollout baseline + reachability eval (prep only)

**Role:** Node 2 of the SqueezeEvolve reachability diagnostic — the *compute-matched
independent-sampling* arm and the offline reachability comparison. **Node 2 does NOT run
SqueezeEvolve.** Node 1 owns official SqueezeEvolve setup + the loop=2 smoke/pilot.

**Date:** 2026-06-04. **Status: PREP ONLY. No model was called; no API request was made;
no generation, SFT, or RL was run.** Evidence labels per `CLAUDE.md`:
`CODE-SUPPORTED` / `RESULT-DEPENDENT` / `PAPER-ONLY` / `HUMAN-VERIFY`.

This file is a **new, Node-2-owned doc** — created instead of editing the shared
`HANDOFF.md` (filesystem is shared with the Node 1 session). Node 2 must not modify
Node 1's `configs/squeeze_evolve_generation.yaml` or write into Node 1 output paths.

---

## 1. Environment status (this machine)

| Item | State | Evidence |
|---|---|---|
| Python | 3.11.11, system `/usr/local/bin/python` (no `.venv`) | `CODE-SUPPORTED` (ran) |
| Heavy deps (torch, transformers, trl, peft, openai, yaml, pydantic, numpy, pandas) | importable | `CODE-SUPPORTED` (ran) |
| `pytest` | **was missing → installed `pytest 9.0.3`** (the only dep installed; no heavy packages) | `CODE-SUPPORTED` (ran) |
| Base model `Qwen/Qwen3-4B-Thinking-2507` | **present & complete** in shared cache `…/hf_cache/hub/` (3 shards ≈7.6 GiB + index + tokenizer; no partial markers) — **not re-downloaded** | `CODE-SUPPORTED` (verified) |
| vLLM server (Node 2) | **RUNNING** — see §1b | `CODE-SUPPORTED` (health-checked) |

## 1b. Model serving (Node 2) — READY (health-checked; NO generation run)

Prepared 2026-06-04 ("Node 2 model serving only"). Node 2 serves its **own** endpoint on a
**dedicated GPU + distinct port** so it never collides with Node 1 (Node 1 keeps `localhost:8000`
per its config; this is a shared box — all 8 GPUs were free at launch).

| Field | Value |
|---|---|
| Model cache | shared `/mnt/cpfs/yangboxue/opsd/TTS/hf_cache`; snapshot `768f209d9ea81521153ed38c47d515654e938aea` **complete, not re-downloaded** |
| Served snapshot path | `…/hf_cache/hub/models--Qwen--Qwen3-4B-Thinking-2507/snapshots/768f209d9ea81521153ed38c47d515654e938aea/` (explicit local path, not name lookup) |
| Served model name | `Qwen/Qwen3-4B-Thinking-2507` (`--served-model-name`, so Node 2 scripts address it by canonical name) |
| Endpoint | **`http://localhost:8001/v1`** (port 8000 left for Node 1; 8001 chosen + documented) |
| GPU | **GPU 7** (`CUDA_VISIBLE_DEVICES=7`), away from Node 1's default GPU 0 |
| `max_model_len` | **40960** (native ctx 262144, `rope_scaling: null` → no scaling; 32768 fallback not needed) |
| GPU memory reserved | `gpu_memory_utilization=0.9` → **73,787 MiB used of 81,920 MiB** on GPU 7 (weights 7.6 GiB; KV cache 419,536 tokens ≈ 10.2× concurrency @40960; PID 321065) |
| Health checks | `/health` → 200; `/v1/models` → lists the model at `max_model_len=40960`. **No** `/v1/chat/completions` or `/v1/completions` called. |
| Background task | bash id `b0qpg5pf9`; log `/tmp/node2_vllm_8001.log` |

Exact command used (offline; no telemetry; explicit local path):
```bash
SNAP=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache/hub/models--Qwen--Qwen3-4B-Thinking-2507/snapshots/768f209d9ea81521153ed38c47d515654e938aea
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
CUDA_VISIBLE_DEVICES=7 VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 \
HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache DO_NOT_TRACK=1 VLLM_NO_USAGE_STATS=1 \
vllm serve "$SNAP" \
  --served-model-name Qwen/Qwen3-4B-Thinking-2507 \
  --host 0.0.0.0 --port 8001 \
  --max-model-len 40960 --gpu-memory-utilization 0.9
```

⛔ **Still blocked on Node 1.** Serving is ready, but Node 2 must NOT run independent rollouts
until Node 1's loop=2 smoke yields the real per-problem budget `N_i` and `se_budget.py` flips
`UNKNOWN → FROM_RAW_METRICS` (§4). The matched-rollout command (T3) targets
`--base-url http://localhost:8001/v1` once unblocked.

## 2. Verification run (safe; no model/API)

- `python -m pytest -q` → **97 passed in 0.52s** (was 87 in the prior session; +`test_run_squeeze_evolve.py`, +`test_se_loop_candidates.py`). `CODE-SUPPORTED`.
- `--help` exit 0 for: `run_independent_rollouts.py`, `eval_reachability.py`, `se_budget.py`, `run_raw_generation.py`. `CODE-SUPPORTED`.
- Offline reachability on bundled fixtures →
  `total=4 both=1 only_se=1 only_independent=1 neither=1` (all four categories exercised). `CODE-SUPPORTED`.
- `se_budget.py` on fixtures → every record `budget_status="UNKNOWN"`,
  `estimated_total_generations=null` (honest by design). `CODE-SUPPORTED`.

## 3. Node 2 code readiness (inspected, `CODE-SUPPORTED`)

**`scripts/run_independent_rollouts.py` — READY.**
- N rollouts/problem via `--n-samples` (loops `for i in range(n_samples)`), emits `responses:[...]`, `n_rollouts`.
- Sampling defaults **match SqueezeEvolve**: `temperature=0.7`, `top_p=0.95`, `max_tokens=8192` (not raw-gen's 0.6).
- Resume: whole-problem, via `read_existing_ids` (skips ids already in the output). `--overwrite` truncates first.
- `--limit N` (prefix of seeds). Per-sample distinct RNG via `--seed` (`seed+i`).
- Generation params recorded per record under `generation_params` (`temperature/top_p/max_tokens/n_samples/seed`).
- Partial-failure safety: if any of the N samples fails, the **whole problem is skipped** (never writes an under-budget record that would silently break compute-matching).
- Never grades / never imports the answer checker (grading is offline, separate).

**`scripts/eval_reachability.py` — READY.**
- Emits the 4 categories: `both_solved | only_se_solved | only_independent_solved | neither_solved` (`CATEGORIES`, `categorize()`).
- **Any-of-N on both arms**: pulls SE texts from `candidates`/`population`/`responses`/`final_response`; independent from `responses`/`response`.
- Grades with the repo's exact-match checker (`src/tts_sft/answer_extraction.py`) — no symbolic equivalence (known limitation).
- Compares only ids present in **both** arms; reports `n_only_in_se_file` / `n_only_in_independent_file`.
- Gold reconciliation: SE `gt` vs independent `answer`, warns on mismatch, uses SE `gt`.
- Optional `--se-budget-jsonl` / `--se-budget-json` to source `se_num_candidates` from Node 1's budget output.
- Summary JSON includes `ids_by_category` and any-of-N solved rates per arm (this rate **is** the arm's pass@N).

**`scripts/se_budget.py` — READY as a tool; the NUMBER it needs is still UNKNOWN.**
- Reads future Node 1 outputs: `--se-output` (normalized JSONL), `--raw-json` (`<output>.raw.json`), `--metrics-json` (`metrics.json`), `--config`.
- Honest contract: returns `estimated_total_generations` only if a recognized field (`total_generations`/`num_generations`/`n_generations`/`generations`) is found; else `null` + `budget_status="UNKNOWN"`. Never passes the final population size off as the total (reports it as `lower_bound_generations`). Records `raw_available_fields` to help locate the real field after a smoke run.

**`src/tts_sft/answer_extraction.py`** — last `\boxed{}` (balanced braces) → "answer is"/"final answer" regex; `normalize_math_answer` (strip `$`/braces/punct/thousands-sep); `is_exact_match` (normalized eq + float fallback). Shared grader for both arms. `CODE-SUPPORTED`.

**`src/tts_sft/metrics.py`** — only `accuracy()`. No `pass@k` function exists; the any-of-N "pass@N" is computed inside `eval_reachability.py`. `CODE-SUPPORTED`.

## 4. The compute-matching dependency on Node 1 (the crux)

True compute-matched independent rollouts need SqueezeEvolve's **per-problem total generations
`N_i`** (sum of LLM completions across all loops 0..t) — **not** the final population size.
`se_budget.py` returns `UNKNOWN` today (`HUMAN-VERIFY`, blocked). Two precise notes for when
Node 1's loop=2 smoke lands:

1. **Where `N_i` actually lives (`CODE-SUPPORTED` by SE source inspection).** With `update: replace`,
   the client's final `<output>.raw.json` keeps only the **final loop's** `routing_details` (a *dict*,
   per problem). The per-loop history is in the checkpoints Node 1 preserves to
   `<output>.checkpoints/<run_name>_loop<t>.json` (`orchestrator.py:458`, every loop). So `N_i` will
   most likely be recovered by **summing generation counts across those per-loop checkpoints** and/or
   from per-loop entries in `metrics.json` — *not* from the final raw.json.
2. **Exact code update needed.** `se_budget._extract_total_generations()` currently (a) only sums when
   `routing_details` is a **list**, and (b) accepts a `metrics` arg but does not yet parse it. After the
   smoke run reveals the real per-loop field, teach that function to read it (and/or add a
   checkpoint-summing path) so `budget_status` flips `UNKNOWN → FROM_RAW_METRICS`. This is a Node-1-data-driven
   change; do not guess the field name now.

**Per-problem vs global N.** `run_independent_rollouts.py --n-samples` is a **single global N**, not
per-problem. If Node 1's smoke shows `N_i` is ~uniform across problems, a single `--n-samples N` is a
valid match. If `N_i` varies per problem, matching requires either a conservative single N (e.g. max/median,
logged as such) or a small per-problem extension to the script. Decide once `N_i` is observed.

## 5. Command templates — ⛔ DO NOT RUN (each gate noted). All paths are Node-2-isolated.

Run dir for all of these: `cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft`.
Shared seed (must match Node 1): `data/seeds/math500_seed_smoke.jsonl` (5 problems, `{id,question,answer}`, all gold present).

```bash
# Common knobs (define once; do NOT export real keys)
SEED=data/seeds/math500_seed_smoke.jsonl        # same seed as Node 1 (smoke); swap to the agreed dataset later
MODEL=Qwen/Qwen3-4B-Thinking-2507
BASE_URL=http://localhost:8001/v1                # Node 2's OWN vLLM (§1b); Node 1 keeps :8000
N_PLACEHOLDER=16                                 # placeholder only; real N comes from Node 1's N_i
```

**T1 — Base model pass@1 (reference accuracy).** ⛔ GATE: base model downloaded + vLLM up (or local load) + Harman go-ahead.
```bash
# Repo's dedicated greedy pass@1 evaluator (loads model locally; or add --use-vllm-server --base-url $BASE_URL).
python scripts/eval_math.py \
    --eval-file "$SEED" \
    --model-name-or-path "$MODEL" \
    --output outputs/node2_independent_loop2_matched/base_pass1.jsonl \
    --temperature 0.0 --max-tokens 8192
```

**T2 — pass@k / N independent rollouts (UN-matched, placeholder N for plumbing).** ⛔ GATE: vLLM up + go-ahead.
```bash
python scripts/run_independent_rollouts.py \
    --input "$SEED" \
    --output outputs/node2_independent_loop2_matched/independent_N${N_PLACEHOLDER}.jsonl \
    --model "$MODEL" --base-url "$BASE_URL" --api-key EMPTY \
    --n-samples ${N_PLACEHOLDER} \
    --temperature 0.7 --top-p 0.95 --max-tokens 8192 \
    --seed 1234            # reproducible-but-distinct draws (reachability is a tail phenomenon)
# (Independent-arm pass@N is read out by T4's any-of-N solved rate once an SE file exists.)
```

**T3 — COMPUTE-MATCHED independent rollouts.** ⛔ GATE: `se_budget.py` reports `budget_status=FROM_RAW_METRICS`
(i.e. Node 1 smoke done + `_extract_total_generations` taught the real field). Set `N = N_i`.
```bash
# N_i := SqueezeEvolve's real per-problem total generations from Node 1's budget JSONL.
# If ~uniform across problems, use that single value; if it varies, see §4 (per-problem matching).
python scripts/run_independent_rollouts.py \
    --input "$SEED" \
    --output outputs/node2_independent_loop2_matched/independent_matched.jsonl \
    --model "$MODEL" --base-url "$BASE_URL" --api-key EMPTY \
    --n-samples <N_i_FROM_se_budget> \
    --temperature 0.7 --top-p 0.95 --max-tokens 8192 \
    --seed 1234
```

**T4 — Reachability comparison.** ⛔ GATE: Node 1 has produced its normalized SE output + (ideally) budget JSONL.
Read Node 1's paths read-only; confirm them with the Node 1 session — do not assume/overwrite.
```bash
# <NODE1_SE_OUTPUT>     e.g. data/generated/se_reach.jsonl  (Node 1 owns the exact path)
# <NODE1_SE_BUDGET>     e.g. data/results/se_budget.jsonl   (optional; sources se_num_candidates)
python scripts/eval_reachability.py \
    --se-output          <NODE1_SE_OUTPUT> \
    --independent-output outputs/node2_independent_loop2_matched/independent_matched.jsonl \
    --se-budget-jsonl    <NODE1_SE_BUDGET> \
    --output-jsonl       outputs/node2_reachability_loop2/reachability_per_problem.jsonl \
    --summary-json       outputs/node2_reachability_loop2/reachability_summary.json
# Headline = only_se_solved vs only_independent_solved (RESULT-DEPENDENT until logs exist).
```

**T0 — (bridge, runs on Node 1's data, no model) recover `N_i`.** ⛔ GATE: Node 1 smoke artifacts exist.
```bash
python scripts/se_budget.py \
    --se-output   <NODE1_SE_OUTPUT> \
    --raw-json    <NODE1_SE_OUTPUT>.raw.json \
    --metrics-json <NODE1_metrics.json> \
    --config      configs/squeeze_evolve_generation.yaml \
    --output      outputs/node2_reachability_loop2/se_budget.jsonl
# If budget_status stays UNKNOWN, STOP — compute-matching (T3) is not yet valid; update se_budget per §4.
```

## 6. Output namespace (Node-2-isolated; created)

- `outputs/node2_independent_loop2_matched/` — independent-rollout JSONL + base pass@1.
- `outputs/node2_reachability_loop2/` — reachability per-problem + summary + (bridge) budget JSONL.
- Node 2 **never** writes into Node 1 paths (e.g. `data/generated/se_reach*`, `<...>.checkpoints/`). It only **reads** Node 1's SE output for T4/T0.

## 7. Dataset alignment

- **Same seed file as Node 1** for a valid matched comparison. Smoke/pilot: `data/seeds/math500_seed_smoke.jsonl` (confirmed present, 5 problems, all gold). The final measurement dataset (MATH500 full vs AIME/HMMT) is **Harman's call** — do not decide here.
- **SFT-data hygiene (future, not now):** AIME26 / HMMT *test* generations must **not** be used as SFT training data. If a Percy-aligned SFT is run later, training data should come from OpenThoughts-style *unlabeled* seed questions, with AIME/HMMT held out strictly for evaluation. Recorded here so the boundary isn't lost; Node 2 runs no SFT.

## 8. What waits for Node 1 (blocking)

1. Node 1 runs the **loop=2** SqueezeEvolve smoke (≤ loop 5 ceiling; "start with loop 2") and produces the normalized SE output + `<output>.raw.json` + preserved `<output>.checkpoints/` + `metrics.json`.
2. From those, recover real per-problem `N_i` (T0) and flip `se_budget` `UNKNOWN → FROM_RAW_METRICS` (§4 code update).
3. Only then are T3 (compute-matched rollouts) and T4 (reachability) valid. Until then Node 2 stays at prep + plumbing.
4. Confirm Node 1's exact output paths (shared FS) before T4/T0 — read-only.

## 8b. Evaluator fix — LaTeX-aware matching (2026-06-04)

Node 1's 1-problem loop=2 smoke surfaced a grader **undercount**: model output
`\boxed{(3, \frac{\pi}{2})}` vs gold `\left( 3, \frac{\pi}{2} \right)` — mathematically
equal, but exact-match scored it **wrong**.

**Fix (evaluation stack only), `src/tts_sft/answer_extraction.py`:**
- `normalize_math_answer` **unchanged** — keeps its gentle, display-preserving contract
  (`"(1, 2)"` stays `"(1, 2)"`; `eval_reachability` prediction display unaffected).
- New `latex_canonical()` + `_unwrap_boxed()`, used as a **third fallback inside
  `is_exact_match()`** (after normalized-equality and numeric-equality): strips
  `\left`/`\right`, unwraps a fully-`\boxed{}` answer, folds `\dfrac`/`\tfrac` → `\frac`,
  deletes LaTeX spacing commands (`\,` `\;` `\:` `\!` `\quad` `\qquad` `~` `\ `) and `$`,
  and removes all whitespace (non-semantic in LaTeX). It only ever **adds** matches;
  value-level differences stay distinct.
- `scripts/eval_reachability.py` and `metrics.py` **unchanged** — reachability grades via
  `is_exact_match` + `extract_final_answer`, so the fix propagates to the any-of-N
  categories automatically.

**Exact regression case (now passes):** `extract_final_answer("…\\boxed{(3, \\frac{\\pi}{2})}")`
→ `(3, \frac{\pi}{2})`; `is_exact_match("(3, \frac{\pi}{2})", "\left( 3, \frac{\pi}{2} \right)")`
→ **True** (both canonicalize to `(3,\frac{\pi}{2})`). Sanity: `(3,…)` vs `(4,…)` → **False**.

**Tests:** `python -m pytest -q` → **107 passed**. New: `TestLatexAwareMatching` (7 cases:
Node 1 case, `\left`/`\right`, internal whitespace, `\,` thin space, `\dfrac`→`\frac`,
different-tuple-still-wrong, normalizer-contract-unchanged) + `test_eval_reachability.py::
test_latex_equivalent_tuple_counts_as_solved` (end-to-end: the boxed tuple now scores
`only_se_solved`).

**`math_verify`:** NOT installed; per instructions no heavy dep added. String canonicalization
covers formatting equivalence (`\left`/`\right`, spacing, boxed, whitespace) but **NOT** symbolic
equivalence (`1/2` vs `0.5`, algebraic rearrangement, set/interval reordering). Add `math_verify`
later as an optional stronger checker if harder formats undercount.

⚠️ **Reachability numbers must use this corrected evaluator.** Any counts produced before this
fix would undercount solves (especially formatting-heavy answers). No reachability run has
happened yet (still blocked on Node 1's `N_i`), so there is nothing to re-grade.

## 8c. Matched independent arm + reachability pilot — RESULT (2026-06-04)

First reachability number (`RESULT-DEPENDENT`). Ran the compute-matched independent arm for
Node 1's 5-problem AIME25 pilot, then the comparison.

**Method.** N=32 independent rollouts/problem (matched to Node 1's recovered `N_i=32`), decoding
**matched to Node 1 exactly**: `temperature=0.6, top_p=0.95, max_tokens=32768`, per-sample seed
`1234+i`, standard math prompt. To use all 8 GPUs, brought up 8 single-GPU vLLM replicas (GPU0–7;
ports 8001 + 8010–8016) and ran a new concurrent round-robin driver
`scripts/run_independent_rollouts_dp.py` (same prompt/seed/params and **identical output schema**
as `run_independent_rollouts.py`). 160 generations finished in ~12 min at ~92% util on all 8 GPUs
(~5.8k tok/s aggregate). Extra 7 replicas torn down afterward; 8001/GPU7 retained.

**Reachability (corrected evaluator §8b, any-of-N):**

| category | count | ids |
|---|---|---|
| both_solved | **5** | aime25-000000…4 |
| only_se_solved | 0 | — |
| only_independent_solved | 0 | — |
| neither_solved | 0 | — |

SE any-of-16 solved 5/5; independent any-of-32 solved 5/5.

**Reading (no overclaim).** On this tiny pilot, matched-budget independent sampling reaches the
same solutions as SqueezeEvolve on all 5 → **no reachability gap observed** (ceiling: these AIME25
problems are within reach of Qwen3-4B-Thinking at N=32). It neither supports nor refutes the sharp
claim — it's a 5-problem plumbing pilot, not evidence. Caveats: (1) SE judged on its **16
final-population** candidates vs independent **32** (the full 32 SE generations live in
`loop_candidates.jsonl`; a symmetric 32-vs-32 comparison would need reshaping that file) — moot
here since both arms are at ceiling; (2) AIME integer answers, so the LaTeX fix wasn't decisive
though it was active; (3) a real signal needs a larger/harder set.

**Files produced:**
- `outputs/node2_independent_loop2_matched/independent_aime25_pilot5_N32.jsonl` (5 × 32 full responses)
- `outputs/node2_reachability_loop2/reachability_aime25_pilot5_N32.per_problem.jsonl`
- `outputs/node2_reachability_loop2/reachability_aime25_pilot5_N32.summary.json`
- `scripts/run_independent_rollouts_dp.py` (new 8-GPU concurrent driver)

## 8d. Symmetric SE-all-32 vs independent-32 — PRIMARY reachability metric (2026-06-04)

Per Harman, the compute-matched PRIMARY metric judges SE over ALL its generations (loop0 16 +
loop1 16 = 32/problem), not just the final-16 population. Reshaped Node 1's `loop_candidates.jsonl`
into the per-problem `candidates[]` schema with a new tested tool
`scripts/group_se_loop_candidates.py`, then re-ran `eval_reachability.py` (no `--se-budget-jsonl`,
so `se_num_candidates`=32). **No new generation** — pure offline reshaping + grading.

Grouping: 160 candidate rows → 5 problems × **32 candidates (16 loop0 + 16 loop1)**, all complete.

| category | SE-all-32 vs ind-32 (PRIMARY) | SE-final-16 vs ind-32 (§8c, secondary) |
|---|---|---|
| both_solved | **5** | 5 |
| only_se_solved | 0 | 0 |
| only_independent_solved | 0 | 0 |
| neither_solved | 0 | 0 |

SE-all-32 solved 5/5; independent-32 solved 5/5. **Same conclusion as final-16 — no reachability
gap on this pilot (both arms at ceiling).** Using SE's full 32 generations did not change the
result. §8c caveats stand (5-problem sample, integer answers, larger/harder set needed for signal).

Derived artifacts (Node 2 dirs only; Node 1 raw outputs untouched):
- `outputs/node2_reachability_loop2/se_all_candidates_aime25_pilot5_N32.jsonl` (reshaped SE, 5×32)
- `outputs/node2_reachability_loop2/reachability_aime25_pilot5_SEall32_vs_ind32.{per_problem.jsonl,summary.json}`
- `scripts/group_se_loop_candidates.py` + `tests/test_group_se_loop_candidates.py` (5 tests; suite 112 pass)

## 8e. Difficulty calibration (N=8, independent only) — 2026-06-05

Calibrated AIME25 remaining-25 + HMMT25 all-30 (**55 problems**) at N=8, matched decoding
(0.6/0.95/32768), to pick an informative subset for the formal SE-vs-independent run. Ran on the
8-GPU fleet via `run_independent_rollouts_dp.py`. New tested tool: `scripts/calibrate_difficulty.py`
(+ `tests/test_calibrate_difficulty.py`). **One mid-run fix:** hard problems generate to the 32768
cap; at concurrency 64 those exceeded the 600s client timeout and thrashed (retries). Killed,
added `--request-timeout` (→1800s) and lowered concurrency (→32), **resumed** (no data lost), 0
retries thereafter.

Buckets (easy ≥6/8, medium 1–5/8, hard 0/8):

| set | easy | medium | hard | total |
|---|---|---|---|---|
| AIME25 (rest-25) | 18 | 3 | 4 | 25 |
| HMMT25 (all-30) | 13 | 10 | 7 | 30 |
| **combined** | **31** | **13** | **11** | **55** |

**Recommended subset** (`recommended_reachability_subset.jsonl`): **20 problems = 11 hard + 9 medium**
(7 AIME + 13 HMMT), least-saturated-first.

⚠️ **Saturation caveat for the formal N=32 budget:** the medium problems here (1–3/8 at N=8) will
largely **saturate** for independent at N=32 (any-of-32 ≈ 1) → both_solved, not discriminating. The
reachability signal will come from the **11 hard (0/8)** problems. Several hard ones are **cap-bound**
(hit the 32768 cap on most/all samples → never finish → can't answer): `aime25-000013/000027`,
`hmmt25-000028` (8/8 cap). Those risk `neither_solved` unless SE's recombination finds a shorter
correct path; the "finishes-but-wrong" hard ones (low cap-hit, e.g. `hmmt25-000017/000018/000019`,
`hmmt25-000005/000007`) are cleaner reachability tests. **Confirm with Harman:** keep 32768, raise it
for cap-bound problems, or drop pure cap-bound ones. Several HMMT golds are non-integer
(`\frac`, `\sqrt`, `2^{25}`) → grader-format-sensitive (the §8b LaTeX fix is active).

Files: `outputs/node2_calibration/{calibration_summary_N8.jsonl, calibration_buckets_N8.json,
recommended_reachability_subset.jsonl, aime25_independent_N8.jsonl, hmmt25_independent_N8.jsonl}`
(+ AIME-only interim `aime25_calibration_{summary.jsonl,buckets.json}`). N=16 still on hold.

## 8f. Overnight matched-independent run + reachability evals — RESULT (2026-06-05)

Stages A/B/C (independent N=32/32/48 on the hard reachability subset) across the 8-GPU fleet, then
Stage D reachability evals vs Node 1's SE outputs. Generation ~5.5h (05:32–11:05), 1600 rollouts,
**0 retries / 0 failures** (calibration-era timeout fix held: `--request-timeout 1800`, concurrency 48).
Node 1 budgets **confirmed**: SE loop_candidates = 32/problem (loops=2: 16+16) and 48/problem
(loops=3: 16+16+16) → matches N=32 / N=48. Per-problem sample counts all complete (7×32, 13×32, 20×48).

Reachability (corrected evaluator §8b, SE-all-N vs independent-N, matched budget):

| eval | both | only_se | only_ind | neither | SE any-of-N | ind any-of-N |
|---|---|---|---|---|---|---|
| AIME hardtail7, loops=2, N=32 | 3 | 1 | 0 | 3 | 4/7 | 3/7 |
| HMMT13, loops=2, N=32 | 6 | 0 | 1 | 6 | 6/13 | 7/13 |
| **loop2 combined (20)** | **9** | **1** | **1** | **9** | **10/20** | **10/20** |
| full20, loops=3, N=48 | 10 | 0 | 2 | 8 | 10/20 | 12/20 |

> **Correction (2026-06-05):** an earlier text report mis-stated the loop2-combined any-of-N as
> `13/20` & `14/20` — a transcription error, **not** a different metric (no metric reproduces 13/14:
> #problems with ≥1 SE answer = 20; summed correct-counts = SE 102 / ind 47). Recomputed directly
> from the `*.per_problem.jsonl` files it is **SE 10/20, independent 10/20**. All four rows now
> satisfy: total = both+only_se+only_ind+neither, SE_any = both+only_se, ind_any = both+only_ind
> (assertions pass).

**Headline (`RESULT-DEPENDENT`):** at matched compute on this hard subset, SqueezeEvolve does **NOT
expand the reachable solution SET** — categorical reachability is neutral→slightly-negative (only_se
1→0, only_ind 1→2), and the few only_X outcomes are tail effects (1–5/N solve rates that flip with
more samples; e.g. loop2's only_se `aime25-000029` became both at N=48). The sharp "reaches what
independent cannot at matched compute" claim is **not supported** here. BUT SE shows a robust **DEPTH**
edge: on co-solved problems it solves ~**1.8×** more often (loop3 mean 14.5/48 vs 8.0/48; SE>ind on
8/10 co-solved; consistent at loop2). All 8 `neither` are hard/cap-bound (budget ceiling, not
reachability). Implication for self-distillation: SE's value is likely **higher yield of correct
traces**, not novel reach — worth testing directly in the SFT stage.

Files: `outputs/node2_independent_loop2_matched/*`, `outputs/node2_independent_loop3_matched/*`,
`outputs/node2_reachability_loop2/*`, `outputs/node2_reachability_loop3/*`.

## 8g. N=64 (loops-4 budget) independent run — DONE; matched eval PENDING (2026-06-05)

Ran full20 independent at **N=64** (loops-4 budget = 16×4) on the 8-GPU fleet (17:35→21:57, ~4.4h,
1280 rollouts, **0 retries/0 failures**, `--request-timeout 1800`, concurrency 48). Output:
`outputs/node2_independent_loop4_matched/independent_reachability20_N64.jsonl` (20×64 verified).
7 extra GPUs freed; 8001/GPU0 retained.

**Matched SE-vs-independent eval is BLOCKED** — Node 1's `outputs/node1_se_loop4_reachability20/*.loop_candidates.jsonl`
not yet present (loops=4 SE). Will run SE-all-64 vs independent-64 (with identity assertions) when it lands.

**Interim independent-only (N=64):** any-of-64 = **11/20** (9 medium + 2 hard: `aime25-000027`,
`hmmt25-000028`); the **9 hard-core problems stay 0/64**. Independent reach ladder: N=32→10, N=48→12,
N=64→**11** /20 — non-monotonic because runs are **independent re-draws, not nested** (vLLM concurrent
batching is numerically nondeterministic at fixed seed). E.g. `aime25-000013` (hard) was 1/48 at N=48
(`only_ind` there) but 0/64 here — confirming the `only_X` outcomes are **tail noise** at ~1–2/N rates.
Independent reach plateaus ~11–12/20; the hard core is unreachable at any tested budget. Reinforces:
no robust reachability gap; SE's edge is depth.

## 8h. N=64/N=80 matched evals on the 10-hard subset — DONE; experiment complete (2026-06-06)

N=64 (loops-4) and N=80 (loops-5) independent runs on full20 completed (~4.4h, ~5.5h; 0 failures).
Node 1 produced SE for these budgets under `node1_se_loop{4,5}_unsolved10/` — scoped to the **10
hardest problems** (9 hard-core `neither` + `hmmt25-000024`), N_i confirmed 64 (16×4) / 80 (16×5).
Matched evals (SE-all-N vs independent-N, intersect = those 10; assertions pass):

| eval | both | only_se | only_ind | neither | SE_any | ind_any |
|---|---|---|---|---|---|---|
| N=64 loops-4, 10-hard | 0 | **0** | 1 | 9 | 0/10 | 1/10 |
| N=80 loops-5, 10-hard | 1 | **0** | 0 | 9 | 1/10 | 1/10 |

**Conclusion:** SqueezeEvolve solved **0** problems independent could not, at every budget incl. the
loops-5 ceiling on the hardest subset. The 9 hard-core are `neither` for both (cap-bound). `only_se`=0
everywhere except loops-2 (tail noise → `both` at N=48). Reachability hypothesis **not supported**;
SE's edge is depth, not reach. Headline numbers + full detail in `docs/REACHABILITY_RESULTS.md`.
Files: `outputs/node2_reachability_loop4/reach_unsolved10_SEall64_vs_ind64.*`,
`outputs/node2_reachability_loop5/reach_unsolved10_SEall80_vs_ind80.*`.

## 8i. Length probe — max_tokens confound (2026-06-06)

BoN-only diagnostic (Harman's concern that the 32768 cap truncated the hard tail). Re-ran independent
sampling on the 11 hardest problems at **max_tokens=65536** (`max_model_len=131072`, top_k=20 preserved):
Phase 1 N=8 + Phase 2 N=16. New tool path: existing `run_independent_rollouts_dp.py`; seed
`data/seeds/length_probe_hard11.jsonl`; outputs `outputs/node2_length_probe/independent_hard11_N{8,16}_max65536.jsonl`.

Findings: the 32768 cap **was** truncating all 11 (cap-hit 32–96% @32k → 0% @64k; final-answer 100% @64k).
Two regimes: **2 controls truncation-limited & now solve** (`aime25-000027` 9/16, `hmmt25-000028` 6/16 @64k,
vs ~6% @32k); **9 hard-core capability-limited** (still 0/16 @64k — complete-but-wrong). So the earlier
hard-tail "neither" was a context-length artifact for the cap, but the 9 are model-capability-bound.

max_tokens sizing (from 176 N=16 samples): correct traces reach **55,247 tok**; p95≈50.7k, max 62,977.
→ 49152 clips ~half control solves (unsafe); 52000 abandons 0 problems but clips 3/15 correct samples
(undercounts rate); **65536 captures all observed correct traces — use it.** SE long-context rec: **(B)
max_tokens=65536, k=2, strip_think=false, max_model_len=262144**. Full detail in REACHABILITY_RESULTS.md §5b.
8-GPU 131072 probe fleet freed after.

## 8j. Saturated-easy calibration (N=16, temp=1.0) — 2026-06-07

Calibrated full AIME(30)+HMMT(30) BoN at N=16/temp1.0/32k (new `scripts/calib_bon_dp.py`, logs tokens+finish_reason).
Buckets — AIME: saturated 12 / informative 15 / hard_zero 0 / bad 3; HMMT: saturated 9 / informative 12 /
hard_zero 3 / bad 6. **non_saturated default: AIME 18, HMMT 21.** cap-hit 21%/26% → the 0-correct buckets are
truncation-confounded at 32k (see REACHABILITY_RESULTS §5c); saturated removal is clean. Filtered files under
`data/filtered/`. One transient: the first launch was killed externally at 96/480 (not RAM/code — 1.17TB free,
servers stayed up); resumed cleanly. All GPUs freed after.

## 9. Confirmation

**No SqueezeEvolve, SFT, or RL was run at any point. No Node 1 config/output was modified.**
Node 2 history: installed `pytest`; created Node-2 output dirs; stood up Node 2 vLLM (§1b); fixed
the math evaluator (§8b, code + tests only); ran the compute-matched independent-sampling arm
(§8c) across an 8-GPU vLLM fleet once authorized (Node-2 endpoints only; Node 1 files read-only)
plus the offline reachability comparison; and reshaped SE loop-candidates to run the symmetric
SE-all-32 vs independent-32 comparison (§8d, offline, no new generation). The 7 extra replicas were
torn down; 8001/GPU7 retained. All result claims remain `RESULT-DEPENDENT`.
