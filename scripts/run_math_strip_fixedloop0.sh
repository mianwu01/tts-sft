#!/usr/bin/env bash
# Loop-0-matched strip ablation for MATH (mirrors the LCBV6 fixedloop0 recipe, scripts/run_lcbv6_strip_fixedloop0.sh):
# strip_think=TRUE loops 1-4 from the strip=FALSE formal runs' loop-0 populations (AIME 18, HMMT 21),
# isolating the recombination-input effect from loop-0 sampling variance. The previous strip=true math
# runs used their own fresh loop-0s -> unfair; this re-run fixes that. Verifier-free, update=replace.
# After each run: loop_candidates + hidden grading (score_se_subset, math exact-match).
set -euo pipefail
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache PYTHONINTMAXSTRDIGITS=0

run_subset () {  # $1=subset(aime|hmmt) $2=recomb_op $3=eval_op
  local S=$1 OP=$2 EV=$3
  local RUN=tts_sft_se_strip_${S}_fixedloop0_node1
  local ODIR=outputs/node1_se_strip_${S}_fixedloop0
  local CK=external/squeeze-evolve/$ODIR/checkpoints
  local SRC=outputs/node1_se_loop5_32k_temp1_${S}_non_saturated/se.jsonl.checkpoints/tts_sft_se_loop5_32k_temp1_${S}_non_saturated_node1_loop0.json
  local SEED=data/filtered/${S}_non_saturated.jsonl

  cat > configs/squeeze_evolve_strip_${S}_fixedloop0.yaml <<EOF
# Loop-0-matched strip ablation ($S): strip=true loops 1-4 from strip=FALSE's loop-0 (resume-continue).
run_name: $RUN
routing: {k: 4, population: 16, groups: 16, loops: 5, confidence_percentiles: [], fitness: diversity, selection: uniform, selection_temperature: 1.0, update: replace, lite_fraction: 0.0, lite_method: majority, recombination: $OP, evaluation: $EV, task: math, generation_batch_size: 48, strip_think: true, seed: 1234}
models: [{name: Qwen/Qwen3-4B-Thinking-2507, base_url: http://localhost:8000/v1, api_key: EMPTY, endpoint: chat, max_tokens: 32768, temperature: 1.0, top_p: 0.95, max_concurrency: 48, extra_body: {top_k: 20}}]
retry: {request_timeout_seconds: 7200}
resume: true
checkpoint_dir: ./$ODIR/checkpoints
metrics_path: ./$ODIR/metrics.json
EOF
  rm -rf external/squeeze-evolve/$ODIR "$ODIR"
  mkdir -p "$CK" "$ODIR"
  cp "$SRC" "$CK/${RUN}_loop0.json"
  python - "$ODIR" "$SRC" "$S" <<'PY'
import json, sys
odir, src, s = sys.argv[1:4]
json.dump({"ablation": "loop-0-matched strip=true (math)", "subset": s,
  "loop0": "REUSED from the strip=false formal run (NOT regenerated)", "loop0_source_checkpoint": src,
  "starts_at_loop": 1, "loops_generated": [1,2,3,4], "strip_think": True,
  "note": "supersedes the unmatched strip=true run for fair strip comparison"},
  open(odir+"/run_manifest.json","w"), indent=2)
PY
  echo "$(date '+%F %T') [$S] pinned strip=false loop-0 placed; starting strip=true loops 1-4"
  python scripts/run_squeeze_evolve.py \
    --input "$SEED" --output "$ODIR/se.jsonl" \
    --config configs/squeeze_evolve_strip_${S}_fixedloop0.yaml \
    --squeeze-evolve-dir external/squeeze-evolve \
    --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY
  python scripts/se_loop_candidates.py --checkpoint-dir "$ODIR/se.jsonl.checkpoints" \
    --se-output "$ODIR/se.jsonl" --output "$ODIR/se.jsonl.loop_candidates.jsonl"
  python scripts/score_se_subset.py \
    --loop-candidates "$ODIR/se.jsonl.loop_candidates.jsonl" --seed "$SEED" \
    --metrics-json "$ODIR/metrics.json" --task math --dataset "$S" \
    --out-genlog "$ODIR/genlog.jsonl" --out-perproblem "$ODIR/per_problem.jsonl" \
    --out-summary "$ODIR/summary.json" --workers 32
  echo "$(date '+%F %T') [$S] DONE (graded)"
}

run_subset aime aime25-aggregate aime25-none
run_subset hmmt hmmt25-aggregate hmmt25-none
echo "$(date '+%F %T') MATH STRIP FIXEDLOOP0 — BOTH SUBSETS COMPLETE"
