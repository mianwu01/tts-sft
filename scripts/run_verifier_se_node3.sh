#!/usr/bin/env bash
# NODE3: V arm ("verifier-SE") — full-suite verdicts key selection grouping + elitist retention;
# prompts are the C2 operator VERBATIM (hidden-test content never enters a prompt).
# Pinned loop-0 from strip=false rerun #1 (same anchor as A/B/C/C2), loops 1-4, seed 1234.
# Usage: run_verifier_se_node3.sh smoke   -> 2 problems, loops 1-2
#        run_verifier_se_node3.sh full    -> all 126, loops 1-4
set -euo pipefail
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
# node3 box: miniconda python lacks pyyaml; working stack (vllm, squeeze-evolve-client) is /usr/local/bin
export PATH=/usr/local/bin:$PATH
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache PYTHONINTMAXSTRDIGITS=0

MODE=${1:-smoke}
SRC=outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/se.jsonl.checkpoints/tts_sft_se_loop5_32k_temp1_lcbv6_non_saturated_node1_loop0.json

if [ "$MODE" = smoke ]; then
  RUN=tts_sft_se_verifier_v_smoke_node3
  ODIR=outputs/node3_lcb_verifier_v_smoke
  CFG=configs/squeeze_evolve_verifier_v_smoke_node3.yaml
  SEED=$ODIR/smoke_seed.jsonl
  mkdir -p "$ODIR"
  head -2 data/filtered/lcbv6_non_saturated.jsonl > "$SEED"
else
  RUN=tts_sft_se_verifier_v_node3
  ODIR=outputs/node3_lcb_verifier_v
  CFG=configs/squeeze_evolve_verifier_v_node3.yaml
  SEED=data/filtered/lcbv6_non_saturated.jsonl
fi

# C2 recombination env (public tests + label-free probe disagreement; unchanged frozen behavior)
export LCB_FB_SEED=$PWD/data/filtered/lcbv6_non_saturated.jsonl
export LCB_FB_PUBLIC=$PWD/data/filtered/lcbv6_public_tests.jsonl
export LCB_FB_HARNESS=$PWD/scripts/lcb_public_probe_harness.py
export LCB_FB_PROBE_INPUTS=$PWD/data/filtered/lcbv6_probe_inputs.jsonl
export LCB_FB_PROBE_EXEC=$PWD/scripts/lcb_probe_exec.py
export LCB_FB_LOG=$PWD/$ODIR/feedback_operator_audit.jsonl

# V-arm verifier env (full-suite verdicts -> machinery only)
CK=external/squeeze-evolve/$ODIR/checkpoints
export LCB_VF_CKPT_DIR=$PWD/$CK
export LCB_VF_RUN=$RUN
export LCB_VF_SEED=$PWD/data/filtered/lcbv6_non_saturated.jsonl
export LCB_VF_HARNESS=$PWD/scripts/lcb_exec_harness.py
export LCB_VF_GRADING=$PWD/scripts/lcb_grading.py
export LCB_VF_CACHE=$PWD/outputs/grading_cache/hidden_inloop.jsonl
export LCB_VF_LOG=$PWD/$ODIR/verifier_operator_audit.jsonl
export LCB_VF_CONC=64
export LCB_VF_ELITES=2

rm -rf external/squeeze-evolve/$ODIR/checkpoints "$ODIR"/se.jsonl* "$ODIR"/*.jsonl "$ODIR"/*.json
mkdir -p "$CK" "$ODIR"
if [ "$MODE" = smoke ]; then head -2 data/filtered/lcbv6_non_saturated.jsonl > "$SEED"; fi
python scripts/build_pinned_loop0.py --source-checkpoint "$SRC" --subset-seed "$SEED" \
  --checkpoint-out "$CK/${RUN}_loop0.json" --metadata-dir "$ODIR"
python - "$ODIR" "$MODE" <<'PY'
import json, sys
odir, mode = sys.argv[1:3]
json.dump({"arm": "V_verifier_se", "mode": mode,
  "loop0": "REUSED from strip=false rerun #1 (NOT regenerated)",
  "starts_at_loop": 1, "config": f"configs/squeeze_evolve_verifier_v{'_smoke' if mode=='smoke' else ''}_node3.yaml",
  "machinery": "selection=livecodebench-verifier-selection (1 verified-correct scaffold/group), "
               "update=livecodebench-elitist-replace (<=2 elites/problem)",
  "verdict_source": "FULL hidden suites of THESE problems -> oracle/regime-simulation claim only; "
                    "outputs are NOT held-out eval results and NOT SFT data",
  "prompts": "C2 operator verbatim; hidden-test content NEVER in prompts",
  "grading": "post-hoc standard pipeline (verdicts shared via grading cache)", "no_sft": True,
  "hyperparams": {"population":16,"k":4,"groups":16,"temperature":1.0,"top_p":0.95,"top_k":20,
                  "max_tokens":32768,"seed":1234,"elites":2}},
  open(odir+"/run_manifest.json","w"), indent=2)
PY
echo "$(date '+%F %T') [V_$MODE] pinned loop-0 placed; starting loops"
python scripts/run_squeeze_evolve.py --input "$SEED" --output "$ODIR/se.jsonl" --config "$CFG" \
  --squeeze-evolve-dir external/squeeze-evolve \
  --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY
python scripts/se_loop_candidates.py --checkpoint-dir "$ODIR/se.jsonl.checkpoints" \
  --se-output "$ODIR/se.jsonl" --output "$ODIR/se.jsonl.loop_candidates.jsonl"
echo "$(date '+%F %T') [V_$MODE] DONE"
