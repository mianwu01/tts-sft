#!/usr/bin/env bash
# update=accumulate variant of the formal SE run. Same settings as the non_saturated
# formal runs EXCEPT update: accumulate (population grows 16->80; still 16 new generations
# per loop => N_i=80, compute-matched to the replace runs). strip_think chosen at runtime.
#
# Usage:  bash scripts/run_se_accumulate.sh <true|false>
# Order:  LCBV6 -> AIME -> HMMT  (per request). Runs on the shared TP8@262144 :8000 endpoint;
# launch only AFTER the current strip=true re-run has finished (GPUs free).
set -u
STRIP="${1:?usage: run_se_accumulate.sh <true|false>}"
[ "$STRIP" = "true" ] || [ "$STRIP" = "false" ] || { echo "strip must be true|false"; exit 2; }
TAG="accum_strip${STRIP}"
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache
export PYTHONINTMAXSTRDIGITS=0   # code-path safety net (see common.py int() guard)

declare -A RECOMB=( [aime]=aime25-aggregate [hmmt]=hmmt25-aggregate [lcbv6]=livecodebench-aggregate )
declare -A EVAL=( [aime]=aime25-none [hmmt]=hmmt25-none [lcbv6]=livecodebench-none )
declare -A TASK=( [aime]=math [hmmt]=math [lcbv6]=code )

gen_config () {
  local ds=$1 odir=$2 run=$3
  cat > configs/squeeze_evolve_loop5_32k_temp1_${TAG}_${ds}_non_saturated.yaml <<EOF
# update=accumulate variant (strip_think=${STRIP}). loops=5, temp=1.0, verifier-free. N_i=80.
run_name: ${run}
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
}

run_one () {
  local ds=$1
  local odir=outputs/node1_se_loop5_32k_temp1_${TAG}_${ds}_non_saturated
  local run=tts_sft_se_loop5_32k_temp1_${TAG}_${ds}_non_saturated_node1
  local cfg=configs/squeeze_evolve_loop5_32k_temp1_${TAG}_${ds}_non_saturated.yaml
  local out=$odir/se.jsonl
  gen_config $ds $odir $run
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

for ds in lcbv6 aime hmmt; do
  run_one $ds || echo "continuing after $ds failure"
done
echo "================ $(date '+%F %T')  ACCUMULATE ($TAG) ALL ATTEMPTED ================"
