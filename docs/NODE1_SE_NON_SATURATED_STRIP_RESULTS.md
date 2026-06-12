# Node 1 — SE non_saturated: strip_think=false vs strip_think=true vs BoN (final)

> ## ⚠️ CORRECTION (run 2026-06-10, doc updated 2026-06-12): LCBV6 strip=true rows/claims below are SUPERSEDED
> The strip=true LCBV6 run in this doc had its **own fresh loop-0 (82 solved vs strip=false's 90)** —
> loop-0 sampling variance, not a strip effect. The **loop-0-MATCHED rerun**
> (`outputs/node1_se_strip_lcbv6_fixedloop0/`, strip=true loops 1–4 resumed from strip=false's exact
> loop-0; `scripts/run_lcbv6_strip_fixedloop0.sh`) gives, on the identical 90-solving loop-0:
>
> | LCBV6 (126), SAME loop-0 | reach (any-of-80) | final-pop | per-loop solved | correct traces (loops 1–4) |
> |---|---|---|---|---|
> | strip=F (formal) | 90 | 80 | 90→84→82→82→80 | 3,657 |
> | **strip=T (pinned rerun)** | **91** | **82** | **90→89→86→84→82** | **3,742** |
>
> **Corrected conclusions:**
> - Conclusion #1's "on LCBV6 strip=true reaches FEWER (85<90)" is **wrong** — fairly compared, strip=T
>   reaches **91 ≥ 90** (+1 is within ±1–2 grading noise → read as parity with strip=F and BoN).
> - Conclusion #3's decay contrast ("strip=T 82→75") was the unmatched run's own trajectory. Pinned,
>   **strip=T decays SLOWER than strip=F** (−8 vs −10 from the same loop-0) and yields **+85 more correct
>   traces** in loops 1–4 — verifier-free recombination on code is mildly *better*, not worse, with
>   stripped parents.
> - Conclusions #2 and #4 (token-matched depth, strip=T total-token efficiency) **stand** (token-based;
>   the pinned rerun's cost profile is unchanged, ~141M total). The #4 caveat "trades reach (85<90) for
>   efficiency" is **withdrawn** — there is no reach trade.
> - **Net: on code, strip=true is parity-or-slightly-better at ~0.2× the recombination input cost** —
>   consistent with math, where strip=T was already the compute-fair winner.
>
> **The AIME/HMMT strip=true rows below carried the SAME confound** (own loop-0s) — now also resolved
> with loop-0-matched runs (node2's `outputs/node2_math_plainstrip_f0_{aime,hmmt}/` + node1's
> independent replications `outputs/node1_se_strip_{aime,hmmt}_fixedloop0/`; pin digests verified
> identical to the strip=F anchors):
>
> | AIME (18), SAME loop-0 | union | final | per-loop solved | traces L1–4 |
> |---|---|---|---|---|
> | strip=F (anchor) | 15 | 14 | 15/15/15/14/14 | 848 |
> | strip=T OLD (own loop-0, started 13) | 15 | 15 | 13/14/14/14/15 | 870 |
> | **strip=T PINNED** (node2 / node1 replication) | **15** | **15** | 15/15/15/15/15 | **887 / 891** |
>
> | HMMT (21), SAME loop-0 | union | final | per-loop solved | traces L1–4 |
> |---|---|---|---|---|
> | strip=F (anchor) | 14 | 12 | 12/14/13/12/12 | 553 |
> | strip=T OLD (own loop-0, started 15) | **16** ← lottery | 13 | 15/15/15/14/13 | 726 |
> | **strip=T PINNED** (node2) | **14** | **13** | 12/13/13/13/13 | **653** |
>
> **HMMT's old "strip=T reaches MORE (16>14)" was ALSO loop-0 lottery — in strip=T's favor** (its own
> loop-0 started at 15 solved vs the anchor's 12). Pinned: reach 14 = 14. Conclusion #1's claim of a
> strip=T reach gain on HMMT is withdrawn alongside the LCBV6 reach loss; **reach is strip-invariant on
> all three datasets.** The depth claims survive at corrected magnitudes: same-anchor traces strip=T vs F
> = AIME +5%, HMMT +18%, LCBV6 +2.3% (the old HMMT trace count, 726, was inflated by the lucky start;
> token-matched depth-vs-BoN ratios should be recomputed from the pinned runs before being quoted).
>
> **The clean, fully fair three-dataset strip story (all same-anchor):**
> 1. **Reach: strip-invariant everywhere** (AIME 15=15, HMMT 14=14, LCBV6 91≈90). All prior ± reach
>    deviations in either direction were loop-0 sampling variance.
> 2. **strip=T consistently erodes the population LESS** (AIME holds 15/15/15/15 vs F dripping to 14;
>    HMMT 13s vs F 12s; LCBV6 −8 vs −10).
> 3. **strip=T yields more correct traces from the same start** (+5% / +18% / +2.3%) at a fraction of
>    the recombination prompt cost → it is the strictly better verifier-free SE setting on every dataset.

Formal verifier-free SqueezeEvolve (single model, `fitness=diversity`, `update=replace`, loops=5,
temp=1.0, top_k=20, max_tokens=32768) on the `non_saturated` subsets, compared to compute-matched
Parallel-BoN (N=80). **Not** full-paper Squeeze-Evolve (no confidence routing / no fork). All grading
offline; math = LaTeX exact-match, code = hidden private tests (same harness as calibration).
strip=true LCBV6 = the post-int()-bug-fix re-run (completed 2026-06-09 03:44, 5 loops, no errors).

## Headline table (N=80 each; reach = any-of-80, traces = total correct generations)

| dataset | arm | reach | correct traces | total tokens | traces / M-total | traces / M-decode |
|---|---|---|---|---|---|---|
| **AIME** (18) | BoN | 15 | 801 | 38.9M | 20.6 | 20.8 |
| | strip=F | 15 | 1,006 | 48.3M | 20.8 | 100.6 |
| | strip=T | 15 | **1,026** | **33.4M** | **30.7** | 67.9 |
| **HMMT** (21) | BoN | 15 | 493 | 47.5M | 10.4 | 10.4 |
| | strip=F | 14 | 657 | 57.7M | 11.4 | 55.2 |
| | strip=T | **16** | **831** | **41.1M** | **20.2** | 45.2 |
| **LCBV6** (126) | BoN | **90** | 4,070 | 147.2M | 27.6 | 28.7 |
| | strip=F | **90** | 4,473 | 227.5M | 19.7 | 87.7 |
| | strip=T | 85 | 4,398 | **140.1M** | **31.4** | 41.5 |

Token-matched depth (BoN sub-sampled to the SE arm's token budget, per problem):
- AIME: SE-T 1,026 vs BoN 549 = **1.87×**. HMMT: SE-T 831 vs BoN 344 = **2.42×**.
- LCBV6: SE-T total tokens (140.1M) < BoN's (147.2M), so a token-matched BoN ≈ its full 80 (4,070) →
  SE-T 4,398 ≈ **1.08×** (no real depth edge; SE-T is just slightly cheaper *and* slightly more).

## Conclusions

**1. No reachability expansion — confirmed on all 3 datasets, both settings.** AIME 15 (all arms);
HMMT 14–16 (±1 tail noise); LCBV6: BoN 90, strip=F 90, strip=T 85. SE never reaches *more* than
matched BoN; on LCBV6 strip=true it reaches **fewer** (85<90; only_SE-T = 1 problem, only_BoN = 6).
The hard frontier is capability-limited and identical across methods.

**2. SE's depth advantage is MATH-specific, and strip=true is the compute-fair winner there.**
- AIME/HMMT: strip=true gives **~1.9× / 2.4× more correct traces token-matched**, at **lower total
  tokens than BoN** and ~0.4–0.7× the decode cost. strip=false's edge was partly compute-bought
  (more total tokens than BoN; HMMT reach 14<15).
- **On code there is no depth advantage:** strip=F 4,473 and strip=T 4,398 are both ~1.08–1.10× BoN
  (co-solved density ratio 1.09×). SE doesn't concentrate correct *programs* the way it does correct
  math answers.

**3. Why code differs (mechanism, evidence-backed).** `update=replace` + verifier-free recombination
**net-destroys** correct programs on code: LCBV6 per-loop solved decays (strip=F 90→80, strip=T
82→75; "lost-after-solved" = 10 vs 1–2 on math). Without running tests the model can't tell which
candidate is correct or merge programs without breaking them — so recombination loses ~as much as it
makes. On math the model self-verifies/votes, so replace is near-lossless and recombination amplifies.

**4. The one thing strip=true fixes on code: total-token efficiency.** strip=false's k=4 full-trace
code recombination costs 176M input tokens → 19.7 traces/M-total (worse than BoN's 27.6). strip=true
cuts input to 34M → **31.4 traces/M-total, now above BoN** (and total 140M < BoN 147M). So strip=true
makes SE *FLOP-competitive* on code — but with no reach gain and tied depth, it still doesn't *beat*
BoN; it trades reach (85<90) for efficiency.

## Bottom line
For the self-distillation goal (max correct traces per compute, same reachable set): **SE +
strip_think=true is a clear win on math** (~1.4× count-matched / 1.9–2.4× token-matched more correct
traces, cheaper) and **roughly a wash on code** (efficiency-competitive but no depth/reach edge,
and `replace` erodes the population). The paper's mechanism we *didn't* run (confidence-routed
multi-tier compute) is a separate question.

## Output paths
- `outputs/node1_se_loop5_32k_temp1_{aime,hmmt,lcbv6}_non_saturated/` (strip=false),
  `…_strip_{aime,hmmt,lcbv6}_non_saturated/` (strip=true): se.jsonl, raw.json, checkpoints/ (loops0-4),
  loop_candidates.jsonl, genlog.jsonl, per_problem.jsonl, summary.json.
- BoN: `outputs/node2_bon_parallel_N80_32k_temp1_*_non_saturated.jsonl` (+ graded
  `outputs/node2_bon_lcbv6_graded/`).
- SE per-loop tokens: `external/squeeze-evolve/outputs/node1_*/metrics.json`.
- Scorer: `scripts/score_se_subset.py`. Tests/verifiers were NOT used inside SE (verifier-free).
