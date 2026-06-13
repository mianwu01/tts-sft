#!/bin/bash
# Sequential-B BoN (N=16 @ max_tokens=163840, temp=1.0, top_k=20) on NON_SATURATED (165 problems = 2640 gens).
# STAGED — do NOT run until Parallel-A finishes AND the sequential fleet is up + smoke-tested.
# REQUIRED FLEET: 8 single-GPU vLLM replicas with --max-model-len 196608 (>= max_prompt 1364 + 163840 + slack;
#   262144 also valid but tighter concurrency). Ports 8001 + 8010..8016. Concurrency starts LOW (long-context KV
#   is heavy: ~28GB/full-196608-seq); tune down further if OOM/timeouts.
# Run DETACHED via setsid; resume-safe (drivers skip already-written problems).
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
export NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1
BASE="http://localhost:8001/v1,http://localhost:8010/v1,http://localhost:8011/v1,http://localhost:8012/v1,http://localhost:8013/v1,http://localhost:8014/v1,http://localhost:8015/v1,http://localhost:8016/v1"
COMM="--model Qwen/Qwen3-4B-Thinking-2507 --base-urls $BASE --api-key EMPTY --n-samples 16 --temperature 1.0 --top-p 0.95 --top-k 20 --max-tokens 163840 --seed 1234 --concurrency 16 --request-timeout 14400"
echo "=== SEQUENTIAL-B NONSAT AIME (18x16=288) @ $(date +%H:%M:%S) ==="
python scripts/calib_bon_dp.py --input data/filtered/aime_non_saturated.jsonl  --output outputs/node2_bon_sequential_N16_160k_temp1_aime_non_saturated.jsonl  --dataset aime $COMM
echo "=== SEQUENTIAL-B NONSAT HMMT (21x16=336) @ $(date +%H:%M:%S) ==="
python scripts/calib_bon_dp.py --input data/filtered/hmmt_non_saturated.jsonl  --output outputs/node2_bon_sequential_N16_160k_temp1_hmmt_non_saturated.jsonl  --dataset hmmt $COMM
echo "=== SEQUENTIAL-B NONSAT LCBV6 (126x16=2016) @ $(date +%H:%M:%S) ==="
python scripts/gen_lcbv6_calibration.py --input data/filtered/lcbv6_non_saturated.jsonl --output outputs/node2_bon_sequential_N16_160k_temp1_lcbv6_non_saturated.jsonl $COMM
echo "=== SEQUENTIAL-B NONSAT DONE @ $(date +%H:%M:%S) ==="
