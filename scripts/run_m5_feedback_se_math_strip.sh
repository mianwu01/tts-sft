#!/usr/bin/env bash
# Formal MATH Feedback-SE experiment (Node 2): M5 feedback in recombination, PINNED loop-0.
# Mirrors scripts/run_feedback_vfonly_pilot.sh (LCB). Per dataset (aime, hmmt):
#   loop-0 = the STRIP=TRUE formal verifier-free run's loop-0 population, reused VERBATIM (no regeneration)
#   loops 1-4 = resume-continue with recombination = <ds>25-m5-feedback-aggregate
#   M5 = answer-hidden verifier verdict + margin-gated population consistency + mention-suppression
#   (frozen config: docs/MATH_FEEDBACK_ANSWER_HIDDEN_PROBE.md). Gold strings never enter prompts.
# Paired reference = the formal run's own loops 1-4 from the IDENTICAL loop-0. No SFT, no RL.
# WARNING: rm -rf's its own output dirs at start — do NOT re-run while a pilot is live.
set -euo pipefail
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache PYTHONINTMAXSTRDIGITS=0

for ds in aime hmmt; do
  RUN=tts_sft_se_m5fb_strip_${ds}_node2
  ODIR=outputs/node2_math_m5fb_se_strip_${ds}
  CK=external/squeeze-evolve/$ODIR/checkpoints
  SRC=outputs/node1_se_loop5_32k_temp1_strip_${ds}_non_saturated/se.jsonl.checkpoints/tts_sft_se_loop5_32k_temp1_strip_${ds}_non_saturated_node1_loop0.json
  SEED=data/filtered/${ds}_non_saturated.jsonl

  export M5_FB_CKPT_DIR=$PWD/$CK
  export M5_FB_RUN=$RUN
  export M5_FB_TTS_SRC=$PWD/src
  export M5_FB_LOG=$PWD/$ODIR/feedback_operator_audit.jsonl
  export M5_FB_BASE_URL=http://localhost:8000/v1
  export M5_FB_MODEL=Qwen/Qwen3-4B-Thinking-2507
  export M5_FB_CONC=48

  rm -rf external/squeeze-evolve/$ODIR "$ODIR"
  mkdir -p "$CK" "$ODIR"
  python scripts/build_pinned_loop0.py \
    --source-checkpoint "$SRC" \
    --source-run tts_sft_se_loop5_32k_temp1_strip_${ds}_non_saturated_node1 \
    --subset-seed "$SEED" \
    --checkpoint-out "$CK/${RUN}_loop0.json" \
    --metadata-dir "$ODIR"

  python - "$ODIR" "$SEED" "$SRC" "$ds" <<'PY'
import json, sys
odir, seed, src, ds = sys.argv[1:5]
json.dump({
  "run_name": f"tts_sft_se_m5fb_strip_{ds}_node2", "arm": "M5_feedback_se_math_STRIP",
  "loop0": "REUSED from the STRIP=TRUE formal verifier-free run (NOT regenerated)", "loop0_source_checkpoint": src,
  "starts_at_loop": 1, "loops_total": 5, "loops_generated": [1, 2, 3, 4],
  "config": f"configs/squeeze_evolve_m5fb_strip_{ds}_node2.yaml",
  "operator": f"{ds}25-m5-feedback-aggregate: answer-hidden verifier verdict + margin-gated "
              "population consistency (gate margin<=1 & second>=4) + mention-suppression tail; "
              "critic temp 0.1 / 10240 tok / stripped view / post-think block only",
  "feedback_source": "gt used ONLY for the accepted/rejected verdict bit (string hidden); "
                     "distribution is population self-signal (gold-free)",
  "paired_reference": f"outputs/node1_se_loop5_32k_temp1_strip_{ds}_non_saturated (same loop-0, plain aggregate)",
  "no_sft": True, "update": "replace", "strip_think": True,
  "hyperparams": {"population": 16, "k": 4, "groups": 16, "loops": 5, "temperature": 1.0,
                  "top_p": 0.95, "top_k": 20, "max_tokens": 32768, "seed": 1234,
                  "model": "Qwen/Qwen3-4B-Thinking-2507"},
  "subset_seed": seed, "n_problems": sum(1 for _ in open(seed)),
}, open(odir + "/run_manifest.json", "w"), indent=2)
print("wrote", odir + "/run_manifest.json")
PY

  echo "$(date '+%F %T') [$ds] pinned loop-0 placed; starting M5 Feedback-SE loops 1-4"
  python scripts/run_squeeze_evolve.py \
    --input "$SEED" \
    --output "$ODIR/se.jsonl" \
    --config configs/squeeze_evolve_m5fb_strip_${ds}_node2.yaml \
    --squeeze-evolve-dir external/squeeze-evolve \
    --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY

  python scripts/se_loop_candidates.py \
    --checkpoint-dir "$ODIR/se.jsonl.checkpoints" --se-output "$ODIR/se.jsonl" \
    --output "$ODIR/se.jsonl.loop_candidates.jsonl"
  echo "$(date '+%F %T') [$ds] DONE generation + loop_candidates"
done
echo "$(date '+%F %T') ALL DONE (aime + hmmt). Post-hoc grading next."
