#!/usr/bin/env bash
# Clean strip ablation: strip=true loops 1-4 from strip=FALSE's loop-0 (the 90-solving population),
# isolating the recombination-input effect from loop-0 sampling variance. Uses the resume-continue
# patch (orchestrator skips regenerating loop 0 when a loop-0 checkpoint is present + resume=true).
set -u
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export VLLM_USE_MODELSCOPE=False HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache PYTHONINTMAXSTRDIGITS=0
RUN=tts_sft_se_strip_lcbv6_fixedloop0_node1
ODIR=outputs/node1_se_strip_lcbv6_fixedloop0
CK=external/squeeze-evolve/$ODIR/checkpoints
SRC=outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/se.jsonl.checkpoints/tts_sft_se_loop5_32k_temp1_lcbv6_non_saturated_node1_loop0.json
cat > configs/squeeze_evolve_strip_lcbv6_fixedloop0.yaml <<EOF
run_name: $RUN
routing: {k: 4, population: 16, groups: 16, loops: 5, confidence_percentiles: [], fitness: diversity, selection: uniform, selection_temperature: 1.0, update: replace, lite_fraction: 0.0, lite_method: majority, recombination: livecodebench-aggregate, evaluation: livecodebench-none, task: code, generation_batch_size: 48, strip_think: true, seed: 1234}
models: [{name: Qwen/Qwen3-4B-Thinking-2507, base_url: http://localhost:8000/v1, api_key: EMPTY, endpoint: chat, max_tokens: 32768, temperature: 1.0, top_p: 0.95, max_concurrency: 48, extra_body: {top_k: 20}}]
retry: {request_timeout_seconds: 7200}
resume: true
checkpoint_dir: ./$ODIR/checkpoints
metrics_path: ./$ODIR/metrics.json
EOF
rm -rf external/squeeze-evolve/$ODIR; mkdir -p $CK $ODIR
cp "$SRC" "$CK/${RUN}_loop0.json"
echo "$(date '+%F %T') placed fixed loop0 (strip=false's 90-solving population); starting strip=true loops 1-4"
python scripts/run_squeeze_evolve.py \
  --input data/filtered/lcbv6_non_saturated.jsonl \
  --output $ODIR/se.jsonl --config configs/squeeze_evolve_strip_lcbv6_fixedloop0.yaml \
  --squeeze-evolve-dir external/squeeze-evolve \
  --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY || { echo "FAILED"; exit 1; }
python scripts/se_loop_candidates.py --checkpoint-dir $ODIR/se.jsonl.checkpoints --se-output $ODIR/se.jsonl --output $ODIR/se.jsonl.loop_candidates.jsonl
echo "$(date '+%F %T') DONE fixedloop0 ablation"
