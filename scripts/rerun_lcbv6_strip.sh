#!/usr/bin/env bash
# Re-run LCBV6 strip=true full (loops 0-4) after the SE code-path int() bug-fix.
# PYTHONINTMAXSTRDIGITS=0 = belt-and-suspenders (no behavior change; lifts the
# interpreter digit cap in case any other int() path is hit). Bug-fix itself is in
# external/squeeze-evolve/src/squeeze_evolve/common.py (guarded int() conversions).
set -u
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache
export PYTHONINTMAXSTRDIGITS=0

cfg=configs/squeeze_evolve_loop5_32k_temp1_strip_lcbv6_non_saturated.yaml
seed=data/filtered/lcbv6_non_saturated.jsonl
odir=outputs/node1_se_loop5_32k_temp1_strip_lcbv6_non_saturated
out=$odir/se.jsonl

echo "================ $(date '+%F %T')  RE-RUN lcbv6 strip=true ================"
# clear stale (failed-run) checkpoints in the SE clone to avoid run_name-scoped mixing
rm -rf external/squeeze-evolve/$odir 2>/dev/null

python scripts/run_squeeze_evolve.py \
  --input  $seed \
  --output $out \
  --config $cfg \
  --squeeze-evolve-dir external/squeeze-evolve \
  --model Qwen/Qwen3-4B-Thinking-2507 \
  --base-url http://localhost:8000/v1 --api-key EMPTY
rc=$?
if [ $rc -ne 0 ]; then echo "RE-RUN FAILED rc=$rc"; exit $rc; fi

python scripts/se_loop_candidates.py \
  --checkpoint-dir $out.checkpoints \
  --se-output      $out \
  --output         $out.loop_candidates.jsonl
echo "================ $(date '+%F %T')  RE-RUN lcbv6 DONE ================"
