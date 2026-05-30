# data/seeds/

Math seed questions used for **data generation** (both raw self-generation
and SqueezeEvolve).

## Canonical format (JSONL)

```json
{"id": "000001", "question": "...", "answer": "optional"}
```

- `id` (str): unique identifier within the file. Zero-padded integers are
  fine, but any stable string works.
- `question` (str): the math problem statement.
- `answer` (str, optional): reference answer. Not required for training
  seeds; required for evaluation files (see `data/eval/`).

## Files here

- `sample_math_seed.jsonl` — 8 toy problems for smoke-testing the pipeline.
- Drop your real seed set in as e.g. `math_seed.jsonl` and reference it from
  `configs/raw_generation.yaml` or via the script's `--input` flag.

## Preparing your own seeds

`scripts/prepare_math_seed.py` converts arbitrary JSON/JSONL into this
canonical layout — point `--question-field` / `--answer-field` at the
source columns.
