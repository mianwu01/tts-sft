# Node 1 — SqueezeEvolve Reachability Results

Consolidated results for the Node 1 SqueezeEvolve (SE) reachability experiments. Standalone summary;
the running status log is `docs/NODE1_STATUS.md` (§11–§15). Generated 2026-06-06.

> **TL;DR.** Under matched compute accounting (`N_i = population × loops`, verified), SqueezeEvolve's
> **loop-1 recombination reaches a few hard problems that initial sampling (and independent N=8) miss**
> — but **additional loops (3, 4) add no further reach, only density**, and the genuinely-hardest tail
> stays unreached at every loop count. All SE-vs-independent numbers below are **vs the N=8 calibration
> and are NOT compute-matched** — the decisive matched comparison (independent N=N_i) is Node 2's.

---

## 1. Setup (constant across all runs)

- **Model:** `Qwen/Qwen3-4B-Thinking-2507` (local HF snapshot).
- **Engine:** official SqueezeEvolve (`squeeze-evolve-client`); thin wrapper `scripts/run_squeeze_evolve.py`.
- **Serving:** vLLM **tensor-parallel-size 8 @ max_model_len 262144** (8× A100-80GB). *Required:* with
  `strip_think=false`, loop-≥1 recombination packs k=4 full parent traces; hard problems max the 32768
  cap, so k=4 recombination ≈ 158k tokens — **overflows 131072**; 262144 is the working setting.
- **SE params:** `population=16, groups=16, k=4, fitness=diversity, temperature=0.6, top_p=0.95,
  max_tokens=32768, strip_think=false, update=replace, recombination=aime25-aggregate`.
- **Effective sampling — BOTH arms, verified from vLLM per-request `SamplingParams` logs (3,400+ requests):**
  `temperature=0.6, top_p=0.95, top_k=20, min_p=0, presence/frequency_penalty=0, repetition_penalty=1.0,
  max_tokens=32768, seed=None`. vLLM runs `generation_config=auto`, so Qwen3's `generation_config.json`
  (`temp 0.6, top_k 20, top_p 0.95`) supplies any field the request omits; neither client sets top_k →
  **top_k=20 (NOT disabled)**. SE and BoN are sampling-matched; only N and evolution-vs-independent differ.
- **Grading:** repo exact-match (`src/tts_sft/answer_extraction.py`), any-of-N. **SE-all** = any of the
  `N_i` candidates across all loops correct; **SE-final** = any of the 16 final-population candidates.

## 2. Budget rule — VERIFIED

`N_i = population × loops` (one generation per candidate per loop; `model_0_count`=16 every loop). Verified
empirically on 1 easy problem (`configs/budget_check_loops{1,2,3}.yaml`) and reproduced by `se_budget.py`
(`FROM_RAW_METRICS`) on **every** run below:

| loops | per-loop model_0_count | N_i | se_budget |
|---|---|---|---|
| 1 | [16] | 16 | 16 ✓ |
| 2 | [16,16] | 32 | 32 ✓ |
| 3 | [16,16,16] | 48 | 48 ✓ |
| 4 | [16,16,16,16] | 64 | 64 ✓ |
| 5 | [16,16,16,16,16] | 80 | 80 ✓ |

→ **Node 2 compute-matched N: loops=2 → N=32, loops=3 → N=48, loops=4 → N=64, loops=5 → N=80** (population=16).

## 3. Runs & headline results

| run | dataset | loops | N_i | runtime | SE-all | SE-final | output dir |
|---|---|---|---|---|---|---|---|
| First-5 pilot | AIME25 first-5 (easy-ish) | 2 | 32 | ~16 min | **5/5** | 5/5 | `outputs/node1_se_loop2_reachability_pilot/` |
| AIME hardtail | AIME25 7 non-easy | 2 | 32 | ~50 min | **4/7** | 4/7 | `outputs/node1_se_loop2_aime25_hardtail7/` |
| Stage A | HMMT25 13 non-easy | 2 | 32 | ~87 min | **6/13** | 6/13 | `outputs/node1_se_loop2_hmmt25_reachability13/` |
| Stage B | full 20 (7 AIME + 13 HMMT) | 3 | 48 | ~158 min | **10/20** | 8/20 | `outputs/node1_se_loop3_reachability20/` |
| loops=4 | 10 unsolved-at-loops3 | 4 | 64 | ~82 min | **0/10** | 0/10 | `outputs/node1_se_loop4_unsolved10/` |
| loops=5 | same 10 unsolved | 5 | 80 | ~88 min | **1/10** | 1/10 | `outputs/node1_se_loop5_unsolved10/` |

Every run: rc=0, no timeouts; no overflow once on 262144. Per-candidate metadata fully saved (loop_index,
full_response, thinking_trace, final_answer, parent_ids/lineage, fitness, routing, raw_candidate); the only
gaps are `thinking_trace`/`final_answer` on generations that hit the 32768 cap (full output always saved).

### Stage B (full 20, loops=3) — by dataset / bucket
- **By dataset:** AIME **4/7**, HMMT **6/13**. **By bucket:** medium **8/9**, hard **2/11**.
- **Solved (10):** AIME 000009, 000019, 000027, 000029; HMMT 000005, 000007, 000012, 000014, 000023, 000028.
- **Unsolved (10):** AIME 000012, 000013, 000014; HMMT 000013, 000016, 000017, 000018, 000019, 000024, 000029.

## 4. Reachability findings

1. **Recombination reaches a hard tail that sampling misses.** Two HARD problems with **independent N=8 =
   0/8** were solved by SE, and in both the correct answer **first appeared at loop 1 (recombination), with
   loop-0 initial sampling at 0/16**:
   - `aime25-000027` — loop0 0 → loop1 4 → loop2 9 (Stage B).
   - `hmmt25-000028` — loop0 0 → loop1 3/4 (Stage A/B).
   This is the candidate evidence for *"evolutionary TTS reaches solution space independent sampling cannot."*
2. **More loops do NOT extend reach — only density.** `new-at-loop2 = 0` (Stage B) and `new-at-loop3 = 0`
   (loops=4): loops 3 and 4 solved **no** problem that earlier loops missed; they only raised the number of
   correct candidates on already-solvable problems (e.g. aime000019 2→11→14). loops=3 solved the **exact same
   10/20** as loops=2 (reproducible). **loops=4 on the hard tail: 0/10; loops=5: 1/10** — but that single
   solve (`hmmt25-000024`, a *borderline* problem: indep N=8 = 1/8) appeared at **loop 1** (l1=5→l4=10) and
   was **0/64 in the loops=4 run** — i.e. **run-to-run sampling variance on a borderline problem, NOT a
   5th-loop effect**. The 9 genuinely-hard (indep 0/8) problems stayed **0/80** across all 5 loops. Net: extra
   loops never add reach beyond loop 1; comparing loops=4(0/10) vs loops=5(1/10) across separate runs conflates
   loop count with sampling variance.
3. **The genuinely-hardest tail is unreached at any budget.** ~9 hard problems (indep 0/8) stayed 0 across
   all loops and all N_i — recombination cannot manufacture a correct solution with no correct parent.
4. **SE is strong on medium, weak on hard:** Stage B medium 8/9 vs hard 2/11.

## 5. Caveats (important)

- **NOT compute-matched.** All SE-vs-independent comparisons here are SE (N=32/48/64) vs the **N=8**
  calibration. The decisive test is independent **N = N_i** (Node 2). Until then, every "SE reaches X that
  sampling can't" is **RESULT-DEPENDENT** — independent N=N_i might also reach it.
- **Exact-match undercounts.** No symbolic equivalence. Complex-form golds (radicals/fractions/factorials,
  e.g. `\sqrt{23}-2\sqrt{3}`, `\frac{448}{3}`, `2^{25}\cdot 26!`) are prone to false negatives, so the
  "unsolved" counts are **lower bounds** — e.g. `hmmt25-000024` is indep N=8 1/8 but SE 0/64. **Recommend a
  `math_verify`/symbolic recheck** before treating the hard-tail 0s as final.
- Loop ceiling = **5** (loops=5 is the last allowed; not exceeded).

## 6. Node 2 — compute-matched independent commands (per run; temperature 0.6)

```bash
# Stage A (HMMT13, loops=2 -> N=32)
python scripts/run_independent_rollouts.py --input data/seeds/hmmt25_seed_reachability13.jsonl \
  --output outputs/node2_independent_loop2_matched/independent_hmmt25_reachability13_N32.jsonl \
  --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY \
  --n-samples 32 --temperature 0.6 --top-p 0.95 --max-tokens 32768 --seed 1234

# Stage B (full20, loops=3 -> N=48)
python scripts/run_independent_rollouts.py --input data/seeds/reachability20_seed.jsonl \
  --output outputs/node2_independent_loop3_matched/independent_reachability20_N48.jsonl \
  --model Qwen/Qwen3-4B-Thinking-2507 --base-url http://localhost:8000/v1 --api-key EMPTY \
  --n-samples 48 --temperature 0.6 --top-p 0.95 --max-tokens 32768 --seed 1234
```
Then `scripts/eval_reachability.py` (SE vs independent, with each run's `se_budget.jsonl`). The key check:
does independent N=48 **also** reach `aime25-000027` and `hmmt25-000028`? If not → confirmed reachability win.

## 7. Files (per run, under each output dir)
`se.jsonl` (normalized, 16 final candidates/problem) · `se.jsonl.raw.json` · `se.jsonl.checkpoints/<run>_loop<t>.json`
(every loop) · `se.jsonl.loop_candidates.jsonl` (flattened every-loop candidates, full traces + metadata) ·
`se_budget.jsonl` (per-problem N_i). Seeds in `data/seeds/`, configs in `configs/`.

### loops=5 (ceiling) — unsolved-10
rc=0, ~88 min, N_i=80 (all 10, FROM_RAW_METRICS), 800 candidates (160/loop), full_response 800/800,
final_answer 752/800, no overflow. **SE-all 1/10** — only `hmmt25-000024` (borderline, indep 1/8; solved at
loop 1, run variance vs the loops=4 0/64). The 9 truly-hard (indep 0/8) problems: **0/80**. **Loop ceiling
reached — loops=5 is the last run; loops>5 will not be run.**

**Overall conclusion (loops 2→5):** SqueezeEvolve's reachability gain is concentrated at **loop 1
(recombination)** — it reaches a few hard problems (`aime25-000027`, `hmmt25-000028`; both indep 0/8) that
initial sampling and indep N=8 miss. Loops 3/4/5 add **density, not reach**; the genuinely-hardest tail is
unreached at every loop count. ⚠️ Still **vs N=8, not compute-matched** — Node 2's independent N=N_i runs are
required to confirm, and a `math_verify` recheck is advised for the complex-gold hard tail.

## 8. Context-overflow preflight for a max_tokens=65536 run (2026-06-07)

Goal: pick k for a 65k SE run without overflowing `max_model_len=262144` (loop1 prompt must be ≤ 196608).
Ran **loop-0 only** on hard11 (`configs/squeeze_evolve_context_preflight_loop0_hard11.yaml`, pop16, loops1,
temp1.0, top_p0.95, top_k20, max_tokens65536, strip_think=false; output `outputs/node1_context_preflight_loop0_hard11_max65536_temp1/`),
then tokenized loop-0 candidates with the official `aime25-aggregate` operator + Qwen chat template and computed
loop-1 prompt sizes over all C(16,k) groups (additive model validated vs exact: Δ≤+4 tok). At 65536 cap, loop-0
candidates were **22k–65k tok (mean 36.3k)** — several problems are cap-bound (hmmt25-000028 hits the full 65536).

| variant | overflow (all C(16,k)×11) | selected 16/prob | loop1 prompt mean / p90 / p95 / max | verdict |
|---|---|---|---|---|
| **A. k=4, strip_think=false** | **1410/20020 (7.0%)** | 11/176 (6.2%) | 145k / 183k / **207k** / 254k | **OVERFLOWS** — fails |
| **B. k=2, strip_think=false** | **0/1320 (0%)** | 0/176 | 73k / 93k / 105k / **130k** | **SAFE** (66k headroom) |
| **C. k=4, strip_think=true** | 0/20020 (0%) | 0/176 | 5.5k / 5.9k / 6.7k / 72k | safe but drops parent reasoning |

Overflow in A is driven by **cap-bound parents**: hmmt25-000028 (parent max 65536 → 1338/1820 groups overflow,
max prompt 253,840) and aime25-000027 (72/1820); the other 9 problems don't overflow at k=4. SE does not skip
over-length requests, so loop1 would 400-crash on those.

**Decision: use k=2, strip_think=false for the 65k run** — zero overflow, preserves full parent reasoning
(preferred over strip_think=true per the criteria). Note: even at 65536, hmmt25-000028 still maxes the cap, so
65k doesn't fully remove truncation for the most extreme problems (separate from the k choice).
