#!/usr/bin/env bash
# Attribution-set completion runs, SEQUENTIAL: C2 (vfonly + disagreement) first, then B (stay-close only).
# Both: ALL 126 non_saturated, loop-0 PINNED verbatim from strip=false rerun #1 (same anchor as arm C),
# loops 1-4 via resume-continue. Public/sample tests + label-free probe-input disagreement ONLY for
# feedback; hidden tests OFFLINE post-hoc only. No V3/V4, no SFT.
set -euo pipefail
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache PYTHONINTMAXSTRDIGITS=0

SRC=outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/se.jsonl.checkpoints/tts_sft_se_loop5_32k_temp1_lcbv6_non_saturated_node1_loop0.json
SEED=data/filtered/lcbv6_non_saturated.jsonl
export LCB_FB_SEED=$PWD/$SEED
export LCB_FB_PUBLIC=$PWD/data/filtered/lcbv6_public_tests.jsonl
export LCB_FB_HARNESS=$PWD/scripts/lcb_public_probe_harness.py
export LCB_FB_PROBE_INPUTS=$PWD/data/filtered/lcbv6_probe_inputs.jsonl
export LCB_FB_PROBE_EXEC=$PWD/scripts/lcb_probe_exec.py

run_arm () {  # $1=RUN $2=ODIR $3=CONFIG $4=ARM_LABEL
  local RUN=$1 ODIR=$2 CFG=$3 ARM=$4
  local CK=external/squeeze-evolve/$ODIR/checkpoints
  export LCB_FB_LOG=$PWD/$ODIR/feedback_operator_audit.jsonl
  rm -rf external/squeeze-evolve/$ODIR "$ODIR"
  mkdir -p "$CK" "$ODIR"
  python scripts/build_pinned_loop0.py --source-checkpoint "$SRC" --subset-seed "$SEED" \
    --checkpoint-out "$CK/${RUN}_loop0.json" --metadata-dir "$ODIR"
  python - "$ODIR" "$ARM" "$CFG" <<'PY'
import json, sys
odir, arm, cfg = sys.argv[1:4]
json.dump({"arm": arm, "loop0": "REUSED from strip=false rerun #1 (NOT regenerated)",
  "starts_at_loop": 1, "loops_generated": [1,2,3,4], "config": cfg,
  "feedback_source": "PUBLIC tests + label-free probe-input disagreement (C2) / none (B)",
  "grading": "hidden tests OFFLINE post-hoc only", "no_v3_v4": True, "no_sft": True,
  "hyperparams": {"population":16,"k":4,"groups":16,"loops":5,"update":"replace","strip_think":False,
                  "temperature":1.0,"top_p":0.95,"top_k":20,"max_tokens":32768,"seed":1234}},
  open(odir+"/run_manifest.json","w"), indent=2)
PY
  echo "$(date '+%F %T') [$ARM] pinned loop-0 placed; starting loops 1-4"
  python scripts/run_squeeze_evolve.py --input "$SEED" --output "$ODIR/se.jsonl" --config "$CFG" \
    --squeeze-evolve-dir external/squeeze-evolve \
    --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY
  python scripts/se_loop_candidates.py --checkpoint-dir "$ODIR/se.jsonl.checkpoints" \
    --se-output "$ODIR/se.jsonl" --output "$ODIR/se.jsonl.loop_candidates.jsonl"
  echo "$(date '+%F %T') [$ARM] DONE"
}

run_arm tts_sft_se_feedback_c2_disagreement_node1 outputs/node1_lcb_feedback_se_c2_disagreement \
        configs/squeeze_evolve_feedback_c2_node1.yaml C2_feedback_disagreement
run_arm tts_sft_se_stayclose_b_node1 outputs/node1_lcb_stayclose_b \
        configs/squeeze_evolve_stayclose_b_node1.yaml B_stayclose_only
echo "$(date '+%F %T') BOTH ARMS COMPLETE"
