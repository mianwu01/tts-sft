#!/usr/bin/env bash
# C-only Feedback-SE viability/compounding pilot, PINNED loop-0.
# Loop-0 = the strip=false rerun #1 (node1_se_loop5_32k_temp1_lcbv6_non_saturated, 90/126) population for
# ALL 126 non_saturated problems — reused verbatim, NO new loop-0 generation.
# C_feedback_vfonly (livecodebench-feedback-aggregate) runs loops 1-4 (resume-continue). Public/sample
# tests build visible feedback only; hidden tests are used OFFLINE post-hoc only. No V3/V4, no SFT.
set -euo pipefail
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache PYTHONINTMAXSTRDIGITS=0

RUN=tts_sft_se_feedback_vfonly_pilot_node1
ODIR=outputs/node1_lcb_feedback_se_vfonly_pilot
CK=external/squeeze-evolve/$ODIR/checkpoints
SRC=outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/se.jsonl.checkpoints/tts_sft_se_loop5_32k_temp1_lcbv6_non_saturated_node1_loop0.json
SEED=data/filtered/lcbv6_non_saturated.jsonl   # ALL 126 non_saturated problems (loop-0 pinned from #1)

# feedback operator env (public/sample tests ONLY; hidden never here)
export LCB_FB_SEED=$PWD/$SEED
export LCB_FB_PUBLIC=$PWD/data/filtered/lcbv6_public_tests.jsonl
export LCB_FB_HARNESS=$PWD/scripts/lcb_public_probe_harness.py
export LCB_FB_LOG=$PWD/$ODIR/feedback_operator_audit.jsonl   # per-call audit (categories, blocks, fallback)

# clean run dirs (keep nothing stale), then PIN loop-0 from #1
rm -rf external/squeeze-evolve/$ODIR "$ODIR"
mkdir -p "$CK" "$ODIR"
python scripts/build_pinned_loop0.py \
  --source-checkpoint "$SRC" \
  --subset-seed "$SEED" \
  --checkpoint-out "$CK/${RUN}_loop0.json" \
  --metadata-dir "$ODIR"

# run_manifest (anchor reuse record)
python - "$ODIR" "$SEED" "$SRC" <<'PY'
import json, sys
odir, seed, src = sys.argv[1:4]
json.dump({
  "run_name": "tts_sft_se_feedback_vfonly_pilot_node1",
  "arm": "C_feedback_vfonly",
  "loop0": "REUSED from strip=false rerun #1 (NOT regenerated)", "loop0_source_checkpoint": src,
  "starts_at_loop": 1, "loops_total": 5, "loops_generated": [1,2,3,4],
  "config": "configs/squeeze_evolve_feedback_vfonly_pilot_node1.yaml",
  "operator": "livecodebench-feedback-aggregate (vfonly): CHECK-bearing V2-concise on visible-failed only; NO block on all_pass",
  "feedback_source": "PUBLIC/sample tests only", "grading": "hidden tests OFFLINE post-hoc only",
  "no_v3_v4": True, "no_sft": True, "update": "replace", "strip_think": False,
  "hyperparams": {"population":16,"k":4,"groups":16,"loops":5,"temperature":1.0,"top_p":0.95,"top_k":20,"max_tokens":32768,"seed":1234,"model":"Qwen/Qwen3-4B-Thinking-2507"},
  "subset_seed": seed, "n_problems": sum(1 for _ in open(seed)),
}, open(odir+"/run_manifest.json","w"), indent=2)
print("wrote", odir+"/run_manifest.json")
PY

echo "$(date '+%F %T') pinned loop-0 placed; starting C_feedback_vfonly loops 1-4"
python scripts/run_squeeze_evolve.py \
  --input "$SEED" \
  --output "$ODIR/se.jsonl" \
  --config configs/squeeze_evolve_feedback_vfonly_pilot_node1.yaml \
  --squeeze-evolve-dir external/squeeze-evolve \
  --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY

# per-loop candidate dataset (loop_candidates.jsonl carries parent_ids per loop candidate)
python scripts/se_loop_candidates.py \
  --checkpoint-dir "$ODIR/se.jsonl.checkpoints" --se-output "$ODIR/se.jsonl" \
  --output "$ODIR/se.jsonl.loop_candidates.jsonl"
echo "$(date '+%F %T') DONE C_feedback_vfonly pilot. Post-hoc grading + report next."
