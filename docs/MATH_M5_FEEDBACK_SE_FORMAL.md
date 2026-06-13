# Formal Math Feedback-SE Experiment (M5 in-loop) — Node 2

**Status: COMPLETE — base experiment + strip=true extension + loop-0-controlled 2×2 factorial,
all generated and graded. Last updated 2026-06-12 ~12:45.
Headline: frozen datagen config = M5 + strip_think=true (super-additive on HMMT, zero erosion,
reach invariant across all 8 cells).**
User-authorized formal experiment (2026-06-11): *"use the same loop setup [as the previous formal
math experiment] … run it through loop 4 with M5 … refer to how we are currently doing this on LCB."*
Launched 17:17 via `scripts/run_m5_feedback_se_math.sh` (nohup, log `/tmp/node2_m5fb_se_run.log`),
datasets chained **aime → hmmt**. No SFT, no RL. All numbers below `RESULT-DEPENDENT` on this run's logs.

## Question

Does putting **M5 answer-hidden feedback** (frozen config from the offline diagnostic,
`docs/MATH_FEEDBACK_ANSWER_HIDDEN_PROBE.md`) inside the real SE evolution loop (a) lift per-loop
density, (b) stop `update=replace` erosion, (c) widen reach — relative to the formal verifier-free
runs, **paired on an identical pinned loop-0**?

## Design (mirrors the LCB vfonly pilot)

- **Loop-0 PINNED** verbatim from the formal verifier-free runs
  (`outputs/node1_se_loop5_32k_temp1_{aime,hmmt}_non_saturated` loop-0 checkpoints) via
  `scripts/build_pinned_loop0.py`; orchestrator resume-continue starts at loop 1 (log:
  *"Resume: loaded checkpoint at loop 0; continuing from loop 1."*). **Paired reference = the formal
  run's own loops 1–4 from the IDENTICAL loop-0** (same caveat as LCB: the arm bundles
  stay-close + suppression + feedback, so it is C-vs-A, not pure-feedback isolation).
- **Configs** `configs/squeeze_evolve_m5fb_{aime,hmmt}_node2.yaml` = 3-line diffs from the formal
  configs (run_name, paths/resume, `recombination: {ds}25-m5-feedback-aggregate`). Everything else
  identical: pop16 / k4 / groups16 / loops5 / update=replace / fitness=diversity / strip_think=false /
  temp 1.0 / top_p 0.95 / top_k 20 / max_tokens 32768 / seed 1234 / `evaluation: {ds}25-none`
  (selection stays verifier-free; the gold-derived bit enters ONLY via recombination feedback).
  vLLM TP8 @ 262144 on :8000 (all 8 GPUs).
- **M5 operator** `external/squeeze-evolve/benchmarks/aime25/_m5_feedback_aggregate.py`, registered
  additively (`aime25-` and `hmmt25-m5-feedback-aggregate`; official benchmark-plugin pattern;
  original operators untouched; module exec is discovery-safe for other nodes — `tts_sft` import is
  lazy). Per loop t recombination it reads the **loop t−1 checkpoint** → current population + `gt`,
  then per candidate builds: answer-hidden **verifier verdict** (accepted/rejected/no-answer; gold
  string never in any prompt) + **population final-answer distribution** (clustered with the grader's
  own `is_exact_match`; *refreshes every loop*) with **margin gate** (top-two clusters within 1 AND
  runner-up ≥ 4/16 → distribution omitted, verdict-only). Critic: temp 0.1, 10240 tok, stripped
  candidate view, post-`</think>` STATUS block only, unparseable → neutral placeholder. Feedback for
  all 16 candidates × all problems is **batch-precomputed once per loop** (ThreadPool 48, cached) so
  SE's sequential prompt building stays fast. Recombination prompt: stay-close + full strip=false
  candidates + interleaved feedback blocks + **mention-suppression tail**. Fully guarded: any error →
  no-feedback stay-close fallback, audited (`feedback_operator_audit.jsonl`).
- **Pre-launch validation (mocked critic, zero GPU):** checkpoint discovery, 288-call precompute,
  4 interleaved blocks + suppression tail in the assembled prompt, pairing asserts, registry intact,
  discovery-safety without env, and the guarded fallback path (exercised for real by a SOCKS-proxy
  failure — launcher unsets proxies).

## Live progress

| stage | state |
|---|---|
| AIME pin + loops 1–4 | **DONE 18:56** (1:39:36 wall; ~25 min/loop incl. ~8–12 min critic precompute) |
| AIME audit | 4×288 = 1,152 recomb calls, **0 fallbacks, 0 cache misses**; gate fired only at loop-2 recomb (2 problems) |
| HMMT pin + loops 1–4 | **DONE 20:52** (~1:56 wall); audit 4×336 = 1,344 recomb calls, **0 fallbacks**; gate fired at source-loops 0/1/2 (32/64/32 calls — the hmmt near-tie populations the offline analysis predicted) |
| Grading | **DONE both** (`score_se_subset.py --task math`; genlog/per_problem/summary in both outdirs) |

## Results — HMMT (paired on identical loop-0)

Loop-0 sanity: identical both arms (12 solved, 104 correct traces).

| arm | solved/loop 0→4 | SE-all | SE-final | correct traces/loop (of 336) | traces loops 1–4 |
|---|---|---|---|---|---|
| Formal (plain aggregate) | 12·**14**·13·**12**·**12** | 14 | 12 | 104·131·133·140·149 | 553 |
| **M5 feedback** | 12·13·13·**13**·**13** | 14 | **13** | 104·**136·143·152·171** | **602 (+49, +8.9%)** |

- **Reach identical in both arms** (SE-all 14; same solved sets): both gained exactly hmmt24+hmmt28
  at loop-1 — the known recombination-reach pair — and neither reached more. Reach is a property of
  recombination itself; feedback neither added nor subtracted it.
- **Erosion reduced, and the margin-gate problem is the proof**: both arms lost hmmt23 (the 1/16
  problem whose single correct lineage died early), but the formal run *additionally* lost
  **hmmt25-000010 — the 8-vs-7 near-tie problem — from loops 3–4, while M5 held it to the end.**
  The gate fired exactly on those near-tie populations (source-loops 0/1/2), switching to
  verdict-only feedback — the designed behavior, validated in the wild.
- **Density ahead every loop with a growing gap** (+5, +10, +12, **+22**) — stronger compounding
  than AIME; at loop-4 M5 yields +14.8% more correct traces than the formal arm.

## Combined verdict (decision rule)

| | SE-all (reach) | SE-final | correct traces loops 1–4 |
|---|---|---|---|
| Formal | 29/39 | 26/39 | 1,401 |
| **M5** | 29/39 | **28/39** | **1,490 (+6.4%)** |

**PASS on the LCB-style rule:** the density gain holds and *grows* across loops on both datasets
(no washout), replace-erosion shrinks (AIME eliminated, HMMT halved — including the targeted
near-tie save), and operational quality is clean (0 fallbacks across 2,496 recombination calls,
suppression holding). Reach is unchanged — fully consistent with every prior finding (reach is
capability-limited; feedback buys density and retention, not reach). M5 Feedback-SE is the best
known data-generation configuration for math on this model: same reach as BoN/plain-SE, highest
correct-trace density per generation, and the only arm whose final population retains (nearly) the
full reachable set.

## First results — AIME (paired on identical loop-0)

Loop-0 sanity: **identical** in both arms (15 solved, 158 correct traces) — pinning verified at the
data level.

| arm | solved/loop 0→4 | SE-all | SE-final | correct traces/loop (of 288) | traces loops 1–4 |
|---|---|---|---|---|---|
| Formal (plain aggregate) | 15·15·15·**14**·**14** | 15 | 14 | 158·205·210·216·217 | 848 |
| **M5 feedback** | 15·15·15·**15**·**15** | 15 | **15** | 158·**214·220·226·228** | **888 (+40, +4.7%)** |

- **Replace-erosion eliminated on AIME:** the formal run lost a solved problem at loops 3–4
  (SE-final 14); M5 holds all 15 through the final population. This is the in-loop analog of the
  offline "preserve the accepted candidate" selection channel.
- **Density ahead every loop, advantage mildly growing** (+9, +10, +10, +11) — no washout across
  loops; consistent with compounding-lite rather than a one-shot effect.
- **Reach unchanged (15/18 both arms; same solved sets).** The 3 unsolved AIME problems are the
  known pure-0 capability-limited tail (aime 000012/13/14) — consistent with the offline reach-floor
  result that no deployable feedback manufactures reach.
- **Mention-suppression holds in-loop:** 12.5% of loops-1–4 visible solutions (post-`</think>`)
  contain meta words (majority/consensus/verifier/feedback) — near the no-feedback base rate
  measured offline (~10%); a post-filter remains advisable for SFT use.

### AIME vs BoN (generation-matched, 80/problem, same model+sampling)

| arm | solved | correct traces /1440 | density | tokens in/out (M) | traces per Mtok total / out |
|---|---|---|---|---|---|
| Parallel BoN N=80 | 15/18 | 801 | 0.556 | 0.4 / 38.6 | 20.6 / 20.8 |
| Formal SE | 15/18 (final 14) | 1006 | 0.699 | 38.3 / 10.0 | 20.8 / ~100 |
| **M5 Feedback-SE** | 15/18 (**final 15**) | **1046** | **0.726** | 38.2 / 9.9 + ~10.9 critic (est.) | 17.7 / ~78 |

Reach ties everywhere (core negative result intact). M5 = **1.31× BoN density per generation** and
the only arm whose final population holds all 15 — but on **total**-token efficiency M5 < BoN
(input-heavy strip=false recombination + critic overhead; the density edge is partly compute-bought),
while on **decode**-token efficiency SE-style wins ~3.7× (recombinations converge short; prefill is
cacheable). Open question for SFT value: M5's extra correct traces are partly repaired variants of
existing solutions — pool *diversity* vs BoN's independent correct traces is unmeasured. (Critic
token estimate = 1,152 calls × offline per-call profile; per-call usage not logged in the audit.)

## Pending / next

1. ~~HMMT completion + grading~~ **DONE — see Results & Combined verdict above.**
2. Exact critic token accounting: the operator now logs `critic_ptok`/`critic_ctok` in every
   `loop_precompute_done` audit event (added post-AIME; this run's audits carry estimates only,
   ~10.9M for AIME / ~12.7M est. for HMMT).
3. **Next decision (Harman):** with the verdict a PASS, the natural continuation is SE→SFT data
   generation with the M5 configuration on a non-leaking training pool (recall
   `docs/SE_SFT_REPO_RECON.md`: AIME/HMMT/LCBV6 seeds ARE the held-out evals — a training pool such
   as NuminaMath/MATH-train must be chosen first). Notify-before-generation gate applies.
4. Optional analyses on existing data: trace-diversity of M5's correct pool vs BoN's (matters for
   SFT value); loop-1-only vs all-loops data ablation.

## Strip=true extension (launched 2026-06-12) + the loop-0 anchor confound

User-directed follow-up: redo SE+M5 under **strip_think=true** (the compute-fair math winner).
In-flight: M5-strip paired on the strip=true formal runs' own pinned loop-0
(`outputs/node2_math_m5fb_se_strip_{aime,hmmt}`; operator cache key strip-normalized first —
under strip=true the orchestrator passes stripped candidates while checkpoints store full texts).

**Anchor confound (user-spotted, quantified):** the strip=true and strip=false formal runs drew
DIFFERENT loop-0 populations — AIME 13 vs 15 solved (strip=true missing aime27/29), HMMT **15 vs
12** (strip=true luckily drew hmmt12/13/24 — two of them reach-floor everywhere else). So all
prior cross-strip math claims (e.g. "strip=true HMMT 16 > strip=false 14") are confounded at the
±2–3-problem level — the LCBV6 82-vs-90 artifact again. Notably, strip=true AIME reached 15 from a
13 anchor (+2 recombination reach — *better* than it looked).

### Strip=true anchor results (DONE 2026-06-12 05:22; paired, loop-0 verified identical; 0 fallbacks)

| ds | arm | solved/loop 0→4 | SE-all | SE-final | traces Σ loops 1–4 |
|---|---|---|---|---|---|
| AIME (anchor 13/18) | plain-strip | 13·14·14·14·15 | 15 | 15 | 870 |
| | **M5-strip** | 13·14·**15·15**·15 | 15 | 15 | **919 (+5.6%)** |
| HMMT (anchor 15/21) | plain-strip | 15·15·15·14·**13** | 16 | 13 | 726 |
| | **M5-strip** | 15·14·14·14·**15** | 16 | **15** | **820 (+12.9%)** |

- **The M5 effect replicates on a second anchor and under strip=true, larger**: density +5.6%/+12.9%
  (vs +4.7%/+8.9% at strip=false), gap growing across loops (HMMT +14/+30/+26/+24).
- **Retention again**: HMMT final population 15 vs 13 (plain-strip eroded −3 from its SE-all 16;
  M5 only −1). AIME final tied at 15 (plain-strip recovered by loop 4; M5 got there 2 loops earlier).
- **Reach tied again** (AIME 15, HMMT 16, identical sets). Note both arms reach HMMT 16 from the
  15-anchor — so the famous "strip=true HMMT 16" is anchor + ordinary recombination, not a strip or
  feedback effect. Likewise AIME: both arms climbed 13→15 on this anchor (+2 recombination reach —
  the anchor's loop-0 missed aime27/29-class problems that recombination recovers).
- First exact critic accounting: ~3.8M prompt + ~1.4M completion tokens per loop-precompute (288
  calls); ~20M critic tokens per dataset run.

### The loop-0-controlled 2×2 — COMPLETE (2026-06-12 12:17)

All four cells `{plain, M5} × {strip false, true}` pinned to the SAME strip=false loop-0
(verified identical: AIME 15/158, HMMT 12/104 in every cell). New cells:
`outputs/node2_math_plainstrip_f0_{ds}` (the math fixedloop0 ablation) and
`outputs/node2_math_m5fb_strip_f0_{ds}`. Launcher `scripts/run_math_strip_2x2_completion.sh`.

**Trace-accounting convention (avoid misreading):** paired/2×2 tables report correct traces over
**loops 1–4 only** — the pinned loop-0 contributes an identical constant to every cell (AIME 158,
HMMT 104; e.g. M5-F = 1,490 over loops 1–4 = **1,752 total** incl. loop-0) and is excluded so the
numbers contrast only where the interventions act. The BoN table instead uses **totals incl.
loop-0** because that comparison is generation-matched against BoN's full 80 samples.

**Correct traces Σ loops 1–4 (effect vs plain-F):**

| | AIME | HMMT |
|---|---|---|
| plain-F | 848 (final 14) | 553 (final 12) |
| M5-F | 888 (+40, final 15) | 602 (+49, final 13) |
| plain-T | 887 (+39, final 15) | 653 (+100, final 13) |
| **M5-T** | **926 (+78, final 15)** | **778 (+225, final 14)** |
| interaction | **−1 (perfectly additive)** | **+76 (super-additive)** |

- **AIME: clean additivity** — M5 (+40) and strip (+39) are independent levers; combined +78 ≈
  predicted +79. Each alone fixes the final-pop erosion.
- **HMMT: synergy** — combined +225 vs +149 predicted (+41% density over the formal baseline).
  Plausible mechanism: feedback *salience* — under strip=false the four ~30k-token parents dwarf
  the ~300-token feedback blocks (~0.3% of the prompt); under strip=true parents are ~2k and the
  feedback is ~10% of what the recombiner reads. Stripping doesn't just shorten prompts; it
  amplifies the feedback channel.
- **M5-T is the only cell with ZERO erosion on both datasets** (HMMT final 14 = SE-all 14 — the
  full reachable set survives to the final population; no other math cell has ever done that).
- **Reach: the solved sets are IDENTICAL across all 8 cells** (AIME 15/18, HMMT 14/21) — the
  cleanest demonstration yet that neither strip, nor M5, nor their combination moves the frontier.
- **Cost (exact critic accounting):** under strip=true the critic pass collapses after loop 1
  (HMMT: 4.6M ptok at loop-1 → ~0.5M/loop after — later-loop candidates are short recombinations,
  not cap-bound 32k views) ≈ **~6M critic tokens/dataset vs ~20M under strip=false**; recombination
  prompts are ~15× smaller.

**Frozen data-generation recommendation: `M5 + strip_think=true`** — stacked density gains
(+9% AIME / +41% HMMT over the formal baseline), zero final-population erosion, identical reach,
and the cheapest token profile of any feedback configuration tested.

### Reach and density vs loop (all 2×2 cells, identical pinned loop-0)

**Density per loop** (correct traces / trials-per-loop; AIME /288, HMMT /336):

| AIME | loop0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| plain-F | .549 | .712 | .729 | .750 | .753 |
| M5-F | .549 | .743 | .764 | .785 | .792 |
| plain-T | .549 | .712 | .774 | .792 | .802 |
| **M5-T** | .549 | .733 | **.819** | **.833** | **.830** |

| HMMT | loop0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| plain-F | .310 | .390 | .396 | .417 | .443 |
| M5-F | .310 | .405 | .426 | .452 | .509 |
| plain-T | .310 | .399 | .473 | .518 | .554 |
| **M5-T** | .310 | **.482** | **.592** | **.616** | **.625** |

- **M5-T doubles HMMT's loop-0 density by loop 4** (.310 → .625) and separates from every other
  cell from loop 1 onward; the synergy is visible immediately, not a late-loop artifact. plain-F's
  curve is the flattest — each added ingredient steepens it (M5 mostly late via retention,
  strip steadily, the combination from the first evolution step).
- AIME saturates: all cells converge toward the low-.8s ceiling; M5-T reaches it ~2 loops earlier.

**Cumulative reach per loop** (problems solved by any candidate up to loop t):

| | loop0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| AIME — all 4 cells | 15 | 15 | 15 | 15 | 15 |
| HMMT — all 4 cells | 12 | **14** | 14 | 14 | 14 |

Identical in every cell at every loop: all reach arrives at **loop 1** (HMMT +2 = hmmt24/28, the
known recombination-reach pair) and nothing afterward, regardless of strip or feedback. Per-loop
**solved** (non-cumulative) is where the cells differ — that is retention, not reach: plain-F decays
(HMMT 14→12, AIME 15→14) while M5-T ends at the full cumulative set on both datasets (15 and 14 —
zero erosion).

## Artifacts

Each run dir contains: se.jsonl, se.jsonl.raw.json, se.jsonl.checkpoints/ (loops 0–4),
se.jsonl.loop_candidates.jsonl, run_manifest.json, pinned_subset.jsonl, loop0_population.jsonl,
loop0_source_manifest.json, feedback_operator_audit.jsonl (M5 arms), genlog.jsonl, per_problem.jsonl,
summary.json — all graded.

- Base experiment (strip=false anchor): `outputs/node2_math_m5fb_se_{aime,hmmt}/`
  (launcher `scripts/run_m5_feedback_se_math.sh`)
- Strip-anchor replication: `outputs/node2_math_m5fb_se_strip_{aime,hmmt}/`
  (launcher `scripts/run_m5_feedback_se_math_strip.sh`)
- 2×2 completion cells (strip=false anchor): `outputs/node2_math_plainstrip_f0_{aime,hmmt}/` (plain-T)
  and `outputs/node2_math_m5fb_strip_f0_{aime,hmmt}/` (M5-T)
  (launcher `scripts/run_math_strip_2x2_completion.sh`)
- Reference cells (Node 1 formal runs): `outputs/node1_se_loop5_32k_temp1_{,strip_}{aime,hmmt}_non_saturated/`
- Operator + registrations: `external/squeeze-evolve/benchmarks/{aime25,hmmt25}/`
  (`_m5_feedback_aggregate.py`; strip-normalized cache key; exact critic-token audit events)
- Configs: `configs/squeeze_evolve_m5fb_{,strip_}{aime,hmmt}_node2.yaml`,
  `configs/squeeze_evolve_{plainstrip,m5fb_strip}_f0_{aime,hmmt}_node2.yaml`
