#!/usr/bin/env python3
"""P1 step 1: model-proposed PROBE INPUTS per problem (INPUTS ONLY — no outputs are ever requested,
stored, or shown; probe inputs are used solely for cross-candidate DISAGREEMENT detection, so they
carry no correctness labels and cannot leak hidden-test information).

One call per problem, cached to data/filtered/lcbv6_probe_inputs.jsonl {id, probe_inputs:[str,...]}.
Inputs deduped against the problem's public inputs (running on those is uninformative for all_pass
candidates — they already agree there).
"""
from __future__ import annotations
import argparse, json, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

PROMPT = """You are given a competitive programming problem and its example test inputs. Propose {k} ADDITIONAL test inputs for this problem.

Rules:
- Inputs ONLY. Do NOT compute or write any outputs.
- Every input must be VALID under the problem's constraints.
- Explore edge cases: minimum sizes, boundary values, ties/duplicates, tricky structures, small adversarial cases.
- Keep each input small (prefer the smallest inputs that exercise an edge case).
- Format each input EXACTLY like the example inputs shown below.
- Output exactly {k} inputs, each in its own fenced block: ```input
<the input>
```

Problem:
{problem}

Example test inputs (format reference):
{examples}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=_REPO / "data/filtered/lcbv6_probe_inputs.jsonl")
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Thinking-2507")
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--concurrency", type=int, default=24)
    ap.add_argument("--limit", type=int, default=None, help="only first N problems (smoke)")
    args = ap.parse_args()

    seeds = [json.loads(l) for l in (_REPO / "data/filtered/lcbv6_non_saturated.jsonl").open()]
    public = {json.loads(l)["id"]: json.loads(l) for l in (_REPO / "data/filtered/lcbv6_public_tests.jsonl").open()}
    if args.limit:
        seeds = seeds[: args.limit]
    done = {}
    if args.out.exists():
        for l in args.out.open():
            r = json.loads(l); done[r["id"]] = r
    todo = [s for s in seeds if s["id"] not in done]
    print(f"{len(todo)} problems to generate ({len(done)} cached)", flush=True)

    from openai import OpenAI
    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=7200)
    sem = threading.Semaphore(args.concurrency)
    lock = threading.Lock()

    def gen(s):
        pid = s["id"]
        pub = json.loads(public[pid]["public_tests"]); pub_inputs = [str(x) for x in pub["inputs"]]
        examples = "\n\n".join(f"```input\n{x}\n```" for x in pub_inputs[:3])
        prompt = PROMPT.format(k=args.k, problem=s["problem"], examples=examples)
        for attempt in range(4):
            try:
                with sem:
                    r = client.chat.completions.create(model=args.model,
                        messages=[{"role": "user", "content": prompt}], temperature=args.temperature,
                        top_p=0.95, max_tokens=args.max_tokens, seed=1234, extra_body={"top_k": 20})
                text = r.choices[0].message.content or ""
                break
            except Exception:  # noqa: BLE001
                time.sleep(min(20, 2 ** attempt)); text = ""
        blocks = re.findall(r"```input\s*\n(.*?)```", text, re.DOTALL) or re.findall(r"```\s*\n(.*?)```", text, re.DOTALL)
        pubset = {x.strip() for x in pub_inputs}
        inputs, seen = [], set()
        for b in blocks:
            b = b.strip("\n").rstrip()
            if b and b.strip() not in pubset and b not in seen:
                seen.add(b); inputs.append(b)
        rec = {"id": pid, "n": len(inputs), "probe_inputs": inputs[: args.k]}
        with lock:
            with args.out.open("a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return pid, len(inputs)

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        got = list(ex.map(gen, todo))
    import collections
    print("per-problem probe-input counts:", dict(collections.Counter(n for _, n in got)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
