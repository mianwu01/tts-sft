# Results by dataset — BoN (parallel / sequential) vs SE (verifier-free / verifier-guided)

**Compiled 2026-06-12 00:15.** All numbers `RESULT-DEPENDENT`, sourced from the graded runs listed
under Provenance. Token columns recomputed 2026-06-12 directly from `metrics.json` (SE arms) and
generation-log usage fields (BoN arms); where a source doc quoted a different estimate, the
recomputed value is used and footnoted.

Model: Qwen/Qwen3-4B-Thinking-2507. Problem sets: `non_saturated` AIME (18), HMMT (21), LCBV6 (126).
Sampling everywhere: temp 1.0 / top_p 0.95 / top_k 20 / max_tokens 32768 / seed 1234 (except
Sequential-BoN: max_tokens 163840). All SE arms: pop 16 / k 4 / groups 16 / loops 5 (= loop 0 + 4
evolution loops) / update=replace / fitness=diversity ⇒ 80 generations per problem, generation-
matched to BoN N=80. Verifier arms resume from the **identical pinned loop-0** of the verifier-free
strip=F run, so they are paired by construction.

**Arms**
- **BoN parallel** — N=80 independent samples @32k (multi-sampling).
- **BoN sequential** — N=16 independent samples @160k (sequential/length scaling; ⚠ N=16, not
  compute-matched to the N=80 arms — it trades width for depth and is far cheaper in tokens).
- **SE vf (strip=F / strip=T)** — verifier-free SqueezeEvolve, full traces vs stripped thinking in
  recombination prompts.
- **SE + verifier (iterations)** — math: **M5** answer-hidden feedback (verdict + population
  consistency, margin-gated) in recombination; LCB: **C** vfonly public-test feedback → **C2**
  +disagreement probes → **V** full-verdict selection+elitism (running) → **B** stay-close control
  (running).

**Verifier framing (important):** LCB C/C2 use **public tests only** (deployable-TTS legitimate).
Math M5's verdict is derived from the gold answer (answer-hidden) and V uses the full hidden
suites — both are **regime simulations of SFT data generation** (every training problem ships a
checker), NOT deployable-TTS or held-out-eval claims; their outputs must never become SFT data
for these benchmarks (the seeds ARE the held-out evals).

Columns: solved = any-of-N reach (union over loops for SE); μ = correct traces ÷ solved problems
(per 80 gens unless noted); density = correct traces ÷ total generations; decode = output tokens;
total = input+output tokens.

## AIME (18)

| arm | solved | correct traces | co-solved μ /80 | density | decode tok | total tok |
|---|---:|---:|---:|---:|---:|---:|
| BoN parallel N=80@32k | 15/18 | 801 | 53.4 | 55.6% | 38.6M | 38.9M |
| BoN sequential N=16@160k | 15/18 | 188 | 12.5 /16 | 65.3% | 8.6M | 8.7M |
| SE vf strip=F | 15/18 (final 14) | 1,006 | 67.1 | 69.9% | 10.0M | 48.3M |
| SE vf strip=T | 15/18 | **1,026** | 68.4 | 71.3% | 15.1M | **33.4M** |
| **SE + M5 feedback** | 15/18 (**final 15**) | **1,046** | **69.7** | **72.6%** | 9.9M | 50.3M (+~10.9M critic est.) |

## HMMT (21)

| arm | solved | correct traces | co-solved μ /80 | density | decode tok | total tok |
|---|---:|---:|---:|---:|---:|---:|
| BoN parallel N=80@32k | 15/21 | 493 | 32.9 | 29.3% | 47.2M | 47.5M |
| BoN sequential N=16@160k | 14/21 | 133 | 9.5 /16 | 39.6% | 10.4M | 10.4M |
| SE vf strip=F | 14/21 (final 12) | 657 | 46.9 | 39.1% | 11.9M | 57.7M |
| SE vf strip=T | **16/21** | **831** | **51.9** | **49.5%** | 18.4M | **41.1M** |
| **SE + M5 feedback** | 14/21 (**final 13**) | 706 | 50.4 | 42.0% | 12.0M | 59.5M (+~12.7M critic est.) |

## Math total (39)

| arm | solved | correct traces | density | decode tok | total tok |
|---|---:|---:|---:|---:|---:|
| BoN parallel | 30/39 | 1,294 | 41.5% | 85.8M | 86.4M |
| BoN sequential | 29/39 | 321 | 51.4% | 19.0M | 19.1M |
| SE vf strip=F | 29/39 (final 26) | 1,663 | 53.3% | 21.9M | 106.0M |
| SE vf strip=T | **31/39** | **1,857** | **59.5%** | 33.5M | **74.5M** |
| **SE + M5 feedback** | 29/39 (**final 28**) | 1,752 | 56.2% | 21.9M | 109.8M (+~23.6M critic est.) |

## LCBV6 (126)

| arm | solved | correct traces | co-solved μ /80 | density | decode tok | total tok |
|---|---:|---:|---:|---:|---:|---:|
| BoN parallel N=80@32k | **90/126** | 4,079¹ | 45.3 | 40.5% | 141.6M | 147.2M |
| BoN sequential N=16@160k | 85/126 | 833 | 9.8 /16 | 41.3% | 28.4M | 29.5M |
| SE vf strip=F (= arm A) | **90/126** (final 80) | 4,473 | 49.7 | 44.4% | 51.0M | 227.5M |
| SE vf strip=T | 85/126 (final 75) | 4,398 | 51.7 | 43.6% | 106.0M | **140.1M** |
| SE + C feedback (vfonly, public tests) | **92/126**² (final ~81) | 4,796 | 52.1 | 47.6% | 47.8M | 228.5M |
| SE + C2 (vfonly + disagreement) | 91/126² (final 80) | **4,805** | 52.8 | **47.7%** | 48.2M | 229.7M |
| SE + V (verifier selection+elitism) | RUNNING³ | — | — | — | — | (145.1M through loop 2) |
| SE + B (stay-close control) | RUNNING³ | — | — | — | — | — |

¹ NODE2 per-problem graded value; the strip-comparison doc's re-grade got 4,070 (±9 = SIGALRM-TLE
grading noise on borderline candidates; same pass everywhere within each row's source).
² Reach has ±1–2 TLE grading noise; one consistent union pass gives A 89 / C 91 / C2 91, the
canonical `score_se_subset`-style pass gives A 90 / C 92 / C2 91. The noise-robust statement is the
**solved-late-only sets**: A = ∅, C = {lcbv6-004 (1 trace, fragile), lcbv6-120 (7 traces, robust)},
C2 = {lcbv6-120}. **lcbv6-120 is 0/80 under parallel BoN and never solved by plain SE** — the first
existence proof of feedback-evolution reaching past the independent-sampling frontier.
³ As of 2026-06-12 00:14: V at loop 2 of 4 (ETA ~05:20) — loop-1 snapshot: population correct
814→1,005 (+23%), reach flat at 90, 0 fallbacks; B launched 23:58 (ETA ~05:00–05:30). Auto-monitors
will grade on completion; this table should then gain their final rows + the five-arm attribution
(B−A wording · C−B feedback · C2−C disagreement · V−C2 machinery).

## Reading

1. **Reach (solved) is capability-limited, not method-limited.** Parallel BoN, sequential BoN
   (length 32k→160k buys zero new solves; saturates at 64k), and verifier-free SE all hit the same
   frontier (AIME 15, HMMT 14–16 ±1 tail noise, LCBV6 85–90). The 9 never-solved math problems and
   36 never-solved LCB problems stay at 0 under every arm. The only reach gain anywhere is the
   feedback existence proof on lcbv6-120/004 (²) — real but small.
2. **SE's win is density, not reach — and verifier/feedback iterations sharpen it.** Math: strip=T
   is the compute-fair verifier-free winner (1.9–2.4× token-matched correct traces vs BoN, at lower
   total tokens); M5 feedback is the best per-generation density (AIME 1.31× BoN) and the only arm
   whose final population retains the full reachable set (erosion eliminated on AIME, halved on
   HMMT). LCB: feedback lifts harvest +9% over plain SE (C/C2 vs A) and holds reach better under
   replace-erosion.
3. **Cost structure differs by axis:** SE strip=F arms are input-heavy (recombination prefill;
   ~4.7× BoN total tokens on LCB) but decode-cheap on math (~4× fewer decode tokens than BoN).
   Sequential BoN is cheapest overall but strictly dominated on solved+traces by width. M5's
   density edge is partly compute-bought (critic overhead, total-token efficiency below BoN;
   decode-token efficiency ~3.7× better).
4. **update=replace erodes every SE arm's final population** (final < any-loop on all datasets);
   elitist retention (V arm) removes this by construction — mechanical, so V is judged on child
   correct-trace yield and reach on the 36 never-solved, not final-pop density.

## Provenance

- BoN parallel + sequential, 3-way + length sweep: `docs/NODE2_BON_NON_SATURATED_RESULTS.md`;
  tokens from `outputs/node2_bon_*.jsonl` usage fields.
- SE verifier-free strip=F/T: `docs/NODE1_SE_NON_SATURATED_STRIP_RESULTS.md`;
  tokens `external/squeeze-evolve/outputs/node1_se_loop5_32k_temp1_*/metrics.json`.
- Math M5: `docs/MATH_M5_FEEDBACK_SE_FORMAL.md`; tokens = pinned loop-0 share (formal run) +
  loops 1–4 from `node2_math_m5fb_se_{aime,hmmt}/metrics.json` (the doc's earlier "38.2M in" for
  AIME was an estimate; metrics.json gives 40.4M in / 9.9M out incl. loop-0). Critic tokens are
  offline-profile estimates (exact logging added post-run).
- LCB C / C2: `docs/LCB_FEEDBACK_SE_VFONLY_PILOT.md`, `docs/LCB_FEEDBACK_SE_C2_B_RUN.md`; traces =
  pinned loop-0 (813) + loops 1–4 harvest (3,983 / 3,992); tokens = loop-0 share + run metrics.json.
- V arm (running): `docs/LCB_VERIFIER_SE_V_RUN.md`.
- Out of scope here (budget ablations, same conclusion direction): 16k/loop10 runs
  (`docs/NODE3_STATUS.md`, `docs/NODE4_STATUS.md`) — halving tokens loses reach that doubling
  loops does not recover; pyramid funnel pilot (`docs/NODE3_PYRAMID_PILOT.md`).
