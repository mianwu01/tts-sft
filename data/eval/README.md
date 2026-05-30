# data/eval/

Held-out math problems used by `scripts/eval_math.py`.

## Format (JSONL)

```json
{"id": "eval_000001", "question": "...", "answer": "REQUIRED"}
```

`answer` is required for evaluation files — it is the gold target used to
score the model's response with exact match (after normalization).

## Files here

- `sample_eval.jsonl` — toy eval set used in CI / smoke tests.
- For real comparisons, drop your benchmark in alongside (e.g.
  `aime_2024.jsonl`, `hmmt_feb_2024.jsonl`).

## Scoring

`scripts/eval_math.py` extracts the model's final answer (preferring the
last `\boxed{...}`) and applies `normalize_math_answer` before comparing.
This is intentionally shallow — no symbolic equivalence in v1.
