# Node 2 — Parallel-A BoN on NON_SATURATED (results)

**Config:** independent Best-of-N, **N=80**, **max_tokens=32768**, temperature=1.0, top_p=0.95, **top_k=20**, seed=1234, Qwen3-4B-Thinking-2507. Fresh generation (no calibration reuse). Grading: AIME/HMMT corrected exact-match; LCBV6 hidden-test code executor (offline). 0 failed requests / 0 retries across all 13,200 generations.

Wall: AIME+HMMT+LCBV6 chained, 2026-06-07 11:13 → 2026-06-08 09:35 (~22.4h; first ~33min shared GPUs with a since-killed duplicate run). 8×A100, 8 single-GPU vLLM replicas @ max_model_len 40960, concurrency 48.

## Summary (Parallel-A N=80@32k)

| dataset | solved (any-of-80) | correct_traces | co-solved μ(/80) | answer/code-extract | cap-hit | input_tok | output_tok | total_tok |
|---|---|---|---|---|---|---|---|---|
| AIME (18) | 15/18 | 801/1440 (55.6%) | 53.4 | 1151/1440 (79.9%) | 516/1440 (35.8%) | 384,000 | 38,554,820 | 38,938,820 |
| HMMT (21) | 15/21 | 493/1680 (29.3%) | 32.9 | 1420/1680 (84.5%) | 658/1680 (39.2%) | 281,200 | 47,209,774 | 47,490,974 |
| LCBV6 (126) | 90/126 | 4079/10080 (40.5%) | 45.3 | 10065/10080 (99.9%) | 39/10080 (0.4%) | 5,662,320 | 141,550,051 | 147,212,371 |

**Math vs code (key contrast):** math arms are heavily truncation-bound at 32k (cap-hit AIME 35.8% / HMMT 39.2%), code is not (LCBV6 cap-hit 0.4%). So for math the 32k parallel arm leaves headroom that **Sequential-B (N=16@163840)** will test; for code, 32k is already near-complete, so Sequential-B is expected to add little on LCBV6.

## AIME non_saturated — per problem (N=80@32k)

| id | correct/80 | ans/80 | cap/80 | avg_tok |
|---|---|---|---|---|
| aime25-000012 | 0 | 41 | 57 | 31970 |
| aime25-000013 | 0 | 71 | 63 | 32222 |
| aime25-000014 | 0 | 53 | 42 | 30815 |
| aime25-000029 | 3 | 34 | 71 | 32494 |
| aime25-000027 | 7 | 41 | 74 | 32500 |
| aime25-000019 | 19 | 60 | 56 | 31753 |
| aime25-000009 | 25 | 63 | 40 | 30913 |
| aime25-000006 | 56 | 60 | 22 | 28890 |
| aime25-000028 | 57 | 71 | 9 | 23785 |
| aime25-000008 | 59 | 64 | 19 | 24000 |
| aime25-000017 | 63 | 68 | 17 | 26144 |
| aime25-000022 | 64 | 64 | 19 | 27860 |
| aime25-000010 | 66 | 71 | 14 | 27995 |
| aime25-000024 | 69 | 72 | 10 | 24277 |
| aime25-000011 | 77 | 78 | 2 | 22445 |
| aime25-000023 | 77 | 80 | 0 | 18840 |
| aime25-000001 | 79 | 80 | 1 | 16410 |
| aime25-000026 | 80 | 80 | 0 | 18621 |

## HMMT non_saturated — per problem (N=80@32k)

| id | correct/80 | ans/80 | cap/80 | avg_tok |
|---|---|---|---|---|
| hmmt25-000013 | 0 | 75 | 52 | 31801 |
| hmmt25-000016 | 0 | 56 | 60 | 31870 |
| hmmt25-000017 | 0 | 68 | 32 | 29152 |
| hmmt25-000018 | 0 | 74 | 29 | 29708 |
| hmmt25-000019 | 0 | 79 | 12 | 28739 |
| hmmt25-000029 | 0 | 80 | 22 | 29144 |
| hmmt25-000014 | 2 | 72 | 13 | 26690 |
| hmmt25-000028 | 2 | 34 | 77 | 32515 |
| hmmt25-000024 | 3 | 47 | 76 | 32705 |
| hmmt25-000023 | 4 | 56 | 49 | 31011 |
| hmmt25-000012 | 5 | 52 | 63 | 31699 |
| hmmt25-000005 | 22 | 80 | 1 | 23293 |
| hmmt25-000015 | 28 | 50 | 37 | 30305 |
| hmmt25-000007 | 33 | 80 | 10 | 26579 |
| hmmt25-000006 | 38 | 76 | 40 | 27809 |
| hmmt25-000010 | 38 | 65 | 19 | 28401 |
| hmmt25-000002 | 42 | 73 | 26 | 25758 |
| hmmt25-000009 | 52 | 68 | 30 | 29890 |
| hmmt25-000026 | 72 | 77 | 7 | 18330 |
| hmmt25-000008 | 74 | 80 | 1 | 22230 |
| hmmt25-000011 | 78 | 78 | 2 | 22491 |

## LCBV6 non_saturated — per problem (N=80@32k)

| id | correct/80 | code-extract/80 | cap/80 | difficulty | avg_tok |
|---|---|---|---|---|---|
| lcbv6-000 | 0 | 79 | 1 | medium | 25360.1 |
| lcbv6-004 | 0 | 78 | 2 | hard | 26731.7 |
| lcbv6-007 | 0 | 80 | 0 | hard | 17691.3 |
| lcbv6-019 | 0 | 80 | 0 | hard | 20231.0 |
| lcbv6-036 | 0 | 80 | 0 | hard | 10089.0 |
| lcbv6-039 | 0 | 79 | 1 | hard | 21771.6 |
| lcbv6-048 | 0 | 80 | 0 | hard | 17618.6 |
| lcbv6-049 | 0 | 80 | 0 | hard | 20155.0 |
| lcbv6-050 | 0 | 80 | 0 | medium | 21044.8 |
| lcbv6-060 | 0 | 80 | 0 | hard | 20446.3 |
| lcbv6-061 | 0 | 80 | 1 | hard | 26220.1 |
| lcbv6-062 | 0 | 80 | 0 | hard | 17542.3 |
| lcbv6-063 | 0 | 74 | 12 | hard | 28177.8 |
| lcbv6-064 | 0 | 80 | 0 | medium | 18298.4 |
| lcbv6-065 | 0 | 77 | 3 | hard | 24240.3 |
| lcbv6-067 | 0 | 80 | 0 | hard | 21223.7 |
| lcbv6-068 | 0 | 80 | 0 | hard | 13222.0 |
| lcbv6-072 | 0 | 80 | 0 | hard | 18249.4 |
| lcbv6-073 | 0 | 78 | 5 | hard | 27496.5 |
| lcbv6-075 | 0 | 80 | 0 | hard | 21395.4 |
| lcbv6-076 | 0 | 80 | 0 | hard | 20568.5 |
| lcbv6-078 | 0 | 80 | 0 | hard | 22312.0 |
| lcbv6-079 | 0 | 80 | 0 | hard | 20733.5 |
| lcbv6-080 | 0 | 80 | 0 | hard | 13727.1 |
| lcbv6-081 | 0 | 80 | 1 | hard | 25689.2 |
| lcbv6-088 | 0 | 80 | 0 | hard | 19202.7 |
| lcbv6-090 | 0 | 80 | 0 | medium | 15053.5 |
| lcbv6-091 | 0 | 80 | 0 | medium | 13551.7 |
| lcbv6-092 | 0 | 80 | 0 | hard | 21928.6 |
| lcbv6-095 | 0 | 80 | 0 | hard | 16476.2 |
| lcbv6-102 | 0 | 80 | 0 | hard | 22071.4 |
| lcbv6-106 | 0 | 80 | 0 | hard | 15873.4 |
| lcbv6-113 | 0 | 80 | 0 | hard | 21451.3 |
| lcbv6-118 | 0 | 80 | 0 | hard | 15677.2 |
| lcbv6-120 | 0 | 80 | 0 | medium | 12142.1 |
| lcbv6-124 | 0 | 80 | 0 | medium | 20808.0 |
| lcbv6-071 | 1 | 80 | 0 | medium | 21301.5 |
| lcbv6-066 | 2 | 80 | 0 | hard | 21757.2 |
| lcbv6-069 | 2 | 80 | 3 | hard | 25438.5 |
| lcbv6-056 | 4 | 80 | 0 | medium | 15374.9 |
| lcbv6-070 | 4 | 80 | 0 | hard | 19316.6 |
| lcbv6-074 | 5 | 80 | 0 | hard | 22182.5 |
| lcbv6-109 | 6 | 80 | 0 | medium | 21186.9 |
| lcbv6-017 | 7 | 80 | 0 | medium | 24113.6 |
| lcbv6-023 | 7 | 80 | 0 | hard | 22688.8 |
| lcbv6-031 | 7 | 80 | 8 | hard | 25985.0 |
| lcbv6-001 | 8 | 80 | 0 | hard | 16435.5 |
| lcbv6-105 | 8 | 80 | 0 | medium | 14672.8 |
| lcbv6-087 | 9 | 80 | 1 | hard | 23795.0 |
| lcbv6-009 | 10 | 80 | 0 | medium | 8168.1 |
| lcbv6-033 | 10 | 80 | 0 | hard | 14430.6 |
| lcbv6-010 | 13 | 80 | 0 | hard | 19480.8 |
| lcbv6-127 | 14 | 80 | 0 | hard | 20057.6 |
| lcbv6-099 | 15 | 80 | 0 | hard | 18930.7 |
| lcbv6-115 | 17 | 80 | 0 | hard | 17363.1 |
| lcbv6-130 | 17 | 80 | 0 | hard | 18075.8 |
| lcbv6-103 | 19 | 80 | 0 | easy | 16126.6 |
| lcbv6-040 | 21 | 80 | 0 | hard | 19987.0 |
| lcbv6-084 | 24 | 80 | 0 | hard | 12978.6 |
| lcbv6-003 | 26 | 80 | 0 | hard | 19897.5 |
| lcbv6-037 | 26 | 80 | 0 | hard | 20278.6 |
| lcbv6-101 | 29 | 80 | 0 | medium | 15523.3 |
| lcbv6-098 | 32 | 80 | 1 | medium | 20384.6 |
| lcbv6-125 | 32 | 80 | 0 | hard | 21932.9 |
| lcbv6-104 | 34 | 80 | 0 | medium | 13167.9 |
| lcbv6-042 | 35 | 80 | 0 | medium | 12065.0 |
| lcbv6-108 | 37 | 80 | 0 | medium | 5234.5 |
| lcbv6-117 | 39 | 80 | 0 | medium | 17558.1 |
| lcbv6-083 | 41 | 80 | 0 | medium | 19935.2 |
| lcbv6-021 | 42 | 80 | 0 | hard | 22934.2 |
| lcbv6-126 | 42 | 80 | 0 | easy | 6010.1 |
| lcbv6-093 | 45 | 80 | 0 | easy | 3576.6 |
| lcbv6-089 | 47 | 80 | 0 | easy | 5292.4 |
| lcbv6-110 | 47 | 80 | 0 | hard | 13772.6 |
| lcbv6-121 | 47 | 80 | 0 | hard | 16560.6 |
| lcbv6-100 | 50 | 80 | 0 | medium | 10112.0 |
| lcbv6-112 | 50 | 80 | 0 | medium | 12032.8 |
| lcbv6-116 | 50 | 80 | 0 | easy | 4830.2 |
| lcbv6-128 | 50 | 80 | 0 | easy | 2676.6 |
| lcbv6-114 | 51 | 80 | 0 | easy | 6578.1 |
| lcbv6-047 | 54 | 80 | 0 | medium | 4737.3 |
| lcbv6-094 | 54 | 80 | 0 | medium | 7330.1 |
| lcbv6-097 | 54 | 80 | 0 | medium | 17132.2 |
| lcbv6-043 | 55 | 80 | 0 | hard | 14350.6 |
| lcbv6-096 | 55 | 80 | 0 | easy | 7067.8 |
| lcbv6-006 | 56 | 80 | 0 | easy | 3343.0 |
| lcbv6-022 | 56 | 80 | 0 | medium | 6816.6 |
| lcbv6-029 | 56 | 80 | 0 | hard | 18803.0 |
| lcbv6-082 | 56 | 80 | 0 | easy | 4871.5 |
| lcbv6-122 | 56 | 80 | 0 | easy | 2389.2 |
| lcbv6-123 | 57 | 80 | 0 | medium | 6684.6 |
| lcbv6-034 | 58 | 80 | 0 | medium | 6616.2 |
| lcbv6-111 | 59 | 80 | 0 | easy | 18250.0 |
| lcbv6-027 | 60 | 80 | 0 | easy | 2745.8 |
| lcbv6-051 | 60 | 80 | 0 | easy | 3440.7 |
| lcbv6-035 | 61 | 80 | 0 | easy | 2641.8 |
| lcbv6-086 | 61 | 80 | 0 | medium | 8669.6 |
| lcbv6-011 | 62 | 80 | 0 | medium | 6358.6 |
| lcbv6-052 | 62 | 80 | 0 | medium | 5212.9 |
| lcbv6-008 | 63 | 80 | 0 | easy | 4583.9 |
| lcbv6-013 | 63 | 80 | 0 | hard | 14387.5 |
| lcbv6-044 | 63 | 80 | 0 | medium | 6730.6 |
| lcbv6-005 | 65 | 80 | 0 | easy | 5751.8 |
| lcbv6-119 | 65 | 80 | 0 | easy | 6093.8 |
| lcbv6-018 | 66 | 80 | 0 | easy | 2091.0 |
| lcbv6-014 | 67 | 80 | 0 | hard | 11139.8 |
| lcbv6-024 | 68 | 80 | 0 | medium | 6099.1 |
| lcbv6-030 | 69 | 80 | 0 | medium | 10302.5 |
| lcbv6-038 | 69 | 80 | 0 | medium | 7435.2 |
| lcbv6-058 | 69 | 80 | 0 | easy | 7204.6 |
| lcbv6-032 | 70 | 80 | 0 | easy | 3915.4 |
| lcbv6-053 | 70 | 80 | 0 | hard | 14453.7 |
| lcbv6-025 | 71 | 80 | 0 | hard | 14548.8 |
| lcbv6-085 | 71 | 80 | 0 | medium | 9402.4 |
| lcbv6-107 | 71 | 80 | 0 | easy | 2555.9 |
| lcbv6-028 | 72 | 80 | 0 | hard | 10497.0 |
| lcbv6-077 | 72 | 80 | 0 | medium | 15100.5 |
| lcbv6-016 | 73 | 80 | 0 | easy | 5112.4 |
| lcbv6-002 | 74 | 80 | 0 | easy | 1487.2 |
| lcbv6-015 | 74 | 80 | 0 | hard | 7015.4 |
| lcbv6-059 | 74 | 80 | 0 | hard | 9861.8 |
| lcbv6-055 | 75 | 80 | 0 | medium | 12496.5 |
| lcbv6-057 | 75 | 80 | 0 | easy | 1789.9 |
| lcbv6-020 | 78 | 80 | 0 | easy | 1870.8 |
| lcbv6-012 | 79 | 80 | 0 | easy | 3086.1 |
| lcbv6-041 | 79 | 80 | 0 | easy | 2227.7 |

## TODO (next stages)
- **Sequential-B (N=16@163840)** columns — staged in `scripts/run_bonB_nonsat.sh`, needs max_model_len=196608 fleet + smoke test.
- **SE loop5@32k (N_i=80)** comparison columns — pending Node 1 SE outputs.
- Combined comparison table (SE vs parallel-BoN vs sequential-BoN) once B + SE available.


---

## Sequential-B (N=16 @ 163840) + combined comparison  — 2026-06-09

Sequential-B run: 2,640 gens, 0 retries / 0 failures / 0 OOM / 0 preemption. Fleet @ max_model_len=196608, concurrency 16. Grading identical to Parallel-A.

### Combined: Parallel-BoN (N=80@32k) vs Sequential-BoN (N=16@163840)

| dataset | A solved | B solved | A cap-hit | B cap-hit | A correct_traces | B correct_traces | A co-solved μ | B co-solved μ |
|---|---|---|---|---|---|---|---|---|
| AIME | 15/18 | 15/18 | 516/1440 (35.8%) | 1/288 (0.3%) | 801/1440 | 188/288 | 53.4/80 | 12.5/16 |
| HMMT | 15/21 | 14/21 | 658/1680 (39.2%) | 0/336 (0.0%) | 493/1680 | 133/336 | 32.9/80 | 9.5/16 |
| LCBV6 | 90/126 | 85/126 | 39/10080 (0.4%) | 0/2016 (0.0%) | 4079/10080 | 833/2016 | 45.3/80 | 9.8/16 |

### KEY: problems UNSOLVED by Parallel-A (N=80@32k) — did Sequential-B (160k) crack them?

| problem | A correct/80 | A cap/80 | B correct/16 | B cap/16 | verdict |
|---|---|---|---|---|---|
| aime25-000012 | 0 | 57 | 0 | 0 | STILL 0 (capability-limited) |
| aime25-000013 | 0 | 63 | 0 | 0 | STILL 0 (capability-limited) |
| aime25-000014 | 0 | 42 | 0 | 0 | STILL 0 (capability-limited) |
| hmmt25-000013 | 0 | 52 | 0 | 0 | STILL 0 (capability-limited) |
| hmmt25-000016 | 0 | 60 | 0 | 0 | STILL 0 (capability-limited) |
| hmmt25-000017 | 0 | 32 | 0 | 0 | STILL 0 (capability-limited) |
| hmmt25-000018 | 0 | 29 | 0 | 0 | STILL 0 (capability-limited) |
| hmmt25-000019 | 0 | 12 | 0 | 0 | STILL 0 (capability-limited) |
| hmmt25-000029 | 0 | 22 | 0 | 0 | STILL 0 (capability-limited) |

### Interpretation (length effect, explicit)
- **Sequential-B removed truncation** on math (cap-hit AIME 35.8%→0.3%, HMMT 39.2%→0%) and on code it was already ~0 both ways.
- **Yet it solved no new problems.** Every problem unsolved at 32k-parallel stays 0 at 160k **with zero cap-hit** → those failures are **capability-limited, not length-limited**; the 32k cap was masking a capability ceiling, not causing the misses.
- **Sequential-B never beats Parallel-A on solved-set** (AIME 15=15, HMMT 14<15, LCBV6 85<90). The losses are the N=16 vs N=80 sample-count effect, not length. So **more independent samples (width) > longer single chains (depth)** under matched-ish budget here.
- **Math vs code reported separately:** code (LCBV6) is not truncation-limited at 32k, so Sequential-B is pure sample-count downgrade there (90→85). For math, the length lever is exhausted — the remaining frontier (AIME 000012/13/14; HMMT 13/16/17/18/19/29) is capability-bound.
- **Implication for the SE comparison:** neither width (N=80) nor depth (160k) reaches these problems → the only untested lever is **recombination/evolution (SE)**. Node 1 SE loop5@32k outputs are present (`outputs/node1_se_loop5_*`) — grading them into this table is the next step.

---

## 3-WAY COMPARISON — SE vs Parallel-BoN vs Sequential-BoN (matched ~N=80 budget @32k; B trades width for 160k length)

| dataset | SE loop5@32k (any-loop, N_i≈80) | Parallel-BoN N=80@32k | Sequential-BoN N=16@160k |
|---|---|---|---|
| AIME (18)  | **15/18** | **15/18** | **15/18** |
| HMMT (21)  | **14/21** | **15/21** | **14/21** |
| LCBV6 (126)| **90/126** | **90/126** | **85/126** |

SE detail (solved problems by loop, cumulative any-loop = first column above):
- AIME: loop0=15 →…→ loop4=14 (final<any; evolution *lost* one). HMMT: loop0=12, loop1=**14**(peak), →loop4=12. LCBV6: loop0=90 → loop4=80.
- **SE's final-loop solved is BELOW its any-loop best on all three** (AIME 14<15, HMMT 12<14, LCBV6 80<90): later evolution loops drift away from correct solutions the population already had.

### Reachability frontier — the problems no method solves
The problems unsolved by Parallel-A are **unsolved by ALL THREE methods, at every SE loop, with ~0 cap-hit**:
`aime25-000012/13/14`, `hmmt25-000013/16/17/18/19/29` → SE any-loop=0, parallel N=80=0, sequential 160k=0.

### Conclusion (project's core hypothesis)
> *"Evolutionary/population-based TTS may reach solution space that ordinary independent sampling cannot reach under matched compute."*

**NOT SUPPORTED by this data.** SqueezeEvolve does **not** expand the reachable solved set beyond independent BoN at matched compute — SE any-loop (15/14/90) ties or trails Parallel-BoN (15/15/90). Neither **recombination (SE)**, **width (N=80 parallel)**, nor **depth (160k sequential)** reaches the hard frontier; those problems are **capability-limited**. SE does show higher solution *density* on already-co-solved problems (AIME correct_traces 1006 vs 801) — i.e. it deepens reachable problems but does not widen the reachable set. (Caveat: `strip_think` SE variants `outputs/node1_se_loop5_32k_temp1_strip_*` also present; this table uses the non-strip runs.)

---

## Sequential length sweep (N=16, max_tokens budget 32k→160k) — 2026-06-09

Method: re-graded the **existing** Sequential-B (163840) traces truncated at each token budget K (exact `max_tokens=K`
simulation — autoregressive prefixes are identical for a fixed seed; a smaller cap only changes where it stops).
Math = truncate+re-extract; LCBV6 = pass requires the solution to complete within K tokens. **Validation:** truncated-at-32k
cap-hit reproduces Parallel-A's actual 32k cap-hit (AIME 35.8% both) — confirms the simulation is faithful.

| budget | AIME solved | AIME corr | cap-hit | HMMT solved | HMMT corr | cap-hit | LCBV6 solved | LCBV6 corr | cap-hit |
|---|---|---|---|---|---|---|---|---|---|
| 32k  | 13/18 | 159/288 | 35.8% | 13/21 | 109/336 | 36.0% | 85/126 | 833/2016 | 0.4% |
| 64k  | **15/18** | 188/288 | 0.7% | **14/21** | 133/336 | 0.3% | 85/126 | 833/2016 | 0.0% |
| 96k  | 15/18 | 188/288 | 0.3% | 14/21 | 133/336 | 0.0% | 85/126 | 833/2016 | 0.0% |
| 128k | 15/18 | 188/288 | 0.3% | 14/21 | 133/336 | 0.0% | 85/126 | 833/2016 | 0.0% |
| 160k | 15/18 | 188/288 | 0.0% | 14/21 | 133/336 | 0.0% | 85/126 | 833/2016 | 0.0% |

**Findings:**
- **All length value is realized by 64k; it saturates completely thereafter.** 32k→64k recovers the truncation-limited solves (AIME +2, HMMT +1, correct-traces AIME 159→188, HMMT 109→133). **64k = 96k = 128k = 160k** — identical solved/correct everywhere. The extra 96k (64k→160k) buys **zero**.
- **Cap-hit collapses 36% → ~0.5% by 64k** — essentially every trace that *can* finish, finishes under 64k. So `max_tokens=163840` was ~3× overkill; **64k is the practical ceiling** for this model/these problems.
- **LCBV6 is flat at every budget** (85/126) — code is length-insensitive (cap-hit ≤0.4% even at 32k).
- **The capability-limited frontier never solves at any budget** (AIME 000012/13/14; HMMT 13/16/17/18/19/29 = 0 at 32k…160k). Length recovers truncated solves but cannot reach those problems.

Raw: `outputs/node2_seqB_length_sweep.json`.

### 16k point added (2026-06-12)

Same simulation extended down to **16384** (validation re-run: at 32768 it reproduces the recorded
AIME 13/159/103, HMMT 13/109/121, LCBV6 85/833/8 exactly):

| budget | AIME solved | AIME corr | cap-hit | HMMT solved | HMMT corr | cap-hit | LCBV6 solved | LCBV6 corr | cap-hit |
|---|---|---|---|---|---|---|---|---|---|
| 16k | 6/18 | 21/288 | 94.1% | 3/21 | 13/336 | 95.8% | 73/126 | 723/2016 | 43.6% |

So the length curve has **two knees**: 16k→32k is catastrophic-to-fine for math (cap-hit 94–96% at
16k; nearly all reasoning traces overflow) and material for code (73→85; 16k cap-hit 43.6% matches
the SE loop-0 strip=false 16k cap-hit ~43.5% from node3); 32k→64k still adds on math (+2 AIME,
+1 HMMT); ≥64k adds exactly zero everywhere. Raw: `outputs/node2_seqB_length_sweep_16k.json`.
