# NODE3 / NODE4 handoff — 16k / loop=10 SE runs

**Read this first.** You are a fresh Claude Code session on **node3 or node4** (each 8×A100-80GB),
sharing the same `/mnt/cpfs` as node1/node2. Goal: run **verifier-free SqueezeEvolve at
`max_tokens=16384`, `loops=10`** on the calibrated `non_saturated` subsets. The project's
`CLAUDE.md` (repo root) and the persistent memory index auto-load — skim those + this doc.

## TL;DR — one command, no Claude needed
The whole pipeline (install SE client → serve vLLM if not up → wait for health → generate →
grade) is a single idempotent script. Just run on the target node:
```bash
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
nohup bash scripts/node_pipeline.sh node3 false lcbv6     > /tmp/node3_pipeline.log 2>&1 &   # node3
nohup bash scripts/node_pipeline.sh node4 false aime hmmt > /tmp/node4_pipeline.log 2>&1 &   # node4
```
Watch: `tail -f /tmp/node4_pipeline.log`. Results land in `outputs/<node>_loop10_16k_stripfalse_*/summary.json`.
Re-runnable: it reuses an already-healthy vLLM and skips re-install. Sections below explain the pieces.

## 0. Onboarding in 60 seconds (shared FS)
- Repo: `/mnt/cpfs/yangboxue/opsd/TTS/tts-sft` (the real codebase; don't reinvent).
- Persistent memory: `…/claude_persist/config/projects/-mnt-cpfs-yangboxue-opsd-TTS/memory/MEMORY.md`
  (index → per-fact files). Read it; it has every env quirk and result so far.
- Key prior docs: `docs/NODE1_SE_NON_SATURATED_RESULTS.md` (formal SE replace, loops=5),
  `docs/NODE1_LCBV6_CALIBRATION.md`, `docs/NODE2_BON_NON_SATURATED_RESULTS.md` (the BoN arm).
- Model weights already cached (shared): `…/TTS/hf_cache/hub/models--Qwen--Qwen3-4B-Thinking-2507`.
- Data already built (shared): `data/filtered/{aime,hmmt,lcbv6}_non_saturated.jsonl`
  (18 / 21 / 126 problems; LCBV6 records carry hidden `tests` for offline grading only).

## 1. What this experiment is (and is NOT) — important
We run the **SqueezeEvolve evolutionary aggregation loop** on a **single model** with
`fitness=diversity`, `selection=uniform`, `update=replace`, **verifier-free** (`evaluation=none`;
for code, gt/tests never enter SE — they're applied only in offline grading). This is the official
`squeeze-evolve` package (no reimplementation), but it is **NOT a full-paper replication**: the
paper's signature **confidence-based multi-tier compute routing ("the squeeze")** is absent (we
have one model, `fitness=diversity`, no `scoring_model`, no `vllm_extensions`/fork). So we measure
"does recombination+replace beat matched-compute BoN on one model," not the paper's routing.
The **vLLM fork is NOT required** for this setting (the confidence/scoring path is never invoked).

Results so far (loops=5, 32k): **no reachability gain vs BoN**; SE's only edge is **depth** (more
correct traces) on **math** (strip=true ~1.9–2.4× token-matched), **neutral on code** — on LCBV6
`update=replace` actually *loses* correct programs across loops (90→80). See the docs above.

## 2. The 16k/loop10 run — caveats baked in
- `N_i = population × loops = 16 × 10 = 160` generations/problem (≫ the loops=5 N=80 runs).
- **`loops=10` supersedes the earlier "do not exceed loop 5" ceiling** — that ceiling was for the
  node1 reachability phase; Harman explicitly requested loop10 here (2026-06-09).
- **16k truncation:** we measured that a 16k cap loses ~half of *math* loop-0 correct solutions
  (long reasoning). loop10 gives more shots but each capped at 16k — this is a deliberate
  different-budget point, not the 32k setting. Expect higher cap-hit on math; near-0 on code.
- **`max_model_len`:** at 16k, k=4 strip=false recombination prompts ≈ 4×16k + question ≈ 67k, so
  **131072 is plenty** (more KV/concurrency than 262144). Serve TP8 @ 131072.
- top_k=20 forced via `extra_body` (logged); temp=1.0, top_p=0.95 (formal-comparison setting).
- `strip_think` is a **choice** (true|false) — pass it to the launcher. strip=false = faithful full
  parent reasoning; strip=true = answers/code only (smaller prompts, more re-reasoning).

## 3. Per-node setup (do once on EACH machine — separate Python envs)
```bash
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
# (a) SE client into THIS node's python (source incl. our code-path int() fix is shared):
python -m pip install hatchling editables
python -m pip install -e "external/squeeze-evolve/.[dev]" --no-build-isolation
python -m pip install pytest   # if running tests
which squeeze-evolve-client && python -c "import squeeze_evolve"   # verify
# (b) serve vLLM TP8 (ModelScope image gotcha: must disable MS + point at the snapshot):
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache
SNAP=$HF_HOME/hub/models--Qwen--Qwen3-4B-Thinking-2507/snapshots/768f209d9ea81521153ed38c47d515654e938aea
nohup vllm serve "$SNAP" --host 0.0.0.0 --port 8000 \
  --served-model-name Qwen/Qwen3-4B-Thinking-2507 \
  --tensor-parallel-size 8 --max-model-len 131072 \
  --gpu-memory-utilization 0.90 --dtype bfloat16 > /tmp/${HOSTNAME}_vllm.log 2>&1 &
# health: curl -s localhost:8000/v1/models ; curl -s -o /dev/null -w '%{http_code}' localhost:8000/health
```
Gotchas (from memory): the box routes through a flaky `127.0.0.1:7897` proxy — **always unset
`*_proxy`** before HF/vLLM/openai calls (the OpenAI client otherwise tries the **SOCKS** proxy and
dies with `socksio not installed`). vLLM defaults to ModelScope on this image; the explicit snapshot
path + `VLLM_USE_MODELSCOPE=False` + `HF_HUB_OFFLINE=1` is required.

## 4. Launch the run — CONFIRMED ASSIGNMENT (Harman, 2026-06-09), strip=false
**node3 → LCBV6**, **node4 → AIME + HMMT**, all `strip_think=false`. Run on each node AFTER its own
vLLM is healthy (§3). Launch detached (these are ~15–20 h runs):
```bash
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
# ── on node3 ──
nohup bash scripts/run_se_16k_loop10.sh node3 false lcbv6     > /tmp/node3_run.log 2>&1 &
# ── on node4 ──
nohup bash scripts/run_se_16k_loop10.sh node4 false aime hmmt > /tmp/node4_run.log 2>&1 &
```
Outputs land in `outputs/<node>_loop10_16k_strip<bool>_<ds>_non_saturated/` (se.jsonl, raw.json,
checkpoints/ loops0-9, loop_candidates.jsonl). The launcher writes its own NODE-scoped config +
run_name, clears stale checkpoints, runs, and flattens. On any non-zero exit it stops that dataset
(no silent retry) — report the error (e.g. context overflow → exact problem/prompt_tokens).

## 5. Grade (offline; after each dataset)
```bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache
D=outputs/<node>_loop10_16k_strip<bool>_<ds>_non_saturated
python scripts/score_se_subset.py \
  --loop-candidates $D/se.jsonl.loop_candidates.jsonl \
  --seed data/filtered/<ds>_non_saturated.jsonl \
  --metrics-json external/squeeze-evolve/$D/metrics.json \
  --task <math|code> --dataset <ds>_<node>_16k_loop10 \
  --out-genlog $D/genlog.jsonl --out-perproblem $D/per_problem.jsonl --out-summary $D/summary.json
```
`score_se_subset.py` handles math (LaTeX exact-match) and code (hidden-test harness, same as
calibration). It emits SE-all/SE-final/per-loop solved + correct traces + derived per-candidate
tokens (authoritative per-loop tokens come from metrics.json).

## 6. Conventions (shared FS — do not break)
- **Own your namespace:** node3 uses `node3_*` paths/run_names, node4 `node4_*`. Never write into
  node1/node2 output dirs or the other node's. Don't edit shared default configs.
- The SE clone source is shared (incl. the code-path int() fix in `common.py`); each node installs
  it into its own interpreter (§3a). Don't modify the clone further without noting it.
- Write a per-node status doc (`docs/NODE3_STATUS.md` / `docs/NODE4_STATUS.md`) — don't rewrite
  shared docs.
- Hard rules still hold: no SFT/RL, no verifier/test feedback inside SE, official SE only.
