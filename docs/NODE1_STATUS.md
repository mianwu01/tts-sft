# NODE1_STATUS — Official SqueezeEvolve setup + loop=2 smoke prep

Node 1 role: **official SqueezeEvolve setup + loop=2 smoke/pilot preparation.**
Updated 2026-06-04. **No SqueezeEvolve generation was run. No model API was called.**
(Node 2's `docs/NODE2_STATUS.md` is owned by the other session — not modified here.)

---

## 1. Official SqueezeEvolve install — ✅ INSTALLED & VERIFIED

- Repo: `external/squeeze-evolve/` (git HEAD `ee5e6da`), cloned (non-recursive).
- Installed editable into the working interpreter (Python 3.11.11):
  - The documented `pip install -e ".[dev]"` **failed** in pip's build-isolation
    subprocess — the Aliyun PyPI mirror SSL-flakes (`SSL: UNEXPECTED_EOF`) while
    fetching the `hatchling` build backend.
  - **Workaround that succeeded:**
    ```bash
    cd external/squeeze-evolve
    python -m pip install hatchling editables
    python -m pip install -e ".[dev]" --no-build-isolation
    ```
- Verification:
  - `which squeeze-evolve-client` → `/usr/local/bin/squeeze-evolve-client`
  - `squeeze-evolve-client --help` → exit 0; flags `--config / --input / --output /
    --n-problems` (+ optional `--include-path`) — match `scripts/run_squeeze_evolve.py`.
  - `python -c "import squeeze_evolve"` → ok (from the editable clone).

## 2. Forked vLLM status — NOT fetched; NOT required for our run

- `external/squeeze-evolve/external/vllm` is **empty** (git submodule, SSH `git@` URL,
  not fetched).
- SE `pyproject.toml` has **no dependency** on this fork. The base
  `squeeze-evolve-client` installs and runs without it (client talks to a vLLM *server*
  over the OpenAI-compatible API; it does not import the fork for generation).
- **Does NOT block our run.** Our config uses `fitness: diversity`, which scores groups
  by unique-answer count and needs no `prompt_logprobs` / `vllm_extensions` / `scoring_model`.
  The fork is required **only** for `fitness: confidence`. → If we ever switch to
  `confidence`, we must fetch + build the fork (or set `prompt_logprobs` on the served model).
- Note: a **stock** `vllm` is already importable system-wide
  (`/usr/local/lib/python3.11/site-packages/vllm`) — usable later to *serve* the base model.

## 3. Loop interpretation — CONFIRMED: loops = 2 as a COUNT

- Harman: "start with loop 2; do not exceed loop 5; keep the option to continue 3/4/5."
- **Confirmed mapping:** `routing.loops = 2` (a count). SqueezeEvolve runs `range(loops)`
  → `loop_index` **t = 0 and t = 1** (`orchestrator.py:450-458`):
  - t=0 — initial population generation (no parents)
  - t=1 — one evolution / recombination step
- **Do NOT** use `loops = 3` for "up to index 2". **Do NOT** run loop > 2 now.
- To continue later: bump `loops` 3 → 4 → 5 (never above 5). Later option (Harman): SFT the
  model first, then re-run SqueezeEvolve for another 2–3 loops with the SFT'd model.

## 4. Config file created — separate, defaults untouched

- **`configs/squeeze_evolve_loop2_smoke.yaml`** (new). Default
  `configs/squeeze_evolve_generation.yaml` was **not** modified.
- Differs from the default only in: `run_name: tts_sft_se_loop2_smoke_node1`,
  `routing.loops: 2`, `checkpoint_dir: ./outputs/node1_se_loop2_smoke/checkpoints`,
  `metrics_path: ./outputs/node1_se_loop2_smoke/metrics.json`.
- Unique `run_name` + unique checkpoint/metrics paths ⇒ **no stale-checkpoint mixing**.
- Validated under SE's live `RunConfig` (`_discover_benchmarks()` + `load_run_config()`):
  loads cleanly, `loops == 2`, operators `aime25-aggregate` / `aime25-none` register.
- All other knobs (`population/groups/k=4`, `fitness: diversity`, `temperature 0.7`,
  `top_p 0.95`, `max_tokens 8192`) are existing **DEFAULTS — placeholders pending Harman**.

## 5. Every-loop saving — GUARANTEED in code (verified offline)

Harman: "save all candidates from every loop + full thinking traces + outputs at every
step + which loop they belong to." Two pieces, both `CODE-SUPPORTED`:

1. **Preserve per-loop checkpoints** — `scripts/run_squeeze_evolve.py`
   `_preserve_loop_checkpoints()` copies the official client's per-loop checkpoints
   `<checkpoint_dir>/<run_name>_loop<t>.json` → `<output>.checkpoints/`. SE writes one
   checkpoint per loop (incl. loop 0) with the FULL `ProblemState`
   (`orchestrator.py:458` → `save_checkpoint(..., {"problems":[s.__dict__...], "metrics":flat})`;
   file naming `utils.py:22`). The client's `--output` JSON keeps only the FINAL loop, so
   these checkpoints are the ONLY per-loop source.
2. **Flatten to per-candidate JSONL** — `scripts/se_loop_candidates.py` emits one record
   per candidate per loop. **Required-field coverage verified on the checkpoint fixture
   (all present):** `id`, `question`, `answer` (gold if available), `loop_index`,
   `candidate_id`, `full_response`, `thinking_trace`, `final_answer`,
   `parent_ids` / `parent_texts` (lineage), `fitness`, `score`, `routing_metadata`,
   `raw_candidate`. Fields SE doesn't expose (e.g. `score` under `diversity`, parents at
   loop 0) are honest `null`, never fabricated.

⚠️ Final guarantee that real per-loop checkpoints land in `<output>.checkpoints/` is
confirmed by code + SE source; it will be observed for real on the first smoke run.

## 6. Prepared loop=2 smoke command — ⛔ NOT LAUNCHED (needs explicit go)

Dry-run validated (command construction + patched config verified: client receives
`run_name=tts_sft_se_loop2_smoke_node1`, `loops=2`, `fitness=diversity`, node1 paths).

**Prerequisites before the (gated) real run:**
- vLLM serving `Qwen/Qwen3-4B-Thinking-2507` at `http://localhost:8000/v1`
  — ✅ **DONE: model downloaded + vLLM running & health-verified (see §9).**
- Harman's explicit go + confirmed SE hyperparameters — **still pending.**

**THE GATED COMMAND (run only after explicit confirmation — drop `--dry-run`):**
```bash
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
python scripts/run_squeeze_evolve.py \
    --input  data/seeds/math500_seed_smoke.jsonl \
    --output outputs/node1_se_loop2_smoke/se_loop2_smoke.jsonl \
    --config configs/squeeze_evolve_loop2_smoke.yaml \
    --squeeze-evolve-dir external/squeeze-evolve \
    --model Qwen/Qwen3-4B-Thinking-2507 \
    --base-url http://localhost:8000/v1 --api-key EMPTY \
    --n-problems 5            # 1–5 examples; use 1 for a minimal first touch
# (append --dry-run to re-verify command construction WITHOUT calling the model)
```

**Follow-up commands (run AFTER the smoke completes — no model, safe):**
```bash
# (a) Recover per-problem rollout budget N_i (token counts are in metrics; if budget_status
#     stays UNKNOWN, teach se_budget._extract_total_generations() the real field, then re-run)
python scripts/se_budget.py \
    --se-output    outputs/node1_se_loop2_smoke/se_loop2_smoke.jsonl \
    --raw-json     outputs/node1_se_loop2_smoke/se_loop2_smoke.jsonl.raw.json \
    --metrics-json external/squeeze-evolve/outputs/node1_se_loop2_smoke/metrics.json \
    --config       configs/squeeze_evolve_loop2_smoke.yaml \
    --output       outputs/node1_se_loop2_smoke/se_budget.jsonl

# (b) Flatten EVERY-LOOP candidates (the Harman dataset: all loops, full traces, metadata)
python scripts/se_loop_candidates.py \
    --checkpoint-dir outputs/node1_se_loop2_smoke/se_loop2_smoke.jsonl.checkpoints \
    --se-output      outputs/node1_se_loop2_smoke/se_loop2_smoke.jsonl \
    --config         configs/squeeze_evolve_loop2_smoke.yaml \
    --run-name       tts_sft_se_loop2_smoke_node1 \
    --output         outputs/node1_se_loop2_smoke/se_loop2_smoke.loop_candidates.jsonl
```

Expected artifacts after the smoke run:
- `outputs/node1_se_loop2_smoke/se_loop2_smoke.jsonl` — normalized (1 line/problem, final candidates)
- `…/se_loop2_smoke.jsonl.raw.json` — raw orchestrator JSON (final loop)
- `…/se_loop2_smoke.jsonl.checkpoints/tts_sft_se_loop2_smoke_node1_loop{0,1}.json` — per-loop snapshots
- `external/squeeze-evolve/outputs/node1_se_loop2_smoke/metrics.json` — per-loop metrics (token counts)

## 7. Safe checks run this session (no model)
- `python -m pytest -q` → **97 passed**.
- `--help` exit 0: `run_squeeze_evolve.py`, `se_loop_candidates.py`, `se_budget.py`
  (and all other scripts).
- SE wrapper `--dry-run` with the new config → exit 0; patched config verified.
- `se_loop_candidates.py` on checkpoint fixtures → 8 records, loops [0,1], all required fields.

## 8. What remains BLOCKED before actual generation
1. **Harman's explicit go** to launch the smoke run (notify-before-launch gate) +
   confirmed SE hyperparameters (`population/loops/k/fitness`, sampling, context length).
2. ~~Base model not downloaded and vLLM not serving.~~ ✅ **RESOLVED (see §9):** weights cached at
   `/mnt/cpfs/yangboxue/opsd/TTS/hf_cache`; vLLM serving on `:8000` (GPU 0), health-verified, idle.
3. **Per-problem budget `N_i` UNKNOWN** until the smoke `metrics.json` is inspected and
   `se_budget._extract_total_generations()` is taught the real field — only then is
   compute-matching (Node 2) valid.

## 9. Model serving environment — ✅ READY & health-verified (2026-06-04)

- **Weights downloaded** to the persistent shared cache `/mnt/cpfs/yangboxue/opsd/TTS/hf_cache`
  (7.6 GB, 3/3 safetensors shards, index complete). Download recipe (this box routes HTTP through a
  flaky proxy `127.0.0.1:7897` + HF's Xet backend is blocked): **unset `*_proxy`**,
  `HF_ENDPOINT=https://hf-mirror.com`, `HF_HUB_DISABLE_XET=1`.
- **This is a ModelScope DSW image** (`VLLM_USE_MODELSCOPE=True` by default). vLLM must be told NOT to
  use ModelScope (or pointed at the explicit local snapshot path) — otherwise it looks in
  `/mnt/workspace/.cache/modelscope/hub` and dies with "Cannot find any model weights".
- **vLLM running & healthy** (background; GPU 0; port 8000):
  - `GET /v1/models` → `Qwen/Qwen3-4B-Thinking-2507`, `max_model_len=16384`.
  - `GET /health` → `200`. Engine init ~115 s; GPU 0 ~74 GB reserved (KV cache), 0% util (idle).
  - **No `chat/completions` was called — no model output was generated.**

**Exact serve command (what is currently running):**
```bash
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export VLLM_USE_MODELSCOPE=False HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache \
       HF_HUB_OFFLINE=1 DO_NOT_TRACK=1 VLLM_NO_USAGE_STATS=1 CUDA_VISIBLE_DEVICES=0
SNAP=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache/hub/models--Qwen--Qwen3-4B-Thinking-2507/snapshots/768f209d9ea81521153ed38c47d515654e938aea
vllm serve "$SNAP" --host 0.0.0.0 --port 8000 \
    --served-model-name Qwen/Qwen3-4B-Thinking-2507 \
    --max-model-len 16384 --gpu-memory-utilization 0.90 --dtype bfloat16
```
Health check (no generation): `curl -s localhost:8000/v1/models` ; `curl -s -o /dev/null -w '%{http_code}' localhost:8000/health`.
Stop the server (frees GPU 0 while waiting for Harman): `pkill -f "vllm serve"`.

**Update: the gated 1-problem smoke in §6 has since been run (explicitly authorized) — see §10.
vLLM remains serving on `:8000`.**

## 10. Loop=2 SMOKE RESULT (1 problem) — ✅ SUCCESS (2026-06-04, authorized)

Ran the §6 command with `--n-problems 1` against the live vLLM. **Official SqueezeEvolve ran
end-to-end: 1 problem, 2 loops (loop_index 0 and 1).**

**Wrapper bugfix (required, applied):** `run_squeeze_evolve.py` passed a *relative* `--output` to the
client, which runs with `cwd=se_dir`, so the raw JSON landed inside the clone and the wrapper reported
"no output" (rc=4). Fixed by resolving the raw-output path to absolute. (Also fixed: `se_loop_candidates.py`
`split_thinking` now handles Qwen3-Thinking-2507's closing-tag-only output; `se_budget.py` now recovers
`N_i` from per-loop metrics — see below.) `pytest` → **99 passed** after all changes.

**Artifacts produced** (`outputs/node1_se_loop2_smoke/`):
- `se_loop2_smoke_n1.jsonl` — normalized (1 record; final population candidates = 4)
- `se_loop2_smoke_n1.jsonl.raw.json` — raw orchestrator JSON (run_id, **2 per-loop metrics**, problems[0])
- `se_loop2_smoke_n1.jsonl.checkpoints/tts_sft_se_loop2_smoke_node1_loop{0,1}.json` — per-loop snapshots
- `se_loop2_smoke_n1.jsonl.loop_candidates.jsonl` — flattened every-loop candidates (**8 records**)
- `se_budget.jsonl` — per-problem budget
- `external/squeeze-evolve/outputs/node1_se_loop2_smoke/metrics.json` — per-loop metrics (client cwd)

**Every-loop candidates (8 = loop0×4 + loop1×4):**
| field | status |
|---|---|
| loop_index | 0 and 1 ✓ |
| candidates / loop | 4 (loop 0) + 4 (loop 1) ✓ |
| full_response | 8/8 present (full output verbatim) ✓ |
| thinking_trace | 8/8 present ✓ (Qwen3-Thinking emits only closing `</think>`; full reasoning also in full_response) |
| final_answer | 8/8 extracted ✓ |
| parent_ids / parent_texts | loop 1 ✓ (e.g. `[3,0,2,1]`); loop 0 = null (no parents) ✓ |
| fitness | loop 1 ✓ (e.g. `1.0`); loop 0 = null ✓ |
| score | null (diversity fitness → no per-candidate confidence) — expected, not fabricated |
| routing_metadata | loop 1 ✓ (`route=model_0`); loop 0 = null ✓ |
| raw_candidate | 8/8 ✓ |

**Per-problem rollout budget `N_i` — RECOVERED = 8** (`budget_status=FROM_RAW_METRICS`). Source: per-loop
`metrics` expose `model_0_count` (loop0=4, loop1=4); `N_i = Σ(model_*_count + lite_count) / n_problems
= 8 / 1 = 8`. The **final population (4) is NOT the budget** — confirms the `n_candidates ≠ N_i`
distinction. `se_budget.py` was minimally updated to read these per-loop counts (was UNKNOWN). For
multi-problem runs this is the run-wide total / n_problems (uniform assumption; per-loop checkpoint
candidate counts can refine per-problem if budgets differ).

**→ For Node 2:** compute-matched independent rollouts use **N = 8** for this config (population 4 ×
loops 2). `se_budget.py` now flips `UNKNOWN → FROM_RAW_METRICS`, unblocking Node 2's T0/T3.

**Scoring caveat (Harman decision):** SE's internal eval reported `mean_acc=0.0`, but the model actually
**solved it** — it produced `\boxed{(3, \frac{\pi}{2})}` vs gold `\left( 3, \frac{\pi}{2} \right)`, a
pure LaTeX-formatting difference. This is exactly the exact-match-undercount risk; it argues for adding
`math_verify` (or `\left(\right)` normalization) before any reachability count. Not a smoke failure.

### Optional 5-problem smoke — ⛔ DO NOT RUN without explicit confirmation
```bash
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
rm -rf external/squeeze-evolve/outputs/node1_se_loop2_smoke   # avoid stale (run_name-scoped) checkpoint mixing
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache HF_HUB_OFFLINE=1 VLLM_USE_MODELSCOPE=False
python scripts/run_squeeze_evolve.py \
    --input data/seeds/math500_seed_smoke.jsonl \
    --output outputs/node1_se_loop2_smoke/se_loop2_smoke_n5.jsonl \
    --config configs/squeeze_evolve_loop2_smoke.yaml \
    --squeeze-evolve-dir external/squeeze-evolve \
    --model Qwen/Qwen3-4B-Thinking-2507 \
    --base-url http://localhost:8000/v1 --api-key EMPTY \
    --n-problems 5
# then: se_loop_candidates.py + se_budget.py on the *_n5 outputs (N_i = total / 5).
```

**Update: the authorized 5-problem reachability pilot has since been run — see §11.**

## 11. FORMAL REACHABILITY PILOT (AIME25 ×5) — ✅ SUCCESS (2026-06-04, authorized)

Config: `configs/squeeze_evolve_loop2_reachability_pilot.yaml` (separate; defaults/smoke untouched).
Params: loops=2, population=16, groups=16, k=4, fitness=diversity, temperature=**0.6**, top_p=0.95,
max_tokens=32768, strip_think=**false** (full-reasoning recombination — the faithful mechanism).
Served via **vLLM TP=8 @ max_model_len 131072** (all 8 GPUs; 27.7× concurrency). Dataset:
`data/seeds/aime25_seed_pilot5.jsonl` (first 5 of AIME25; gold answers). ~15.6 min, rc=0,
**no timeouts, no loop-1 overflow** (131072 held for k=4 full-reasoning recombination).

Loop 0: 80 candidates (5×16), 1.12M output tokens (~14k/candidate). Loop 1: 80 recombinations.

Artifacts (`outputs/node1_se_loop2_reachability_pilot/`): `…pilot.jsonl` (5 normalized, 16 final
candidates each), `…raw.json`, `…checkpoints/{loop0,loop1}.json`, `…loop_candidates.jsonl` (160),
`se_budget.jsonl`; `metrics.json` in the SE clone.

Every-loop candidates (160 = 80+80):
- loop_index 0/1 ✓; full_response 160/160 ✓; final_answer 160/160 ✓.
- thinking_trace 117/160 — the other 43 emitted **no closing `</think>`** (mostly short direct-answer
  generations, median ~2.2k chars; 42/43 still have `\boxed`); **full output preserved in
  full_response/raw_candidate regardless**.
- loop 1: parent_ids 80/80, fitness 80/80, routing_metadata 80/80 ✓; loop 0 lineage null ✓;
  score null (diversity → no per-candidate confidence) ✓.

**Per-problem budget N_i = 32 for all 5** (min=max=mean=32, `FROM_RAW_METRICS`): metrics
`model_0_count` = 80 (loop0) + 80 (loop1) = 160 / 5 = 32. Uniform.

**Grading (repo exact-match extractor, any-of-N over all 32 candidates/problem): 5/5 solved.**
Exact-match == lenient-integer == 5/5 → **no exact-match false negatives for AIME** (integer answers
are clean, unlike the MATH500 polar-coords smoke). ⚠️ The `0.0` in SE's run log is the **disabled
`aime25-none` evaluator's placeholder**, NOT real accuracy — ignore it. (These are the first/easier 5
AIME25 problems at pass@32, so 5/5 is plausible; a reachability *gap* vs independent sampling needs
harder problems and Node 2.)

**→ Node 2 (matched independent rollouts) — recommended command (N=32, MATCH temperature 0.6):**
```bash
python scripts/run_independent_rollouts.py \
    --input data/seeds/aime25_seed_pilot5.jsonl \
    --output outputs/node2_independent_loop2_matched/independent_aime25_pilot5_N32.jsonl \
    --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY \
    --n-samples 32 --temperature 0.6 --top-p 0.95 --max-tokens 32768 --seed 1234
```
then `eval_reachability.py` (SE vs independent, with `se_budget.jsonl`). vLLM TP8@131072 already
serves :8000 for Node 2. **Node 1 does NOT run this.** Deferred ablation: strip_think=true @ 40960.

**Reminder: pilot stopped at 5 problems / loops=2. Do NOT continue to loops 3/4/5, do NOT run Node 2
generation, do NOT start SFT without explicit confirmation.**

## 12. AIME25 HARD-TAIL MINI-PILOT (7 non-easy ids) — ✅ SUCCESS at 262144 (2026-06-05, authorized)

Goal: does SE full-reasoning recombination solve AIME problems where independent N=8 is weak/zero?
Seed `data/seeds/aime25_seed_hardtail7.jsonl` (ids 000009/12/13/14/19/27/29). Config
`configs/squeeze_evolve_loop2_aime25_hardtail7.yaml` (run_name `tts_sft_se_loop2_aime25_hardtail7_node1`);
same params as §11 (loops2/pop16/groups16/k4/diversity/temp0.6/top_p0.95/max_tokens32768/strip_think=false).

**Context-overflow finding (important):** at `max_model_len=131072` the run **crashed at loop 1** — these
hard problems maxed loop-0 traces (~31.8k tok), so k=4 full-reasoning recombination = **158,419 tokens >
131,072** (vLLM 400). SE does NOT skip over-length requests, and `resume` can't continue past loop 0 (it
regenerates loop 0). Fix: **re-ran the full pilot at vLLM TP=8 @ max_model_len 262144** (model native max);
rc=0, ~50 min (loop0 36m + loop1 13.6m), no overflow. First attempt's loop-0 salvage kept in
`outputs/node1_se_loop2_aime25_hardtail7_attempt1_loop0only/`.

Artifacts (`outputs/node1_se_loop2_aime25_hardtail7/`): `…pilot.jsonl` (7 normalized, 16 final each),
`…raw.json`, `…checkpoints/{loop0,loop1}.json`, `…loop_candidates.jsonl` (224), `se_budget.jsonl`.
Coverage (224=112+112): full_response 224/224 ✓; final_answer 173/224 (51 hit the 32768 cap before boxing —
full output still saved); thinking_trace 125/224; loop1 parent_ids 112/112, fitness 112/112 ✓.
**N_i = 32 for all 7** (FROM_RAW_METRICS).

**Results (repo exact-match, any-of-N):**
| problem | indep N=8 | loop0 | loop1 | SE-final(16) | SE-all(32) |
|---|---|---|---|---|---|
| 000009 | 1/8 | 4/16 | 10/16 | ✅ | ✅ |
| 000019 | 3/8 | 7/16 | 16/16 | ✅ | ✅ |
| 000027 | **0/8** | 1/16 | 3/16 | ✅ | ✅ |
| 000029 | 1/8 | 3/16 | 8/16 | ✅ | ✅ |
| 000012 | 0/8 | 0/16 | 0/16 | ✗ | ✗ |
| 000013 | 0/8 | 0/16 | 0/16 | ✗ | ✗ |
| 000014 | 0/8 | 0/16 | 0/16 | ✗ | ✗ |

- **SE-all 4/7; SE-final 4/7.** **1 of the four 0/8 problems (000027) solved by SE**; the three hardest
  (000012/13/14) remain unsolved at 32 samples (no correct parent → recombination can't help).
- **Loop-1 recombination concentrated correct solutions** where solvable (000019 7→16, 000009 4→10,
  000029 3→8, 000027 1→3) but reached no problem loop-0 had 0 on (loop0-alone 4/7 == loop1-alone 4/7). At
  loops=2 the evolutionary step amplified solution *density*, not raw reachability, on this set.
- ⚠️ **4/7 (SE, N=32) vs ~3/7 (independent, N=8) is NOT the matched comparison** (32 vs 8 samples). The real
  reachability claim needs independent **N=32** (Node 2).

**→ Node 2 matched command (N=32, temp 0.6) — recommendation, NOT run here:**
```bash
python scripts/run_independent_rollouts.py \
    --input data/seeds/aime25_seed_hardtail7.jsonl \
    --output outputs/node2_independent_loop2_matched/independent_aime25_hardtail7_N32.jsonl \
    --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY \
    --n-samples 32 --temperature 0.6 --top-p 0.95 --max-tokens 32768 --seed 1234
```
then `eval_reachability.py` (SE vs independent N=32, with `se_budget.jsonl`). vLLM TP8@**262144** now serves :8000.

**Reminder: hard-tail mini-pilot complete at loops=2. Do NOT continue to loops 3/4/5, do NOT run Node 2
generation, do NOT start SFT without explicit confirmation.**

## 13. OVERNIGHT — Stage A: HMMT13 SE loops=2 @262144 — ✅ SUCCESS (2026-06-05)

Pre-flight: vLLM relaunched **TP=8 @ max_model_len 262144** (/health 200, /v1/models 262144, all 8 GPUs).
Seeds built from Node 2's `outputs/node2_calibration/recommended_reachability_subset.jsonl` (authoritative
ids/golds): `data/seeds/hmmt25_seed_reachability13.jsonl` (13 HMMT, matches requested list) and
`data/seeds/reachability20_seed.jsonl` (20 = 7 AIME hardtail + 13 HMMT).

Stage A config `configs/squeeze_evolve_loop2_hmmt25_reachability13.yaml`
(run_name `tts_sft_se_loop2_hmmt25_reachability13_node1`): loops=2, pop16/groups16/k4/diversity/temp0.6/
top_p0.95/max_tokens32768, strip_think=false. **Runtime ~87 min** (loop0 64m + loop1 23m), rc=0,
**no overflow/timeout/schema errors**.

Artifacts (`outputs/node1_se_loop2_hmmt25_reachability13/`): `se.jsonl` (13 normalized, 16 final each),
`se.jsonl.raw.json`, `se.jsonl.checkpoints/{loop0,loop1}.json`, `se.jsonl.loop_candidates.jsonl` (416),
`se_budget.jsonl`; metrics.json in SE clone. Coverage (416=208+208): full_response 416/416; final_answer
356/416 (60 hit the 32768 cap); thinking_trace 271/416; loop1 parent_ids/fitness 208/208. **N_i=32 for all
13** (FROM_RAW_METRICS) — matches the verified budget rule.

**Results — SE-all 6/13, SE-final 6/13** (loop0-alone 4/13, loop1-alone 6/13). vs independent N=8: also 6/13 but DIFFERENT sets:
| id | bucket | indep N8 | SE l0 | SE l1 | SE-all | note |
|---|---|---|---|---|---|---|
| 000005 | medium | 2/8 | 6 | 5 | ✅ | |
| 000007 | medium | 2/8 | 8 | 10 | ✅ | |
| 000012 | medium | 1/8 | 0 | 2 | ✅ | recomb-NEW (loop1 reached) |
| 000014 | medium | 1/8 | 2 | 3 | ✅ | |
| 000023 | medium | 1/8 | 4 | 6 | ✅ | |
| 000028 | **hard** | **0/8** | 0 | 4 | ✅ | **recomb-NEW + SE>indepN8** |
| 000024 | medium | 1/8 | 0 | 0 | ✗ | indep solved, SE missed (variance) |
| 000013/16/17/18/19/29 | hard | 0/8 | 0 | 0 | ✗ | |

- **Loop-1 recombination reached 2 problems loop-0 missed** (000012, 000028) — genuine reachability signal.
- **hmmt25-000028 (hard, indep 0/8, SE loop0 0/16) reached ONLY by loop-1 recombination (4/16)** — strongest
  "evolutionary TTS reaches what independent sampling can't" candidate. ⚠️ Needs the **matched independent
  N=32** check (Node 2) to confirm — SE used N=32 vs the N=8 calibration.

**→ Node 2 matched (Stage A): N=32, temp 0.6:**
```bash
python scripts/run_independent_rollouts.py \
    --input data/seeds/hmmt25_seed_reachability13.jsonl \
    --output outputs/node2_independent_loop2_matched/independent_hmmt25_reachability13_N32.jsonl \
    --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY \
    --n-samples 32 --temperature 0.6 --top-p 0.95 --max-tokens 32768 --seed 1234
```

## 14. OVERNIGHT — Stage B: full20 SE loops=3 @262144 — ✅ SUCCESS (2026-06-05)

Config `configs/squeeze_evolve_loop3_reachability20.yaml` (run_name `tts_sft_se_loop3_reachability20_node1`),
seed `data/seeds/reachability20_seed.jsonl` (20 = 7 AIME hardtail + 13 HMMT). loops=3, same params as Stage A,
strip_think=false. **Runtime ~158 min** (loop0 102m + loop1 38m + loop2 18m), rc=0, **no overflow/timeout/schema**.

Artifacts (`outputs/node1_se_loop3_reachability20/`): `se.jsonl` (20 normalized, 16 final each), `se.jsonl.raw.json`,
`se.jsonl.checkpoints/{loop0,loop1,loop2}.json`, `se.jsonl.loop_candidates.jsonl` (960), `se_budget.jsonl`.
Candidates/loop: 320/320/320. Coverage: full_response 960/960; final_answer 865/960 (95 hit the 32768 cap);
thinking_trace 542/960; loop1&loop2 parent_ids/fitness 320/320. **N_i=48 for all 20** (FROM_RAW_METRICS).

**Results — SE-all 10/20, SE-final 8/20.** By dataset: **AIME 4/7, HMMT 6/13**. By bucket: **medium 8/9, hard 2/11**. Cap-bound problems (>50% candidates hit cap): 0/20.
- **new-at-loop2 = 0** — the third loop reached NO problem that loops 0+1 missed; it only deepened density
  (aime000009 4→10→12, aime000019 2→11→14, aime000027 0→4→9). **loops=3 gave NO reachability gain over loops=2**
  (identical 10/20 solved set to Stage A HMMT 6/13 + AIME hardtail 4/7 — reproducible).
- **Both hard problems SE solved (aime000027, hmmt000028; both indep 0/8) were first reached at loop 1
  (recombination), not initial sampling** — the reachability signal. The other 9 hard problems stayed 0/48.
- ⚠️ NOT compute-matched (SE N=48 vs indep N=8). Matched test = independent **N=48** (Node 2).

**→ Node 2 matched (Stage B): N=48, temp 0.6:**
```bash
python scripts/run_independent_rollouts.py \
    --input data/seeds/reachability20_seed.jsonl \
    --output outputs/node2_independent_loop3_matched/independent_reachability20_N48.jsonl \
    --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY \
    --n-samples 48 --temperature 0.6 --top-p 0.95 --max-tokens 32768 --seed 1234
```

**Overnight plan complete (Stage A + Stage B). Both passed; vLLM TP8@262144 still serving :8000. Did NOT run
loops 4/5, Node 2 generation, or SFT. Key takeaway: at this budget the reachability gain comes from loop-1
recombination (2 hard problems reached that initial sampling missed); loop 2 (loops=3) added density, not reach.**

## 15. loops=4 on the unsolved-10 — ✅ ran, solved 0/10 (2026-06-05)

Tests whether a 4th loop reaches any of the 10 problems SE-all missed at loops=3. Config
`configs/squeeze_evolve_loop4_unsolved10.yaml` (run_name `tts_sft_se_loop4_unsolved10_node1`), seed
`data/seeds/reachability_unsolved10_seed.jsonl` (aime000012/13/14 + hmmt000013/16/17/18/19/24/29). loops=4
(≤5 ceiling), strip_think=false, @262144. **~82 min, rc=0, no overflow.** **N_i=64 for all 10** (FROM_RAW_METRICS).
640 candidates (160/loop); full_response 640/640, final_answer 586/640, thinking_trace 349/640.

**Result: SE-all 0/10** — every loop (l0=l1=l2=l3=0) for all 10. The 4th loop cracked nothing; confirms the
diminishing-returns pattern (loops 2→3→4 add no reachability once no candidate is ever correct — recombination
has no correct ingredient to aggregate).
⚠️ **Grader caveat:** most of these 10 have complex-form golds (radicals/fractions/factorials, e.g.
`\sqrt{23}-2\sqrt{3}`, `\frac{448}{3}`, `2^{25}\cdot 26!`) where the repo's exact-match grader can undercount.
0/10 is a LOWER bound — a `math_verify`/symbolic recheck is advised before concluding these are truly unreached
(e.g. hmmt000024 was indep N=8 1/8 but SE 0/64 — variance or an exact-match miss on its radical gold).

Artifacts: `outputs/node1_se_loop4_unsolved10/` (se.jsonl, raw.json, checkpoints/{loop0-3}.json,
loop_candidates.jsonl, se_budget.jsonl).

## 16. loops=5 (CEILING) on the unsolved-10 — ✅ ran, solved 1/10 (2026-06-06)

Config `configs/squeeze_evolve_loop5_unsolved10.yaml`, seed `data/seeds/reachability_unsolved10_seed.jsonl`,
loops=5 (== ceiling), strip_think=false, @262144. ~88 min, rc=0, no overflow. **N_i=80 for all 10**
(FROM_RAW_METRICS). 800 candidates (160/loop); full_response 800/800, final_answer 752/800.
**SE-all 1/10** — only `hmmt25-000024` (l0=0 l1=5 l2=9 l3=11 l4=10). ⚠️ This is **run variance, not a
5th-loop effect**: the solve appears at **loop 1**, hmmt000024 is borderline (indep N=8 = 1/8), and it was
**0/64 in the loops=4 run**. The 9 truly-hard (indep 0/8) problems stayed **0/80**. Artifacts:
`outputs/node1_se_loop5_unsolved10/`. **Loop ceiling reached — will NOT run loops>5.**
Consolidated results: `docs/NODE1_REACHABILITY_RESULTS.md`.
