#!/usr/bin/env bash
# Chained verifier-free SE loops=5 runs on the 3 non_saturated subsets (shared TP8@262144 :8000).
# Smallest first. Each dataset: run SE -> flatten per-loop candidates. On non-zero exit (e.g. context
# overflow) for a dataset: record FAILED and SKIP flattening for it, then continue to the next dataset
# (no retry, no settings change — per instruction).
set -u
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache

run_one () {
  local ds=$1
  local cfg=configs/squeeze_evolve_loop5_32k_temp1_strip_${ds}_non_saturated.yaml
  local seed=data/filtered/${ds}_non_saturated.jsonl
  local odir=outputs/node1_se_loop5_32k_temp1_strip_${ds}_non_saturated
  local out=$odir/se.jsonl
  echo "================ $(date '+%F %T')  START $ds  ================"
  # avoid stale run_name-scoped checkpoints inside the SE clone
  rm -rf external/squeeze-evolve/$odir 2>/dev/null
  mkdir -p $odir
  python scripts/run_squeeze_evolve.py \
    --input  $seed \
    --output $out \
    --config $cfg \
    --squeeze-evolve-dir external/squeeze-evolve \
    --model Qwen/Qwen3-4B-Thinking-2507 \
    --base-url http://localhost:8000/v1 --api-key EMPTY
  local rc=$?
  if [ $rc -ne 0 ]; then
    echo "================ $(date '+%F %T')  $ds FAILED rc=$rc (NO retry; see log) ================"
    return $rc
  fi
  python scripts/se_loop_candidates.py \
    --checkpoint-dir $out.checkpoints \
    --se-output      $out \
    --output         $out.loop_candidates.jsonl
  echo "================ $(date '+%F %T')  DONE $ds ================"
}

for ds in aime hmmt lcbv6; do
  run_one $ds || echo "continuing to next dataset after $ds failure"
done
echo "================ $(date '+%F %T')  ALL DATASETS ATTEMPTED ================"
