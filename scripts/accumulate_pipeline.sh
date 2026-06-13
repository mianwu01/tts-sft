#!/usr/bin/env bash
# Turnkey end-to-end pipeline for the update=ACCUMULATE variant (formal setting: loops=5,
# temp=1.0, max_tokens=32768, top_k=20, verifier-free, fitness=diversity). One command:
#   activate env -> install SE client (idempotent) -> serve vLLM TP8@262144 if not up
#   (idempotent) -> wait for health -> per dataset: generate+flatten+grade(--accumulate)
#   -> collect a consolidated report. Node-scoped (shared /mnt/cpfs safe; no clobber).
#
# update=accumulate keeps the population (16->80) but still does 16 NEW generations/loop,
# so N_i=80 (compute-matched to replace). Grading counts the 80 unique generations.
#
# Usage (run on the new machine; detach — multi-hour):
#   nohup bash scripts/accumulate_pipeline.sh node5 false aime hmmt > /tmp/node5_accum.log 2>&1 &
#   tail -f /tmp/node5_accum.log
set -u
NODE="${1:?usage: accumulate_pipeline.sh <node> <strip:true|false> <ds...>}"; shift
STRIP="${1:?strip true|false}"; shift
[ "$STRIP" = true ] || [ "$STRIP" = false ] || { echo "strip must be true|false"; exit 2; }
DATASETS="$*"; [ -n "$DATASETS" ] || { echo "give >=1 dataset: aime hmmt lcbv6"; exit 2; }
TAG="${NODE}_accum_loop5_32k_strip${STRIP}"
REPO=/mnt/cpfs/yangboxue/opsd/TTS/tts-sft
cd "$REPO" || { echo "repo not found at $REPO — is /mnt/cpfs/yangboxue/opsd mounted?"; exit 1; }
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache
export PYTHONINTMAXSTRDIGITS=0
SNAP=$HF_HOME/hub/models--Qwen--Qwen3-4B-Thinking-2507/snapshots/768f209d9ea81521153ed38c47d515654e938aea
say(){ echo "[$(date '+%F %T') $NODE] $*"; }

declare -A RECOMB=( [aime]=aime25-aggregate [hmmt]=hmmt25-aggregate [lcbv6]=livecodebench-aggregate )
declare -A EVAL=( [aime]=aime25-none [hmmt]=hmmt25-none [lcbv6]=livecodebench-none )
declare -A TASK=( [aime]=math [hmmt]=math [lcbv6]=code )

# ---- 1. environment / SE client (idempotent) ----
say "python: $(python -V 2>&1) @ $(command -v python)"
if ! python -c "import squeeze_evolve" 2>/dev/null; then
  say "installing SE client into this node's python ..."
  python -m pip install -q hatchling editables || { say "pip hatchling failed"; exit 1; }
  python -m pip install -q -e "external/squeeze-evolve/.[dev]" --no-build-isolation || { say "SE install failed"; exit 1; }
fi
python -c "import squeeze_evolve" 2>/dev/null && command -v squeeze-evolve-client >/dev/null \
  || { say "SE client not importable / not on PATH — abort"; exit 1; }
[ -f data/filtered/aime_non_saturated.jsonl ] || { say "data/filtered missing — shared FS not mounted?"; exit 1; }
say "env + SE client OK."

# ---- 2. vLLM TP8 @ 262144 (idempotent) ----
health(){ curl -s -o /dev/null -w '%{http_code}' --max-time 3 localhost:8000/health 2>/dev/null; }
if [ "$(health)" != "200" ]; then
  say "serving vLLM TP8 @ max_model_len 262144 (log /tmp/${NODE}_vllm.log) ..."
  nohup vllm serve "$SNAP" --host 0.0.0.0 --port 8000 \
    --served-model-name Qwen/Qwen3-4B-Thinking-2507 \
    --tensor-parallel-size 8 --max-model-len 262144 \
    --gpu-memory-utilization 0.90 --dtype bfloat16 > /tmp/${NODE}_vllm.log 2>&1 &
  for i in $(seq 1 150); do [ "$(health)" = "200" ] && break; sleep 10; done
fi
[ "$(health)" = "200" ] || { say "vLLM not healthy — see /tmp/${NODE}_vllm.log"; exit 1; }
say "vLLM healthy."

# ---- 3. per-dataset: generate + flatten + grade(accumulate) ----
gen_grade () {
  local ds=$1
  local odir=outputs/${TAG}_${ds}_non_saturated
  local cfg=configs/squeeze_evolve_${TAG}_${ds}_non_saturated.yaml
  local out=$odir/se.jsonl
  cat > "$cfg" <<EOF
# ${NODE} accumulate variant. loops=5, max_tokens=32768, update=ACCUMULATE, fitness=diversity,
# strip_think=${STRIP}, temp=1.0, top_k=20, verifier-free. N_i=80 (16 new/loop). TP8@262144.
run_name: tts_sft_se_${TAG}_${ds}_non_saturated
routing:
  k: 4
  population: 16
  groups: 16
  loops: 5
  confidence_percentiles: []
  fitness: diversity
  selection: uniform
  selection_temperature: 1.0
  update: accumulate
  lite_fraction: 0.0
  lite_method: majority
  recombination: ${RECOMB[$ds]}
  evaluation: ${EVAL[$ds]}
  task: ${TASK[$ds]}
  generation_batch_size: 48
  strip_think: ${STRIP}
  seed: 1234
models:
  - name: Qwen/Qwen3-4B-Thinking-2507
    base_url: http://localhost:8000/v1
    api_key: EMPTY
    endpoint: chat
    max_tokens: 32768
    temperature: 1.0
    top_p: 0.95
    max_concurrency: 48
    extra_body:
      top_k: 20
retry:
  request_timeout_seconds: 7200
resume: false
checkpoint_dir: ./${odir}/checkpoints
metrics_path: ./${odir}/metrics.json
EOF
  say "START $ds (accumulate, strip=$STRIP)"
  rm -rf "external/squeeze-evolve/$odir" 2>/dev/null
  mkdir -p "$odir"
  python scripts/run_squeeze_evolve.py \
    --input "data/filtered/${ds}_non_saturated.jsonl" \
    --output "$out" --config "$cfg" \
    --squeeze-evolve-dir external/squeeze-evolve \
    --model Qwen/Qwen3-4B-Thinking-2507 \
    --base-url http://localhost:8000/v1 --api-key EMPTY || { say "$ds GENERATION FAILED (no retry)"; return 1; }
  python scripts/se_loop_candidates.py \
    --checkpoint-dir "$out.checkpoints" --se-output "$out" \
    --output "$out.loop_candidates.jsonl" || { say "$ds flatten failed"; return 1; }
  say "grading $ds (accumulate-aware) ..."
  python scripts/score_se_subset.py \
    --loop-candidates "$out.loop_candidates.jsonl" \
    --seed "data/filtered/${ds}_non_saturated.jsonl" \
    --metrics-json "external/squeeze-evolve/$odir/metrics.json" \
    --task "${TASK[$ds]}" --dataset "${ds}_${TAG}" --accumulate --groups 16 \
    --out-genlog "$odir/genlog.jsonl" --out-perproblem "$odir/per_problem.jsonl" \
    --out-summary "$odir/summary.json" || { say "$ds grading failed"; return 1; }
  say "DONE $ds -> $odir/summary.json"
}

for ds in $DATASETS; do gen_grade "$ds" || say "continuing after $ds"; done

# ---- 4. collect consolidated report ----
REPORT=docs/${NODE}_ACCUMULATE_REPORT.md
python - "$TAG" "$REPORT" "$STRIP" $DATASETS <<'PY'
import json, sys
from pathlib import Path
tag, report, strip = sys.argv[1], sys.argv[2], sys.argv[3]
datasets = sys.argv[4:]
lines = [f"# {tag} — update=accumulate results (strip_think={strip})", "",
         "Verifier-free SE, loops=5, temp=1.0, top_k=20, max_tokens=32768, update=ACCUMULATE.",
         "N_i=80 (16 new generations/loop). Graded on the 80 UNIQUE generations.", "",
         "| dataset | SE-all solved | total correct traces | per-loop NEW-correct (0→4) |",
         "|---|---|---|---|"]
for ds in datasets:
    s = Path(f"outputs/{tag}_{ds}_non_saturated/summary.json")
    if not s.exists():
        lines.append(f"| {ds} | (missing — run failed) | — | — |"); continue
    d = json.loads(s.read_text())
    pl = d.get("per_loop", {})
    newc = [pl[k]["correct_candidates"] for k in sorted(pl, key=int)]
    lines.append(f"| {ds} | {d['se_all_solved']}/{d['n_problems']} | {d['total_correct_traces']} | {newc} |")
lines += ["", "Per-dataset detail: outputs/"+tag+"_<ds>_non_saturated/{summary.json,per_problem.jsonl,genlog.jsonl}.",
          "Note: SE-final == SE-all under accumulate (final population keeps all candidates); the",
          "meaningful per-loop metric is NEW-correct introduced per loop (shown above)."]
Path(report).write_text("\n".join(lines))
print("\n".join(lines))
PY
say "PIPELINE COMPLETE. Report: $REPORT . Per-dataset summaries: outputs/${TAG}_*/summary.json"
