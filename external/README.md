# external/

Third-party repositories that this project depends on but does **not**
vendor. The directory is checked in only as a pointer; everything inside
(other than this README and `.gitkeep`) is gitignored.

## Squeeze-Evolve

`scripts/run_squeeze_evolve.py` wraps the official Squeeze-Evolve CLI.
Clone the repo at:

    external/squeeze-evolve/

```bash
git clone --recurse-submodules \
    https://github.com/squeeze-evolve/squeeze-evolve.git external/squeeze-evolve
cd external/squeeze-evolve
pip install -e ".[dev]"
cd ../..
```

After install, verify the console script is on PATH:

```bash
which squeeze-evolve-client   # macOS / Linux
where squeeze-evolve-client   # Windows
```

The wrapper refuses to run if `external/squeeze-evolve/` is missing or
`squeeze-evolve-client` is not on PATH.

## How our wrapper invokes it

The real Squeeze-Evolve CLI takes **only** these flags:

    squeeze-evolve-client --config <yaml> --input <file> --output <file> [--n-problems N]

Model name / endpoint / API key are configured **inside the YAML**, not on
the command line. Our wrapper:

1. Loads the YAML at `--config`.
2. If `--model` / `--base-url` / `--api-key` are passed to the wrapper,
   splices them into every entry of `models:` (and `scoring_model:` if
   present), then writes a temp copy.
3. Converts our seed JSONL into the format the orchestrator's loader
   expects (`{orig_prompt, gt, question}` per line — the orchestrator
   builds `ProblemState` from these keys).
4. Calls `squeeze-evolve-client --config <patched> --input <converted>
   --output <raw.json>` with `cwd=external/squeeze-evolve` so the
   benchmark registries auto-discover.
5. Reads back the JSON (`{run_id, metrics, problems: [...]}`) and writes
   one JSONL line per seed with the `id`, original `question`, gold `gt`,
   chosen `final_response` (first candidate of the evolved population by
   default), and the full `candidates` list.

## Operator names

Bare `aggregate` / `synthesize` / `exact_match` / `none` are **not**
registered in upstream Squeeze-Evolve — every operator carries a
benchmark prefix. Our default config uses:

- `routing.recombination: aime25-aggregate` — generic math aggregator,
  produces a `\boxed{}`-aware prompt.
- `routing.evaluation: aime25-none` — disables per-loop eval (we evaluate
  separately with `scripts/eval_math.py`).

These operators register at CLI start-up because `cli.py` auto-discovers
`benchmarks/*/register.py` in the Squeeze-Evolve repo.

## Why `fitness: diversity` by default

A single-model run with `fitness: confidence` requires **either**
`prompt_logprobs > 0` on the served model **or** a separate
`scoring_model` with `vllm_extensions: true` (the forked vLLM in
`external/vllm`). For a self-distillation run on stock vLLM we use
`fitness: diversity`, which scores groups by unique-answer count and
needs no scoring backend at all. Switch to `fitness: confidence` only
after wiring up the vLLM fork or setting `prompt_logprobs: 20` on the
served model.

## Output schema (raw orchestrator JSON)

`squeeze-evolve-client --output X.json` writes a single JSON object:

```jsonc
{
  "run_id": "tts_sft_se_<hex>",
  "metrics": [ /* per-loop metrics */ ],
  "problems": [
    {
      "orig_prompt": "<the seed question>",
      "gt": "<gold answer or null>",
      "candidates": ["<final candidate 1>", "<final candidate 2>", ...],
      "candidate_groups": [...],
      "routing_details": { /* per-loop routing telemetry */ },
      "question": "<copy of question metadata, optional>",
      "options": null
    }
  ]
}
```

Our wrapper rewrites this into one JSONL line per seed; see the example
shown in the project README.
