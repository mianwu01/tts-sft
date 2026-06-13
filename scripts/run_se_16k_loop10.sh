#!/usr/bin/env bash
# 16k / loop=10 SE run for node3/node4 (each 8xA100). Same formal setting EXCEPT
# max_tokens=16384 and loops=10 (=> N_i = population*loops = 160 generations/problem).
# update=replace, fitness=diversity, verifier-free, temp=1.0, top_k=20. Outputs are
# NODE-scoped so node3/node4 (shared /mnt/cpfs) never clobber each other or node1.
#
# Usage:  bash scripts/run_se_16k_loop10.sh <node3|node4> <strip:true|false> <ds...>
#   e.g.  node3:  bash scripts/run_se_16k_loop10.sh node3 false lcbv6
#         node4:  bash scripts/run_se_16k_loop10.sh node4 false aime hmmt
# Prereqs on THIS node: SE client pip-installed into this node's python; vLLM serving
# Qwen3-4B-Thinking-2507 on localhost:8000 (TP8, max_model_len 131072 is enough at 16k).
set -u
NODE="${1:?usage: run_se_16k_loop10.sh <node3|node4> <true|false> <ds...>}"; shift
STRIP="${1:?strip true|false}"; shift
DATASETS="$*"; [ -n "$DATASETS" ] || { echo "give >=1 dataset: aime hmmt lcbv6"; exit 2; }
TAG="${NODE}_loop10_16k_strip${STRIP}"
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache
export PYTHONINTMAXSTRDIGITS=0   # code-path int() safety net (see common.py guard)

declare -A RECOMB=( [aime]=aime25-aggregate [hmmt]=hmmt25-aggregate [lcbv6]=livecodebench-aggregate )
declare -A EVAL=( [aime]=aime25-none [hmmt]=hmmt25-none [lcbv6]=livecodebench-none )
declare -A TASK=( [aime]=math [hmmt]=math [lcbv6]=code )

run_one () {
  local ds=$1
  local odir=outputs/${TAG}_${ds}_non_saturated
  local run=tts_sft_se_${TAG}_${ds}_non_saturated
  local cfg=configs/squeeze_evolve_${TAG}_${ds}_non_saturated.yaml
  local out=$odir/se.jsonl
  cat > $cfg <<EOF
# ${NODE} 16k/loop10 SE. loops=10, max_tokens=16384, update=replace, fitness=diversity,
# strip_think=${STRIP}, temp=1.0, top_k=20, verifier-free. N_i=160. Serve vLLM TP8 (>=131072).
run_name: ${run}
routing:
  k: 4
  population: 16
  groups: 16
  loops: 10
  confidence_percentiles: []
  fitness: diversity
  selection: uniform
  selection_temperature: 1.0
  update: replace
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
    max_tokens: 16384
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
  echo "================ $(date '+%F %T')  START $ds ($TAG) ================"
  rm -rf external/squeeze-evolve/$odir 2>/dev/null
  mkdir -p $odir
  python scripts/run_squeeze_evolve.py \
    --input  data/filtered/${ds}_non_saturated.jsonl \
    --output $out --config $cfg \
    --squeeze-evolve-dir external/squeeze-evolve \
    --model Qwen/Qwen3-4B-Thinking-2507 \
    --base-url http://localhost:8000/v1 --api-key EMPTY
  local rc=$?
  if [ $rc -ne 0 ]; then echo "$ds FAILED rc=$rc (no retry)"; return $rc; fi
  python scripts/se_loop_candidates.py \
    --checkpoint-dir $out.checkpoints --se-output $out \
    --output $out.loop_candidates.jsonl
  echo "================ $(date '+%F %T')  DONE $ds ================"
}

for ds in $DATASETS; do run_one $ds || echo "continuing after $ds failure"; done
echo "================ $(date '+%F %T')  $TAG ALL ATTEMPTED ================"
