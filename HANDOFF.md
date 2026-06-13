# HANDOFF.md

Reachability-diagnostic prep, 2026-06-04. **No data generation was run; no model was called.**

## Repo path & docs
- Repo: `/mnt/cpfs/yangboxue/opsd/TTS/tts-sft/` (`github.com/mianwu01/tts-sft`).
- Official SqueezeEvolve cloned (non-recursive) at `external/squeeze-evolve/` (gitignored).
  Its `external/vllm` submodule was **not** fetched (SSH `git@` URL, heavy fork — install
  deferred; see "blocked").
- Diagnostic context docs live one level up at `/mnt/cpfs/yangboxue/opsd/TTS/`:
  `CLAUDE.md`, `repo-evidence-map.md`, `results-schema.md`. Work-tracking docs
  (`claim-ledger.md`, this file) live in the repo root.

## Files created / modified
New (untracked):
- `scripts/run_independent_rollouts.py` — Arm B: N independent rollouts/seed → `responses[]`.
- `scripts/se_budget.py` — recover per-problem rollout budget `N_i` (honest UNKNOWN when not derivable).
- `scripts/eval_reachability.py` — any-of-N SE-vs-independent comparison → 4 categories + summary.
- `tests/test_eval_reachability.py`, `tests/test_independent_rollouts.py`, `tests/test_se_budget.py`.
- `tests/fixtures/mock_se_outputs.jsonl`, `tests/fixtures/mock_independent_outputs.jsonl`.
- `claim-ledger.md`, `HANDOFF.md`.
- `data/seeds/math500_seed_smoke.jsonl` — 5-problem MATH500 smoke seed (data prep only, no model).
Modified (tracked): `GPU_RUNBOOK.md` ("Step 1" reachability section + seed-dataset prep commands, pre-generation checklist, exact-next-commands).
Untouched: `scripts/run_raw_generation.py` and all existing pipeline code (backward compatible).

## Dataset preparation status (2026-06-04)
- **MATH500 (local, ready).** Smoke seed **built & verified** with no model:
  `data/seeds/math500_seed_smoke.jsonl` (5 problems, schema `{id, question, answer}`, ids
  `math500-000000…`). The full 500-problem command is drafted and safe to run anytime; not run
  yet because the final dataset is pending Harman.
  - ⚠️ **Path correction:** MATH500 lives at
    `/mnt/cpfs/yangboxue/wujunyi/LightningRL/data/MATH500.json`. The path given earlier,
    `/mnt/cpfs/yangboxue/opsd/wujunyi/...` (extra `opsd/`), does **not** exist.
  - Exact command (drop `--limit 5` for the full set):
    ```bash
    python scripts/prepare_math_seed.py \
        --input  /mnt/cpfs/yangboxue/wujunyi/LightningRL/data/MATH500.json \
        --output data/seeds/math500_seed.jsonl \
        --question-field question --answer-field ground_truth_answer \
        --id-prefix math500- --require-answer
    ```
- **AIME-2025 / HMMT-2025 (placeholder).** Bundled with SqueezeEvolve as parquet
  (`external/squeeze-evolve/data/{aime25,hmmt25}/test.parquet`, 30 problems each, nested fields).
  Flatten-then-prepare commands are drafted in `GPU_RUNBOOK.md` → "Step 1"; **not run** (dataset TBD).
- **Reminder:** seed prep is data-only and done; **data generation remains blocked** until Harman
  confirms hyperparameters + dataset, and one tiny SqueezeEvolve smoke run defines the budget `N_i`.

## Tests / checks run
- `python -m pytest -q` → **87 passed in 0.65s**.
- `--help` exit 0 for `run_raw_generation.py`, `run_independent_rollouts.py`, `se_budget.py`, `eval_reachability.py`.
- `eval_reachability.py` on fixtures → `total=4 both=1 only_se=1 only_independent=1 neither=1`.
- `se_budget.py` on fixtures → 4 records, all `budget_status:"UNKNOWN"` (correct, by design).

## Safe to run now (no GPU/model/API)
The four `--help`s, the fixture-based `eval_reachability` command, `run_squeeze_evolve.py … --dry-run`,
and `pytest`. See GPU_RUNBOOK.md → "Step 1".

## Blocked / not done (by design)
- **No generation / SFT / RL / vLLM** — per instructions.
- **SqueezeEvolve not installed** (`pip install -e ".[dev]"`) and its vLLM submodule not fetched
  — needs the GPU box and SSH access; do on the H100 box.
- **Per-problem budget `N_i` UNKNOWN** → true compute-matching not yet valid (see claim-ledger #4).
- **Base model not downloaded.**
- **End-to-end SqueezeEvolve output schema** beyond `candidates` unverified (no run).

## Must wait for Harman
1. SqueezeEvolve full-run hyperparameters: `routing.population`, `routing.loops`, `routing.k`,
   `routing.fitness` (currently `TODO_HARMAN_CONFIRM`).
2. Pin SE `models` to the single base model `Qwen3-4B-Thinking-2507` for a fair comparison (confirm).
3. Fixed problem set (MATH500 vs AIME/HMMT) and size.
4. Compute-match unit (#generations vs token budget) and scoring rule (exact-match vs add `math_verify`).
5. Explicit go/no-go for data generation.

## Next three actions
1. **(Harman)** Get recommended SE hyperparameters; set them in
   `configs/squeeze_evolve_generation.yaml` (replace `TODO_HARMAN_CONFIRM`).
2. **(GPU box)** Install SqueezeEvolve + submodule, download the base model, start vLLM, build a
   small fixed answer-bearing seed set with `scripts/prepare_math_seed.py`.
3. **(Smoke, with Harman's OK)** Run SqueezeEvolve on a handful of problems **only** to inspect
   `…​.raw.json` / `metrics.json`, then teach `se_budget._extract_total_generations()` the real
   field so `N_i` becomes KNOWN — unblocking compute-matched Arm B.

## Exact message to send Harman before any full data generation
> Reachability-diagnostic scaffolding is ready in `tts-sft` — official SqueezeEvolve is cloned
> into `external/squeeze-evolve`, and I added `run_independent_rollouts.py`, `se_budget.py`, and
> `eval_reachability.py` (tests green, 87 passing; nothing generated yet). Before I launch any
> generation I need your friend's recommended SqueezeEvolve hyperparameters: `routing.population`,
> `routing.loops`, `routing.k`, and `fitness` (`diversity` works on stock vLLM; `confidence` needs
> the vLLM fork). Two design confirmations: (1) pin SqueezeEvolve to the single base model
> `Qwen3-4B-Thinking-2507` so the comparison isolates evolution vs. independent sampling; (2) the
> fixed problem set (MATH500 vs AIME/HMMT) and count. One caveat: SqueezeEvolve doesn't expose a
> per-problem total-rollout count, so I'd like to do ONE tiny smoke run (a handful of problems)
> purely to read its metrics and define the compute-matched budget `N_i` — OK to run that minimal
> smoke? I won't start full generation until you confirm the hyperparameters.

---

## 2026-06-04 — session 2 update (fresh box; verification + Node 1 safe prep)

**Still no model called; no generation/SFT/RL.** Ran on a new machine.

Done (safe, allowed):
- Env verified: **only `pytest` was missing** (system Python already has torch 2.6.0+cu124, transformers 4.55, trl/peft/accelerate/bitsandbytes/…). 8× A100-80GB. **97 tests pass** (was 87; +10 new SE tests). All 13 script `--help` exit 0.
- **Official SqueezeEvolve INSTALLED** (was clone-only): `pip install hatchling editables` → `pip install -e ".[dev]" --no-build-isolation` (Aliyun mirror SSL-flakes in pip build isolation). `squeeze-evolve-client` on PATH; `import squeeze_evolve` OK. No `external/vllm` needed for our `fitness: diversity` config.
- Wrapper `--dry-run` validated against the **real** client; CLI flags confirmed (`--config/--input/--output/--n-problems`).
- Config **validates under live `RunConfig`** (+ `aime25-aggregate`/`aime25-none` operators register).
- **Full MATH500 seed built** → `data/seeds/math500_seed.jsonl` (500 records).
- Verified the every-loop machinery offline (already on disk since session 1, not in the original HANDOFF body): `scripts/se_loop_candidates.py` + `_preserve_loop_checkpoints` in `run_squeeze_evolve.py` → on mock checkpoints yields 8 records across loops [0,1] with full schema (loop_index, full_response, thinking_trace, final_answer, parent lineage, fitness). Matches official SE source (`orchestrator.py:458`, `utils.py:22`).

Blocked / needs decision before any model-calling step:
1. **Loop semantics** — "start with loop 2" = `loops: 2` (count; SE → t∈{0,1}) or `loops: 3` (run through index 2)? Config is currently `loops: 4`. Confirm before editing.
2. Download base model `Qwen/Qwen3-4B-Thinking-2507` + start vLLM (consent — large download).
3. Harman: SE hyperparameters (population/loops/k/fitness) + explicit go for the tiny loop=2 smoke (which defines `N_i`).
