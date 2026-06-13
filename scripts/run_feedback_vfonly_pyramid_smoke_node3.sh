#!/usr/bin/env bash
# NODE3 pyramid/funnel Feedback-SE SMOKE (2 problems, schedule loop1:4 -> loop2:2).
# Loop-0 = PINNED verbatim from the strip=false rerun #1 loop-0 checkpoint (READ-ONLY source) — the
# same anchor the node1 constant-width pilot pins. NO new loop-0 generation.
# Frozen vfonly feedback semantics (operator untouched): CHECK-bearing V2-concise blocks ONLY for
# visible public/sample-test failures, NO block for all_pass, top-level failed-only note, stay-close.
# Hidden tests are NEVER used in-loop (post-hoc grading only). No V3/V4, no SFT.
#
# SAFETY: this script removes/writes ONLY the node3 *pyramid smoke* directories below. It never
# touches outputs/node1_* or the node1 in-flight pilot.
set -euo pipefail
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache PYTHONINTMAXSTRDIGITS=0
export PATH=/usr/local/bin:$PATH   # system python 3.11 (yaml + squeeze-evolve install), not miniconda

RUN=tts_sft_se_feedback_vfonly_pyramid_smoke_node3
ODIR=outputs/node3_lcb_feedback_se_vfonly_pyramid_smoke
EDIR=external/squeeze-evolve/$ODIR            # engine-side run dir (checkpoints + metrics)
CK=$EDIR/checkpoints
SRC=outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/se.jsonl.checkpoints/tts_sft_se_loop5_32k_temp1_lcbv6_non_saturated_node1_loop0.json
SEED=data/filtered/lcbv6_pyramid_smoke2_node3.jsonl   # lcbv6-037 + lcbv6-039 (mixed public-test outcomes)
SCHEDULE="4,2"

# feedback operator env (public/sample tests ONLY; hidden tests never referenced here)
export LCB_FB_SEED=$PWD/$SEED
export LCB_FB_PUBLIC=$PWD/data/filtered/lcbv6_public_tests.jsonl
export LCB_FB_HARNESS=$PWD/scripts/lcb_public_probe_harness.py
export LCB_FB_LOG=$PWD/$ODIR/feedback_operator_audit.jsonl

# clean ONLY this smoke's own dirs (explicit paths, node3 pyramid smoke only)
rm -rf "external/squeeze-evolve/outputs/node3_lcb_feedback_se_vfonly_pyramid_smoke" \
       "outputs/node3_lcb_feedback_se_vfonly_pyramid_smoke"
mkdir -p "$CK" "$ODIR"

# PIN loop-0 from #1 (subset to the 2 smoke problems; writes pinned_subset.jsonl,
# loop0_population.jsonl, loop0_source_manifest.json into $ODIR)
python scripts/build_pinned_loop0.py \
  --source-checkpoint "$SRC" \
  --subset-seed "$SEED" \
  --checkpoint-out "$CK/${RUN}_loop0.json" \
  --metadata-dir "$ODIR"

# run_manifest
python - "$ODIR" "$SEED" "$SRC" "$SCHEDULE" <<'PY'
import json, sys
odir, seed, src, sched = sys.argv[1:5]
schedule = [int(x) for x in sched.split(",")]
json.dump({
  "run_name": "tts_sft_se_feedback_vfonly_pyramid_smoke_node3",
  "node": "node3", "arm": "C_feedback_vfonly_pyramid",
  "variant": "pyramid/funnel — DECREASING per-loop recombination groups (staged resume; "
             "SqueezeEvolve has no native per-loop groups schedule)",
  "schedule_groups_per_loop": schedule,
  "population_funnel": [16] + schedule,
  "loop0": "REUSED from strip=false rerun #1 (NOT regenerated)", "loop0_source_checkpoint": src,
  "starts_at_loop": 1, "loops_generated": list(range(1, len(schedule) + 1)),
  "base_config": "configs/squeeze_evolve_feedback_vfonly_pyramid_node3_smoke.yaml",
  "stage_driver": "scripts/run_se_pyramid_stages.py",
  "operator": "livecodebench-feedback-aggregate (vfonly): CHECK-bearing V2-concise on visible-failed only; NO block on all_pass",
  "feedback_source": "PUBLIC/sample tests only", "grading": "hidden tests OFFLINE post-hoc only",
  "no_v3_v4": True, "no_sft": True, "update": "replace", "strip_think": False,
  "hyperparams": {"population": 16, "k": 4, "loops_total": len(schedule) + 1,
                  "temperature": 1.0, "top_p": 0.95, "top_k": 20, "max_tokens": 32768,
                  "base_routing_seed": 1234, "per_stage_routing_seed": "1234 + loop_index",
                  "model": "Qwen/Qwen3-4B-Thinking-2507"},
  "subset_seed": seed, "n_problems": sum(1 for _ in open(seed)),
  "isolation": "node3-only output dirs; node1 run/baseline untouched",
}, open(odir + "/run_manifest.json", "w"), indent=2)
print("wrote", odir + "/run_manifest.json")
PY

echo "$(date '+%F %T') pinned loop-0 placed; starting pyramid stages (schedule $SCHEDULE)"
python scripts/run_se_pyramid_stages.py \
  --input "$SEED" \
  --output "$ODIR/se.jsonl" \
  --base-config configs/squeeze_evolve_feedback_vfonly_pyramid_node3_smoke.yaml \
  --squeeze-evolve-dir external/squeeze-evolve \
  --schedule "$SCHEDULE" \
  --base-routing-seed 1234 \
  --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY \
  --audit-log "$LCB_FB_LOG"

# per-loop candidate dataset (carries parent_ids per loop candidate)
python scripts/se_loop_candidates.py \
  --checkpoint-dir "$ODIR/se.jsonl.checkpoints" --se-output "$ODIR/se.jsonl" \
  --output "$ODIR/se.jsonl.loop_candidates.jsonl"
echo "$(date '+%F %T') DONE node3 pyramid smoke. Post-hoc: build_node3_pyramid_posthoc.py + score_se_subset.py."
