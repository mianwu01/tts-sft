# Node 2 Reachability diagnostic — results

**Question:** under *matched compute*, does SqueezeEvolve (evolutionary test-time scaling) reach
solutions that ordinary independent sampling from the same base model cannot?

**Status:** **COMPLETE** as of 2026-06-06 ~10:16. All matched evals done — loops 2/3 on the full20
subset; loops 4/5 on the **10-problem hard subset** Node 1 targeted (`node1_se_loop{4,5}_unsolved10`:
the 9 hard-core problems + `hmmt25-000024`). All numbers measured from generated logs (`RESULT-DEPENDENT`).

> **Bottom line:** across **all** budgets (loops 2→5, N=32→80), incl. the loops-5 ceiling focused on the
> hardest problems, **SqueezeEvolve solved ZERO problems that independent sampling could not** at matched
> compute (`only_se` = 1 only at loops-2, and that one was tail noise that became `both` at N=48). The 9
> hard-core problems are `neither`-solved by both arms at every budget (cap-bound). **The reachability
> hypothesis is not supported.** SE's only robust edge is *depth* (solve-rate on already-solvable problems).

---

## 1. Setup

- **Model:** `Qwen/Qwen3-4B-Thinking-2507`, served on local vLLM (8 single-GPU replicas).
- **Matched decoding (both arms):** `temperature=0.6, top_p=0.95, max_tokens=32768`, seed 1234.
- **Budget rule** (verified by Node 1 for loops 1/2/3 = 16/32/48): `N_i = population(16) × loops`.
  Ladder: loops 2→**N=32**, 3→**N=48**, 4→**N=64**, 5→**N=80** (loops=5 is the ceiling).
- **Arms, per problem:** SE = *all* SqueezeEvolve generations across every loop (loop0+loop1+… =
  N_i), regrouped from `loop_candidates.jsonl` via `scripts/group_se_loop_candidates.py`; Independent
  = N_i independent rollouts (`scripts/run_independent_rollouts_dp.py`).
- **Grader:** corrected exact-match (`src/tts_sft/answer_extraction.py` + the §8b LaTeX-aware fix:
  strips `\left`/`\right`, unwraps `\boxed{}`, drops spacing commands, ignores whitespace). No
  symbolic equivalence (`math_verify` not installed).
- **Category per problem (any-of-N):** `both_solved | only_se_solved | only_independent_solved | neither_solved`.
  Identities enforced: `total = both+only_se+only_ind+neither`, `SE_any = both+only_se`, `ind_any = both+only_ind`.
- **Problem set:** a 20-problem hard/medium subset chosen by N=8 calibration over AIME25 + HMMT25
  (7 AIME + 13 HMMT; 11 hard@0/8, 9 medium@1–5/8). The earlier first-5 AIME pilot was at ceiling and
  is excluded. Buckets are from calibration.

---

## 2. Headline finding

At matched compute on this hard subset, **SqueezeEvolve does NOT expand the reachable solution set.**
Categorical reachability is **neutral → slightly negative** for SE (only_se 1→0, only_ind 1→2 as the
budget grows from N=32 to N=48), and the few `only_X` outcomes are **tail noise** — they sit at ~1–5/N
solve rates and flip between runs (e.g. loop2's lone `only_se` `aime25-000029` became `both` at N=48;
the loop3 `only_ind` `aime25-000013` was 1/48 → 0/64). The sharp claim *"evolution reaches solutions
independent sampling cannot at matched compute"* is **not supported** by these data.

**However, SqueezeEvolve has a robust *depth* advantage:** on problems both arms solve, SE produces
correct solutions far more often — **~1.8×** the per-problem solve count (loop3 N=48 mean 14.5 vs 8.0
out of 48; SE > independent on 8 of 10 co-solved). The genuinely hard problems are `neither`-solved at
every budget (cap-bound — the model exhausts the 32768-token budget).

**Implication for self-distillation:** SE's value is likely a **higher yield of correct traces**
(more/cleaner positive examples per problem), not novel reach — directly testable in the SFT stage.

---

## 3. Matched reachability results (SE-all-N vs independent-N)

| eval | total | both | only_se | only_ind | neither | SE any-of-N | indep any-of-N |
|---|---|---|---|---|---|---|---|
| AIME hardtail7, loops=2, **N=32** | 7 | 3 | 1 | 0 | 3 | 4/7 | 3/7 |
| HMMT13, loops=2, **N=32** | 13 | 6 | 0 | 1 | 6 | 6/13 | 7/13 |
| **loop2 combined (20), N=32** | 20 | 9 | **1** | **1** | 9 | **10/20** | **10/20** |
| full20, loops=3, **N=48** | 20 | 10 | **0** | **2** | 8 | 10/20 | 12/20 |

*(An earlier text report mis-stated the loop2-combined any-of-N as 13/14; corrected to 10/10 — see
NODE2_STATUS §8f. All rows satisfy the identities above.)*

### Budget ladder (full20, any-of-N)

| N | budget | scope | SE any-of-N | indep any-of-N | only_se | only_ind | neither |
|---|---|---|---|---|---|---|---|
| 32 | loops 2 | full20 | 10/20 | 10/20 | **1** | 1 | 9 |
| 48 | loops 3 | full20 | 10/20 | 12/20 | **0** | 2 | 8 |
| 64 | loops 4 | 10-hard\* | **0/10** | 1/10 | **0** | 1 | 9 |
| 80 | loops 5 (ceiling) | 10-hard\* | **1/10** | 1/10 | **0** | 0 | 9 |

\* Node 1 scoped the loops-4/loops-5 SE runs to the **10 hardest problems** (`node1_se_loop{4,5}_unsolved10`):
the 9 hard-core `neither` problems (`aime25-000012/000013/000014`,
`hmmt25-000013/000016/000017/000018/000019/000029`) + the edge medium `hmmt25-000024`. The full20
independent any-of-N (for reference) plateaus at 11/20 through N=80 (N=48's 12 was a tail-noise peak).

**`only_se` is 0 at every budget except loops-2 (where it was 1, a tail-noise case that became `both` at
N=48).** On the 9 hard-core problems, BOTH arms score 0 at N=64 and N=80 — SqueezeEvolve's evolution
(even at the loops-5 ceiling, focused only on these problems) reaches none of them. They are cap-bound
(the 4B model can't produce a correct solution within the 32768-token budget), so search strategy can't
help. The one SE movement: `hmmt25-000024` went SE 0/64 → **35/80** across the extra loop (a depth jump),
but independent also solves it (2/80) → `both`, not reach.

---

## 4. Per-problem detail

### full20, loops=3, N=48 (the decisive completed eval)

| id | ds | bucket | SE/48 | ind/48 | category |
|---|---|---|---|---|---|
| aime25-000019 | AIME | medium | 27 | 12 | both |
| aime25-000009 | AIME | medium | 26 | 14 | both |
| aime25-000029 | AIME | medium | 18 | 5 | both |
| aime25-000027 | AIME | hard | 13 | 2 | both |
| hmmt25-000007 | HMMT | medium | 29 | 23 | both |
| hmmt25-000005 | HMMT | medium | 13 | 10 | both |
| hmmt25-000012 | HMMT | medium | 10 | 3 | both |
| hmmt25-000028 | HMMT | hard | 4 | 2 | both |
| hmmt25-000014 | HMMT | medium | 3 | 6 | both |
| hmmt25-000023 | HMMT | medium | 2 | 3 | both |
| aime25-000013 | AIME | hard | 0 | 1 | only_ind |
| hmmt25-000024 | HMMT | medium | 0 | 2 | only_ind |
| aime25-000012, aime25-000014, hmmt25-000013/000016/000017/000018/000019/000029 | — | hard | 0 | 0 | neither (×8) |

### AIME hardtail7, loops=2, N=32 (the one `only_se`)

`aime25-000029` (medium): SE 11/32 vs independent **0/32** → `only_se_solved` at N=32. (At N=48 independent
caught it 5/48 → `both`; an illustration of the tail-noise nature of `only_X`.)
Others: `000009` (14 vs 7), `000019` (23 vs 9), `000027` (4 vs 3) = both; `000012/000013/000014` = neither (cap-bound).

### Independent-only, N=64 (interim; SE eval pending)

any-of-64 = **11/20** (all 9 medium + 2 hard `aime25-000027`, `hmmt25-000028`); the 9 hard-core
problems stay 0/64. Runs are *independent re-draws, not nested* (vLLM concurrent batching is numerically
nondeterministic at fixed seed), so any-of-N can wobble ±1 on edge problems.

---

## 5. Caveats

- **Tiny n (20 hard problems)** — directional, not statistically powered.
- **`only_X` are tail noise** — ~1–5/N solve rates flip between runs; not robust reachability gaps.
- **Cap-bound hard problems** — several `neither` problems hit the 32768-token cap on most/all samples
  (model never finishes); neither arm can solve them at this budget. (`aime25-000013/000027`,
  `hmmt25-000028` were 8/8 cap-hit at N=8.)
- **Non-nested runs** — different-N runs are not strict supersets (see N=64 note), so any-of-N is
  not guaranteed monotone in N.
- **Grader is format-sensitive** — several HMMT golds are non-integer (`\frac`, `\sqrt`, `2^{25}`);
  the LaTeX fix is active but `math_verify` would be a stronger check.
- **SE arm = all generations across loops** (the compute-matched view), not the final population only.

---

## 5b. Length probe — was the 32768 cap the cause of the hard-tail failures? (2026-06-06)

BoN-only diagnostic on the 11 hardest problems (9 hard-core + 2 controls `aime25-000027`,
`hmmt25-000028`), re-running independent sampling at **max_tokens=65536** (vLLM `max_model_len=131072`,
same temp 0.6 / top_p 0.95 / **top_k 20**). Phase 1 N=8 + Phase 2 N=16; no SqueezeEvolve.

- **The 32768 cap WAS truncating all 11.** At 32k (N=80): cap-hit **32–96%**, high no-answer. At 64k:
  **cap-hit 0%**, final-answer **100%** — the model finishes when given room (these need ~33k–63k tokens).
- **Two regimes emerge:** (a) **truncation-limited & solvable** — the 2 controls jump from ~6% (5/80 @32k)
  to **`aime25-000027` 9/16, `hmmt25-000028` 6/16 @64k**; (b) **capability-limited** — the **9 hard-core
  still 0/16 at 64k** (complete-but-wrong; same 4B model can't solve them even with full reasoning).
- **⇒ the earlier "neither/cap-bound" result on the hard problems was confounded by the 32k cap.** A fair
  reachability comparison must use long context. But chasing the 9 via SE is likely futile (capability, not length).

**max_tokens sizing (from the 64k logs, N=16 = 176 samples):** correct traces reach **55,247 tokens**;
aggregate p95 ≈ 50.7k, max 62,977 (one sample hit the 65,535 cap).
- **49152 (48k):** clips ~half the control solves (correct traces up to 51,203) — **unsafe**.
- **52000 (52k):** abandons **0** problems (no problem loses *all* solves), but clips **3/15 correct samples**
  (52,138 / 54,598 / 55,247) on 2 problems → undercounts solve-rate; **−3,247 margin** vs longest correct trace.
- **65536 (64k):** captures all observed correct traces (≤55,247) — **use this.**

**Recommended SE long-context setting: (B) max_tokens=65536, k=2, strip_think=false, max_model_len=262144**
(no truncation; k=2 keeps 2 full-`<think>` parents + gen ≈197k < 262144). (A) 49152/k=4 re-truncates real
solves; (C) 65536/k=4/strip_think=true is the k=4 fallback but strips the reasoning SE recombines.

Files: `outputs/node2_length_probe/independent_hard11_N{8,16}_max65536.jsonl`; seed
`data/seeds/length_probe_hard11.jsonl`.

## 5c. Calibration to drop saturated-easy problems (N=16, temp=1.0, 2026-06-07)

BoN-only calibration of **full AIME (30)** + **HMMT (30)** at **N=16, max_tokens=32768, temperature=1.0,
top_p=0.95, top_k=20** (logged per-sample tokens + finish_reason via `scripts/calib_bon_dp.py`). Buckets:
saturated_easy (16/16), informative (1–15), hard_zero (0 with clean completion: cap-hit≤25% & answer-rate≥75%),
bad_truncated_or_bad_format (0 with high cap-hit or low extraction).

| dataset | saturated_easy | informative | hard_zero | bad | non_saturated (default) |
|---|---|---|---|---|---|
| AIME (30) | 12 | 15 | 0 | 3 | **18** |
| HMMT (30) | 9 | 12 | 3 | 6 | **21** |

cap-hit: AIME 101/480 (21%), HMMT 124/480 (26%). Mean answer-rate: AIME 0.88, HMMT 0.89. Output tokens:
AIME 10.3M, HMMT 11.8M (≈22.3M total).

⚠️ **Truncation confound:** at max_tokens=32768 the `bad`/`hard_zero` (0-correct) buckets are dominated by
the 32k cap (the length probe §5b proved e.g. `aime25-000012/13/14`, `hmmt25-000012/13/16/17` need >32k and
finish at 64k). So **0-correct ≠ unsolvable here.** The **saturated_easy** removal is clean and robust
(those solve 16/16 with low token counts and **0% cap-hit** — genuinely easy & short). The hard_zero-vs-bad
split is *not* reliable at 32k. ⇒ **`*_non_saturated` is the safe default** — it removes only the 12+9 trivially-easy
and KEEPS the truncation-limited problems (which `*_informative` would wrongly drop). For the expensive comparison,
pair non_saturated with the higher max_tokens from §5b. (Also: calibrated at temp 1.0, but the SE/BoN comparison
runs at 0.6 — a hotter calibration.)

Files: `data/filtered/{aime,hmmt}_{full,non_saturated,informative,hard_zero_clean}.jsonl`;
`outputs/node2_calibration/calib_temp1_{per_problem,per_generation}.jsonl`;
`outputs/node2_calibration_{aime,hmmt}_N16_32k_temp1.jsonl`.

## 6. Files

Independent rollouts:
- `outputs/node2_independent_loop2_matched/independent_{aime25_hardtail7,hmmt25_reachability13}_N32.jsonl`
- `outputs/node2_independent_loop3_matched/independent_reachability20_N48.jsonl`
- `outputs/node2_independent_loop4_matched/independent_reachability20_N64.jsonl`
- `outputs/node2_independent_loop5_matched/independent_reachability20_N80.jsonl` *(done; any-of-80 = 11/20)*

Grouped SE (SE-all) + reachability eval outputs:
- `outputs/node2_reachability_loop2/{se_all_*_N32.jsonl, reach_*_SEall32_vs_ind32.{per_problem.jsonl,summary.json}}`
- `outputs/node2_reachability_loop3/{se_all_reachability20_N48.jsonl, reach_*_SEall48_vs_ind48.{per_problem.jsonl,summary.json}}`
- `outputs/node2_reachability_loop4/`, `outputs/node2_reachability_loop5/` *(pending Node 1 SE)*

Calibration + subset:
- `outputs/node2_calibration/{calibration_summary_N8.jsonl, calibration_buckets_N8.json, recommended_reachability_subset.jsonl}`

Tooling: `scripts/{run_independent_rollouts_dp.py, group_se_loop_candidates.py, eval_reachability.py, calibrate_difficulty.py}`
(+ tests). Full operational log: `docs/NODE2_STATUS.md` (§8b evaluator fix, §8c–§8g runs).

**No SqueezeEvolve / SFT / RL was run by Node 2 — independent sampling only; Node 1 outputs read-only.**
