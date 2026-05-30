# Convenience commands. Override variables on the command line, e.g.:
#     make raw-generate MODEL=Qwen/Qwen3-4B-Thinking-2507 SEED=data/seeds/math_seed.jsonl

PYTHON ?= python
MODEL ?= Qwen/Qwen3-4B-Thinking-2507
BASE_URL ?= http://localhost:8000/v1
API_KEY ?= EMPTY

SEED ?= data/seeds/sample_math_seed.jsonl
EVAL ?= data/eval/sample_eval.jsonl

RAW_GEN ?= data/generated/raw_generations.jsonl
SE_GEN ?= data/generated/squeeze_evolve_outputs.jsonl
RAW_SFT ?= data/sft/raw_self_sft_train.jsonl
SE_SFT ?= data/sft/squeeze_evolve_sft_train.jsonl

RAW_OUT_DIR ?= outputs/qwen3_4b_raw_sft
SE_OUT_DIR ?= outputs/qwen3_4b_se_sft

SE_DIR ?= external/squeeze-evolve
SE_CONFIG ?= configs/squeeze_evolve_generation.yaml

.PHONY: install test raw-generate convert-raw squeeze-generate convert-squeeze \
        train-raw train-squeeze eval-base eval-raw eval-squeeze help

help:
	@echo "Targets: install test raw-generate convert-raw squeeze-generate convert-squeeze"
	@echo "         train-raw train-squeeze eval-base eval-raw eval-squeeze"

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest

raw-generate:
	$(PYTHON) scripts/run_raw_generation.py \
		--input $(SEED) \
		--output $(RAW_GEN) \
		--model $(MODEL) \
		--base-url $(BASE_URL) \
		--api-key $(API_KEY) \
		--max-tokens 8192

convert-raw:
	$(PYTHON) scripts/convert_raw_to_sft.py \
		--input $(RAW_GEN) \
		--output $(RAW_SFT)

squeeze-generate:
	$(PYTHON) scripts/run_squeeze_evolve.py \
		--input $(SEED) \
		--output $(SE_GEN) \
		--config $(SE_CONFIG) \
		--squeeze-evolve-dir $(SE_DIR) \
		--model $(MODEL) \
		--base-url $(BASE_URL) \
		--api-key $(API_KEY)

convert-squeeze:
	$(PYTHON) scripts/convert_se_to_sft.py \
		--input $(SE_GEN) \
		--output $(SE_SFT)

train-raw:
	$(PYTHON) scripts/train_sft.py \
		--model-name-or-path $(MODEL) \
		--train-file $(RAW_SFT) \
		--output-dir $(RAW_OUT_DIR) \
		--use-lora \
		--bf16

train-squeeze:
	$(PYTHON) scripts/train_sft.py \
		--model-name-or-path $(MODEL) \
		--train-file $(SE_SFT) \
		--output-dir $(SE_OUT_DIR) \
		--use-lora \
		--bf16

eval-base:
	$(PYTHON) scripts/eval_math.py \
		--eval-file $(EVAL) \
		--model-name-or-path $(MODEL) \
		--output data/results/base_eval.jsonl

eval-raw:
	$(PYTHON) scripts/eval_math.py \
		--eval-file $(EVAL) \
		--model-name-or-path $(MODEL) \
		--adapter-path $(RAW_OUT_DIR) \
		--output data/results/raw_sft_eval.jsonl

eval-squeeze:
	$(PYTHON) scripts/eval_math.py \
		--eval-file $(EVAL) \
		--model-name-or-path $(MODEL) \
		--adapter-path $(SE_OUT_DIR) \
		--output data/results/se_sft_eval.jsonl
