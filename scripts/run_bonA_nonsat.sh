#!/bin/bash
# Parallel-A BoN (N=80 @ 32k, temp=1.0, top_k=20) on the non_saturated subsets.
# Run DETACHED via setsid (run_in_background clients keep getting externally killed;
# setsid servers survive). Resume-safe: each driver skips already-written problems.
cd /mnt/cpfs/yangboxue/opsd/TTS/tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
export NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1
BASE="http://localhost:8001/v1,http://localhost:8010/v1,http://localhost:8011/v1,http://localhost:8012/v1,http://localhost:8013/v1,http://localhost:8014/v1,http://localhost:8015/v1,http://localhost:8016/v1"
COMM="--model Qwen/Qwen3-4B-Thinking-2507 --base-urls $BASE --api-key EMPTY --n-samples 80 --temperature 1.0 --top-p 0.95 --top-k 20 --max-tokens 32768 --seed 1234 --concurrency 48 --request-timeout 7200"
echo "=== PARALLEL-A NONSAT AIME @ $(date +%H:%M:%S) ==="
python scripts/calib_bon_dp.py --input data/filtered/aime_non_saturated.jsonl  --output outputs/node2_bon_parallel_N80_32k_temp1_aime_non_saturated.jsonl  --dataset aime $COMM
echo "=== PARALLEL-A NONSAT HMMT @ $(date +%H:%M:%S) ==="
python scripts/calib_bon_dp.py --input data/filtered/hmmt_non_saturated.jsonl  --output outputs/node2_bon_parallel_N80_32k_temp1_hmmt_non_saturated.jsonl  --dataset hmmt $COMM
echo "=== PARALLEL-A NONSAT LCBV6 @ $(date +%H:%M:%S) ==="
python scripts/gen_lcbv6_calibration.py --input data/filtered/lcbv6_non_saturated.jsonl --output outputs/node2_bon_parallel_N80_32k_temp1_lcbv6_non_saturated.jsonl $COMM
echo "=== PARALLEL-A NONSAT DONE @ $(date +%H:%M:%S) ==="
