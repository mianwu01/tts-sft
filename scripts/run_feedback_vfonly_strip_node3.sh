#!/usr/bin/env bash
# NODE3: C-strip arm — vfonly Feedback-SE (public tests only) with strip_think=true.
# ONE-VARIABLE change vs arm C (strip=false); loop-0 PINNED verbatim from strip=false rerun #1
# (same anchor as A/B/C/C2/V), loops 1-4 resume-continue, seed 1234, 32k, temp 1.0.
# Hidden tests OFFLINE post-hoc only. No V3/V4, no SFT.
set -euo pipefail
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
# node3 box: miniconda python lacks pyyaml; working stack is /usr/local/bin
export PATH=/usr/local/bin:$PATH
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache PYTHONINTMAXSTRDIGITS=0

SRC=outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/se.jsonl.checkpoints/tts_sft_se_loop5_32k_temp1_lcbv6_non_saturated_node1_loop0.json
SEED=data/filtered/lcbv6_non_saturated.jsonl
RUN=tts_sft_se_feedback_vfonly_strip_node3
ODIR=outputs/node3_lcb_feedback_vfonly_strip
CFG=configs/squeeze_evolve_feedback_vfonly_strip_node3.yaml
CK=external/squeeze-evolve/$ODIR/checkpoints

export LCB_FB_SEED=$PWD/$SEED
export LCB_FB_PUBLIC=$PWD/data/filtered/lcbv6_public_tests.jsonl
export LCB_FB_HARNESS=$PWD/scripts/lcb_public_probe_harness.py
export LCB_FB_LOG=$PWD/$ODIR/feedback_operator_audit.jsonl

rm -rf external/squeeze-evolve/$ODIR "$ODIR"
mkdir -p "$CK" "$ODIR"
python scripts/build_pinned_loop0.py --source-checkpoint "$SRC" --subset-seed "$SEED" \
  --checkpoint-out "$CK/${RUN}_loop0.json" --metadata-dir "$ODIR"
python - "$ODIR" <<'PY'
import json, sys
odir = sys.argv[1]
json.dump({"arm": "C_strip_vfonly", "node": "node3",
  "loop0": "REUSED from strip=false rerun #1 (NOT regenerated) — identical anchor to A/B/C/C2/V",
  "starts_at_loop": 1, "loops_generated": [1, 2, 3, 4],
  "config": "configs/squeeze_evolve_feedback_vfonly_strip_node3.yaml",
  "delta_vs_C": "strip_think: true (ONLY change; same operator, env, hyperparams, seed)",
  "feedback_source": "PUBLIC/sample tests only (vfonly)",
  "grading": "hidden tests OFFLINE post-hoc only", "no_v3_v4": True, "no_sft": True,
  "hyperparams": {"population":16,"k":4,"groups":16,"loops":5,"update":"replace","strip_think":True,
                  "temperature":1.0,"top_p":0.95,"top_k":20,"max_tokens":32768,"seed":1234}},
  open(odir+"/run_manifest.json","w"), indent=2)
PY
echo "$(date '+%F %T') [C_strip] pinned loop-0 placed; starting loops 1-4"
python scripts/run_squeeze_evolve.py --input "$SEED" --output "$ODIR/se.jsonl" --config "$CFG" \
  --squeeze-evolve-dir external/squeeze-evolve \
  --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY
python scripts/se_loop_candidates.py --checkpoint-dir "$ODIR/se.jsonl.checkpoints" \
  --se-output "$ODIR/se.jsonl" --output "$ODIR/se.jsonl.loop_candidates.jsonl"
echo "$(date '+%F %T') [C_strip] DONE"
