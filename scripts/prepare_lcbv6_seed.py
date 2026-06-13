#!/usr/bin/env python3
"""Build the LCBV6 (LiveCodeBench v6 window) seed + full-benchmark JSONL.

Faithfully reuses the official `livecodebench/code_generation_lite` dataset and
the test-decoding / prompt logic from the colleague's read-only reference
(`/mnt/cpfs/yangboxue/wujunyi/opd_references/nano-opd/nanoopd/data/livecodebench.py`).
We COPY the small standalone helpers here (we never import or modify the
read-only tree).

LCBV6 := test split (contest_date >= 2025-02-01) filtered to contest_date < 2025-05-01,
which is exactly the colleague's `load_livecodebench("test", until=datetime(2025,5,1))`
(saved as datasets/lcb_v6/). Verified count == 131.

Generation uses the problem statement prompt ONLY (no tests) -> the seed `question`
field carries the CODE_PROMPT-formatted user message. The hidden (private) test suite
is stored in `tests` for OFFLINE evaluation only.

Outputs:
  data/seeds/lcbv6_seed.jsonl      one record/problem (id, question, tests, ...)
  data/filtered/lcbv6_full.jsonl   the full 131-problem benchmark (same content)

Offline-load env (this box): unset *_proxy; HF_ENDPOINT=https://hf-mirror.com;
HF_HUB_DISABLE_XET=1; VLLM_USE_MODELSCOPE=False; HF_HOME=<shared cache>.
"""
from __future__ import annotations

import argparse
import base64
import json
import pickle
import zlib
from datetime import datetime
from pathlib import Path

# Official LCB prompt (verbatim from the reference) ---------------------------
CODE_PROMPT = """You are a coding expert. You will be given a coding problem, and you need to write a correct Python program that matches the specification and passes all tests. The time limit is 1 second. You may start by outlining your thought process. In the end, please provide the complete code in a code block enclosed with ```.

{problem}"""

LCB_TEST_CUTOFF = datetime(2025, 2, 1)
LCB_V6_UNTIL = datetime(2025, 5, 1)
TIME_LIMIT = 6


def _parse_signature(starter_code: str) -> str:
    after_def = starter_code.split("def ")[1]
    return "def " + (after_def.split("Input\n")[0] if "Input\n" in after_def else after_def).strip()


def _translate_private_test_cases(encoded_data, fn_name: str) -> str:
    """Decode LCB private_test_cases (base64 -> zlib -> pickle -> json)."""
    decoded = base64.b64decode(encoded_data)
    decompressed = zlib.decompress(decoded)
    original = pickle.loads(decompressed)
    tests = json.loads(original)
    return json.dumps(
        {
            "inputs": [t["input"] for t in tests],
            "outputs": [t["output"] for t in tests],
            "testtype": tests[0]["testtype"],
            "fn_name": fn_name,
            "time_limit": TIME_LIMIT,
        },
        ensure_ascii=False,
    )


def _asdt(x) -> datetime:
    return x if isinstance(x, datetime) else datetime.fromisoformat(str(x))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--revision", default="refs/pr/6")
    ap.add_argument("--seed-out", type=Path, default=Path("data/seeds/lcbv6_seed.jsonl"))
    ap.add_argument("--full-out", type=Path, default=Path("data/filtered/lcbv6_full.jsonl"))
    args = ap.parse_args()

    from datasets import load_dataset

    ds = load_dataset(
        "livecodebench/code_generation_lite",
        split="test",
        revision=args.revision,
        trust_remote_code=True,
    )
    idx = [
        i
        for i in range(len(ds))
        if LCB_TEST_CUTOFF <= _asdt(ds["contest_date"][i]) < LCB_V6_UNTIL
    ]
    assert len(idx) == 131, f"expected 131 LCBV6 problems, got {len(idx)}"

    args.seed_out.parent.mkdir(parents=True, exist_ok=True)
    args.full_out.parent.mkdir(parents=True, exist_ok=True)

    records = []
    for n, i in enumerate(idx):
        ex = ds[i]
        problem = ex["question_content"]
        if ex["starter_code"].strip():
            problem += (
                "\n\nYour solution should have the following signature: "
                f"```python\n{_parse_signature(ex['starter_code'])}\n```"
            )
        fn_name = ""
        if ex["metadata"].strip():
            fn_name = json.loads(ex["metadata"]).get("func_name", "")
        tests = _translate_private_test_cases(ex["private_test_cases"], fn_name=fn_name)
        testtype = json.loads(tests)["testtype"]

        records.append(
            {
                "id": f"lcbv6-{n:03d}",
                "question_id": ex["question_id"],
                "dataset": "LCBV6",
                "platform": ex["platform"],
                "difficulty": ex["difficulty"],
                "contest_date": str(ex["contest_date"]),
                "starter_code": ex["starter_code"],
                "testtype": testtype,
                "fn_name": fn_name,
                # generation input: problem statement prompt ONLY (no tests)
                "question": CODE_PROMPT.format(problem=problem),
                "problem": problem,
                # hidden test suite for OFFLINE eval only
                "tests": tests,
            }
        )

    for path in (args.seed_out, args.full_out):
        with path.open("w") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_func = sum(r["testtype"] == "functional" for r in records)
    n_stdin = sum(r["testtype"] == "stdin" for r in records)
    print(f"wrote {len(records)} problems -> {args.seed_out} and {args.full_out}")
    print(f"  testtype: functional={n_func} stdin={n_stdin}")
    print("  difficulty: " + ", ".join(
        f"{d}={sum(r['difficulty']==d for r in records)}" for d in ("easy", "medium", "hard")
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
