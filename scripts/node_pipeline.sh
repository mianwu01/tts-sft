#!/usr/bin/env bash
# Turnkey end-to-end pipeline for node3/node4 (16k/loop10 SE). One command does everything:
#   install SE client (idempotent) -> serve vLLM if not already up (idempotent) -> wait for
#   health -> generate+flatten (run_se_16k_loop10.sh) -> grade each dataset (score_se_subset.py).
# Node-scoped throughout (shared /mnt/cpfs safe; never clobbers other nodes/node1).
#
# Usage (run on the target node; detach for the multi-hour job):
#   nohup bash scripts/node_pipeline.sh node4 false aime hmmt > /tmp/node4_pipeline.log 2>&1 &
#   nohup bash scripts/node_pipeline.sh node3 false lcbv6     > /tmp/node3_pipeline.log 2>&1 &
set -u
NODE="${1:?usage: node_pipeline.sh <node3|node4> <strip:true|false> <ds...>}"; shift
STRIP="${1:?strip true|false}"; shift
DATASETS="$*"; [ -n "$DATASETS" ] || { echo "give >=1 dataset: aime hmmt lcbv6"; exit 2; }
TAG="${NODE}_loop10_16k_strip${STRIP}"
REPO=/mnt/cpfs/yangboxue/opsd/TTS/tts-sft
cd "$REPO"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache
export PYTHONINTMAXSTRDIGITS=0
SNAP=$HF_HOME/hub/models--Qwen--Qwen3-4B-Thinking-2507/snapshots/768f209d9ea81521153ed38c47d515654e938aea
say(){ echo "[$(date '+%F %T') $NODE] $*"; }

# ---- 1. SE client (idempotent) ----
if ! python -c "import squeeze_evolve" 2>/dev/null; then
  say "installing squeeze-evolve client into this node's python ..."
  python -m pip install -q hatchling editables || { say "pip hatchling failed"; exit 1; }
  python -m pip install -q -e "external/squeeze-evolve/.[dev]" --no-build-isolation || { say "SE editable install failed"; exit 1; }
fi
python -c "import squeeze_evolve" 2>/dev/null || { say "SE client import still failing — abort"; exit 1; }
command -v squeeze-evolve-client >/dev/null || { say "squeeze-evolve-client not on PATH — abort"; exit 1; }
say "SE client OK."

# ---- 2. vLLM (idempotent: reuse if already healthy, else launch + wait) ----
health(){ curl -s -o /dev/null -w '%{http_code}' --max-time 3 localhost:8000/health 2>/dev/null; }
if [ "$(health)" != "200" ]; then
  say "serving vLLM TP8 @ max_model_len 131072 (log /tmp/${NODE}_vllm.log) ..."
  nohup vllm serve "$SNAP" --host 0.0.0.0 --port 8000 \
    --served-model-name Qwen/Qwen3-4B-Thinking-2507 \
    --tensor-parallel-size 8 --max-model-len 131072 \
    --gpu-memory-utilization 0.90 --dtype bfloat16 > /tmp/${NODE}_vllm.log 2>&1 &
  for i in $(seq 1 120); do [ "$(health)" = "200" ] && break; sleep 10; done
fi
[ "$(health)" = "200" ] || { say "vLLM not healthy after wait — see /tmp/${NODE}_vllm.log"; exit 1; }
say "vLLM healthy: $(curl -s localhost:8000/v1/models | head -c 200)"

# ---- 3. generate + flatten (node-scoped; no clobber) ----
say "starting generation: datasets = $DATASETS (strip=$STRIP, loops=10, max_tokens=16384)"
bash scripts/run_se_16k_loop10.sh "$NODE" "$STRIP" $DATASETS

# ---- 4. grade each dataset offline ----
for ds in $DATASETS; do
  case "$ds" in lcbv6) task=code ;; *) task=math ;; esac
  D=outputs/${TAG}_${ds}_non_saturated
  LC=$D/se.jsonl.loop_candidates.jsonl
  if [ -f "$LC" ]; then
    say "grading $ds (task=$task) ..."
    python scripts/score_se_subset.py \
      --loop-candidates "$LC" \
      --seed "data/filtered/${ds}_non_saturated.jsonl" \
      --metrics-json "external/squeeze-evolve/$D/metrics.json" \
      --task "$task" --dataset "${ds}_${NODE}_16k_loop10" \
      --out-genlog "$D/genlog.jsonl" --out-perproblem "$D/per_problem.jsonl" \
      --out-summary "$D/summary.json" \
      && say "graded $ds -> $D/summary.json" || say "grading $ds FAILED (see above)"
  else
    say "SKIP grade $ds — no loop_candidates at $LC (generation failed? check log)"
  fi
done
say "PIPELINE COMPLETE — datasets attempted: $DATASETS. Summaries: outputs/${TAG}_*/summary.json"
