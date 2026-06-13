#!/usr/bin/env bash
# Completes the loop-0-controlled 2x2 {plain, M5} x {strip false, true} on the STRIP=FALSE anchor.
# Waits for the in-flight strip=true-anchor run (if any), then runs 4 dataset-runs:
#   plain strip=true  from strip=false loop-0   (math fixedloop0 ablation, aime+hmmt)
#   M5    strip=true  from strip=false loop-0   (aime+hmmt)
# Existing cells: plain-F + M5-F (strip=false runs, same anchor). All paired on identical loop-0.
set -euo pipefail
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache PYTHONINTMAXSTRDIGITS=0

WAIT_PID="${1:-}"
if [ -n "$WAIT_PID" ]; then
  echo "$(date '+%F %T') waiting for pid $WAIT_PID (in-flight strip-anchor run) ..."
  while ps -p "$WAIT_PID" >/dev/null 2>&1; do sleep 60; done
  echo "$(date '+%F %T') pid $WAIT_PID gone; starting 2x2 completion"
fi

run_one () {  # run_one <arm:plain|m5> <ds>
  local arm=$1 ds=$2
  local RUN ODIR CFG
  if [ "$arm" = plain ]; then
    RUN=tts_sft_se_plainstrip_f0_${ds}_node2; ODIR=outputs/node2_math_plainstrip_f0_${ds}
    CFG=configs/squeeze_evolve_plainstrip_f0_${ds}_node2.yaml
  else
    RUN=tts_sft_se_m5fb_strip_f0_${ds}_node2; ODIR=outputs/node2_math_m5fb_strip_f0_${ds}
    CFG=configs/squeeze_evolve_m5fb_strip_f0_${ds}_node2.yaml
  fi
  local CK=external/squeeze-evolve/$ODIR/checkpoints
  local SRC=outputs/node1_se_loop5_32k_temp1_${ds}_non_saturated/se.jsonl.checkpoints/tts_sft_se_loop5_32k_temp1_${ds}_non_saturated_node1_loop0.json
  local SEED=data/filtered/${ds}_non_saturated.jsonl

  if [ "$arm" = m5 ]; then
    export M5_FB_CKPT_DIR=$PWD/$CK M5_FB_RUN=$RUN M5_FB_TTS_SRC=$PWD/src
    export M5_FB_LOG=$PWD/$ODIR/feedback_operator_audit.jsonl
    export M5_FB_BASE_URL=http://localhost:8000/v1 M5_FB_MODEL=Qwen/Qwen3-4B-Thinking-2507 M5_FB_CONC=48
  fi

  rm -rf external/squeeze-evolve/$ODIR "$ODIR"
  mkdir -p "$CK" "$ODIR"
  python scripts/build_pinned_loop0.py \
    --source-checkpoint "$SRC" \
    --source-run tts_sft_se_loop5_32k_temp1_${ds}_non_saturated_node1 \
    --subset-seed "$SEED" \
    --checkpoint-out "$CK/${RUN}_loop0.json" \
    --metadata-dir "$ODIR"
  echo "{\"run_name\":\"$RUN\",\"arm\":\"${arm}_strip_true_anchor_stripfalse\",\"loop0_source\":\"$SRC\",\"config\":\"$CFG\"}" > "$ODIR/run_manifest.json"

  echo "$(date '+%F %T') [$arm/$ds] pinned strip=false loop-0; running strip=true loops 1-4"
  python scripts/run_squeeze_evolve.py \
    --input "$SEED" --output "$ODIR/se.jsonl" --config "$CFG" \
    --squeeze-evolve-dir external/squeeze-evolve \
    --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY
  python scripts/se_loop_candidates.py \
    --checkpoint-dir "$ODIR/se.jsonl.checkpoints" --se-output "$ODIR/se.jsonl" \
    --output "$ODIR/se.jsonl.loop_candidates.jsonl"
  echo "$(date '+%F %T') [$arm/$ds] DONE"
}

run_one plain aime
run_one plain hmmt
run_one m5 aime
run_one m5 hmmt
echo "$(date '+%F %T') 2x2 COMPLETION ALL DONE"
