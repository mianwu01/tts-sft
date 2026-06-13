# Math Feedback — Answer-Hidden Probe (Node 2)

**Date 2026-06-11. Diagnostic probe only** — no SE orchestrator change, no in-loop Feedback-SE, no
SFT, no baseline outputs modified. All numbers `RESULT-DEPENDENT` from this run's logs.
Script `scripts/probe_math_feedback_answer_hidden.py`; analysis `scripts/analyze_math_feedback_probe.py`;
outputs `outputs/node2_math_feedback_answer_hidden_probe/{feedback_records,recomb_records}.jsonl, summary.json`.
Served by vLLM TP8 @ max_model_len 262144 (all 8 GPUs), Qwen3-4B-Thinking-2507.

**Question.** Given that AIME/HMMT have only final-answer gold labels (no golden solutions), what
kind of feedback actually helps recombination — and can it be made **answer-hidden / deployable**?
Prior probe (`FEEDBACK_SE_OFFLINE_PROBE.md`): gold-aware helps but leaks ~95% (oracle-only);
free-text gold-free is ~neutral; stripped views win.

## Design

- **Data:** existing loop-0 strip=false candidates from `outputs/node1_se_loop5_32k_temp1_{aime,hmmt}_non_saturated/`
  (16 candidates/problem) + their real loop-1 `parent_ids` as recombination groups (k=4, 16 groups/problem).
- **Coverage: all 33 usable problems**, tiered by loop-0 correctness:
  **mid** (≥5/16 correct; 16 problems), **hard** (1–4/16; 5), **reach_floor** (0/16; 12 — recombination
  has no correct ingredient; included to measure the feedback-vs-oracle gap on capability-limited problems).
- **Trials:** 16 groups × **3 recomb samples/group** (reach_floor ×1), **paired seeds across arms** →
  1,200 trials/arm. Candidate view stripped everywhere; critic at **temperature 0.1**, recombination at
  1.0/top_p 0.95/top_k 20 (SE-matched). All arms share the same stay-close scaffold + interleaved
  `---- Solution i ---- / ---- Feedback on Solution i ----` blocks; **arms differ ONLY in feedback content**.
- **Arms** (signal spectrum):
  | arm | external signal | deployable? |
  |---|---|---|
  | M0_no_feedback | none (control) | — |
  | M1_gold_free_structured | none; critic re-reads candidate; structured STATUS/PRESERVE/ISSUE/CHECK | ✅ |
  | M2_verifier_aware_answer_hidden | **1 bit**: exact-match verdict text (accepted/rejected/no-answer); gold string hidden | ✅ (needs labels) |
  | M4_consistency_aware | **population final-answer distribution** over the 16 attempts (gold-free; clustered with the grader's own `is_exact_match`, so `\dfrac`≡`\frac`) | ✅ (label-free) |
  | M3_gold_aware_oracle | gold answer shown to critic | ❌ leaky/oracle ceiling |
- Critic output is the post-`</think>` structured block only; unparseable feedback (no STATUS) is replaced
  by a uniform neutral placeholder so raw critic reasoning can never pollute recombination or leak gold.

## Results (1,200 paired trials/arm)

| arm | density | traces | net flips vs M0 (win/loss) | sign-test p |
|---|---|---|---|---|
| M0_no_feedback | 0.609 | 731 | — | — |
| M1_gold_free_structured | 0.629 | 755 | **+24** (67/43) | 0.028 |
| M2_verifier_aware_answer_hidden | 0.660 | 792 | **+61** (84/23) | 2.4e-9 |
| **M4_consistency_aware** | **0.663** | **796** | **+65** (95/30) | 4.7e-9 |
| M3_gold_aware_oracle (ceiling) | 0.833 | 999 | +268 (281/13) | ~0 |

By tier (density; net flips):

| arm | mid (16) | hard (5) | reach_floor (12) |
|---|---|---|---|
| M0 | 0.862 | 0.275 | 0.016 |
| M1 | 0.866 (+3) | 0.358 (+20) | 0.021 (+1) |
| M2 | **0.913 (+39)** | 0.362 (+21) | 0.021 (+1) |
| M4 | 0.900 (+29) | **0.412 (+33**, 40w/7l, p=1.1e-6**)** | 0.031 (+3) |
| M3 | 0.962 (+77) | 0.821 (+131) | 0.328 (+60) |

**M4 vs M2 head-to-head (paired): 48 vs 44 — statistically tied** (p=0.76). M2 is better on mid,
M4 on hard.

### Feedback quality

| arm | verdict-vs-truth | unparsed | leak_any | phrase-leak | note |
|---|---|---|---|---|---|
| M1 | 0.746 | 87/518 | 13% | 11 | leak = incidental (critic sees no gold) |
| M2 | 0.998 | 35/518 | 10% | 34 | verdict given; **0/250 rejected-feedback generic** — all engage the candidate's reasoning |
| M4 | 0.852 | 82/518 | 21% | 57 | leak = quoting the population mode (self-generated, not a label) |
| M3 | 0.967 | 68/518 | **43%** | 63 | real gold leakage — oracle-only, as before |

M4's "matches-mode" bit alone predicts candidate correctness at **0.87 accuracy** (TP157 FP63 FN4
TN294) — recall 0.975: a correct candidate is almost never a minority answer. Mode==gold: **16/16 mid,
1/5 hard, 0/12 reach_floor** — the majority is reliable exactly where problems are mid-difficulty.

## Key findings

1. **Answer-hidden feedback works on math.** Both deployable signal arms beat no-feedback decisively
   (M2 +61, M4 +65; p<5e-9), unlike free-text gold-free critique (M1 +24, marginal — confirming the
   prior probe). The lever is an **external signal bit**, not critique format.
2. **The label-free arm (M4) matches the label-dependent arm (M2).** Population answer-consistency —
   available for free inside SE, no gold needed — delivers the same overall gain as the exact-match
   verifier verdict (48-44 paired tie). **Deployable math Feedback-SE does not require labels.**
3. **M4's gain is NOT majority-copying.** Its largest win is aime25-000027 (loop0 1/16; majority
   WRONG): M4 36/48 vs M0 18/48 (19w/1l) — above even the oracle (28/48). Mechanism: 10/16 attempts
   produced no clean final answer, so the distribution exposes the single decisive value (248) to every
   group — including groups whose 4 parents lack the correct candidate (legitimate population→group
   information flow that plain group recombination structurally lacks) — and the critic *verified* that
   candidate's key recurrence ("s₁=36=3·12¹, s₂=432=3·12², s₃=62208=3·12⁴ — closed form checks").
   Caveat: M4 is not uniformly safe — on aime25-000029 (majority also wrong) M2 (+5) beat M4 (+1).
4. **Half the oracle gap is reachable without the gold answer** on mid problems (M2 +39 vs M3 +77);
   on hard problems the deployable arms capture only ~¼ of the oracle's +131. The rest of the oracle
   gain is answer-knowledge itself (M3 leaks 43%) — answer-conditioned proof-finding is far easier
   (reach_floor: M3 solves 11/12 problems / 63 traces; deployable arms ≤2/12 / ~4–6 traces ≈ M0).
   **Reach on capability-limited problems is NOT obtainable from any deployable feedback we tested.**
5. **Feedback density gains are where SE needs them** — hard problems with mixed populations (M4 +50%
   relative on hard). Per the SE-vs-BoN core result, SE's only edge over BoN is density on reachable
   problems; answer-hidden feedback amplifies exactly that edge.
6. **Pilot replication:** an accidental independent 16-problem/1-sample run at critic-temp 1.0
   (`outputs/node2_math_feedback_answer_hidden_probe_pilot16_fbtemp1/`, see its README) shows the same
   ordering (M2 +27 net, 30w/3l; M1 +7) — the M2 effect is robust to critic temperature and sampling.

## Verdict per the decision rule

**M2 significantly improves over M1 and M0 without leaking gold answers → math feedback is worth
continuing.** Moreover M4 shows the verdict bit isn't even necessary: the population answer
distribution (fully label-free, in-loop-available) achieves the same gain. The combination
(M2+M4 in one prompt) is untested and is the obvious next arm. What remains oracle-only is *reach*
on 0/16 problems — only gold knowledge cracks those (M3), consistent with all prior reach findings.

## Deep-dive analysis (`scripts/analyze_math_feedback_deep.py`, read-only)

**A. Mechanism — the two arms work through different channels.** Splitting flips by whether the
k=4 group contains a correct parent (mixed tiers, paired):

| arm | groups WITH correct parent (n=834) | groups WITHOUT (n=174; M0 solves only 21) |
|---|---|---|
| M1 | +15 (52w/37l) | +8 |
| M2 | **+58 (74w/16l)** | +2 (8w/6l) |
| M4 | +39 (63w/24l) | **+23 (28w/5l)** |
| M3 | +104 | +104 |

- **M2 = within-group selection**: the accept/reject bit lets the recombiner identify and preserve
  the correct parent. Where no parent is accepted it has nothing to point at (+2 ≈ noise).
- **M4 = selection + population value-import**: on groups with NO correct parent it more than
  doubles the win rate (21→44/174) by exposing answers the group's 4 parents never produced.
  This is the only deployable channel that produces **group-level reach beyond the parents** —
  exactly the channel an in-loop Feedback-SE would exploit (k=4 draws often miss the population's
  correct member). M2 structurally lacks it.

**B. Complementarity (M2 vs M4, paired).** Wins vs M0: 60 shared, 24 M2-only, **35 M4-only**;
losses: 10 shared, 13 M2-only, 20 M4-only. A hypothetical OR-arm ceiling is **+109** net vs +61/+65
individually — the combined M2+M4 arm has real headroom (~+44 over best-single) and only 10
irrecoverable shared losses.

**C. Failure forensics.**
- M4's losses concentrate on ONE problem: hmmt25-000010 (10/30 losses; M4 24/48 vs M0 26 vs M2 35).
  Its distribution is a **near-tie: 8× "56"(gold) vs 7× "8"** — consistency signal degrades exactly
  when the population splits ~50/50; the heavy wrong attractor pulls recombinations. M2's clean
  binary verdict wins there. → **Gate the consistency block on mode margin** (math analog of the
  LCB vfonly lesson "omit uninformative blocks"); margin is computable gold-free.
- The hypothesized "minority-correct parent gets discouraged" failure is rare: 2/30 M4 losses.
- M1's collapse on hmmt10 (14/48 vs M0 26): its verdicts were wrong on 8/16 candidates there —
  free-text critique fails precisely where the model's prior is wrong (errors correlated with the
  population's own bias), endorsing the seductive wrong count.
- M1 placebo check: groups containing ≥1 placeholder feedback (n=603 of 1,008!) net **−6** —
  unparseable-feedback dilution wipes out M1's thin signal; its +24 comes from the verdict-bearing
  minority of groups.
- Biggest universal win, hmmt25-000002 (M0 22 → M1 42/M2 39/M4 40): population splits 7×(1/576) vs
  5×(576) — a *local, nameable* slip (forgot the inversion). Any scrutiny trigger repairs it; this
  is the failure class math feedback fixes best.

**D. Trace cleanliness (matters for self-distillation).** Recombination OUTPUTS cite feedback
meta-info: M4 mentions population/majority/attempts words in 385/1200 outputs (255/796 of its
*correct* traces ≈ 32%; M0 base rate 116/1200), M2 mentions the verifier in 272/1200 (~23%).
If these traces feed SFT, add **"do not mention the feedback/verifier/other attempts in your final
solution"** to the recombination prompt (test in the next probe) and/or a post-filter. M4 outputs
are also ~14% shorter than M0 (2904 vs 3380 mean ctok); truncation negligible (4/1200 all arms).

**E. Per-problem table** is in the analyzer output (section G); 6/16 mid problems are 48/48
saturated across all arms and dilute mid-tier averages.

## M5 combined arm (run 2026-06-11, same paired design)

`scripts/probe_math_feedback_m5_combined.py` → `outputs/node2_math_feedback_m5_combined/`;
comparison `scripts/analyze_m5_vs_canonical.py`. M5 = M2 verdict + margin-gated M4 distribution
(gate: top-two clusters within 1 AND runner-up ≥4/16 → omit distribution; fired on hmmt10 8v7 and
hmmt5 6v5) + mention-suppression line in the recombination tail. Same 33 problems / 1,200 trial keys
/ per-trial seeds as the canonical arms (startup asserts verify pairing).

**Headline: M5 +102 net flips (125w/23l, p=3.6e-18), density 0.694** — beats both parents
head-to-head (vs M2 +41, p=2e-5; vs M4 +37, p=3e-4) and **exceeds the naive OR-ceiling win count**
(125 wins vs 119): it captures 54/60 shared wins, 17/24 M2-only, 18/35 M4-only, and finds **36 new
wins neither parent had** — the verdict bit and the distribution interact (e.g. "rejected + minority
answer + here is where attempts diverge" gives richer repair direction than either signal alone).
Losses stay at M2's low level (23).

| tier | M0 | M2 | M4 | **M5** | M3 oracle | M5 closes M0→M3 gap |
|---|---|---|---|---|---|---|
| mid | .862 | .913 | .900 | **.938 (+58)** | .962 | **76%** |
| hard | .275 | .362 | .412 | **.442 (+40)** | .821 | 31% |
| reach_floor | .016 | .021 | .031 | .036 (+4) | .328 | ~0 (as expected) |

**Both channels preserved:** groups WITH a correct parent +76 (better than M2's +58); groups
WITHOUT +22 (≈ M4's +23 value-import). Quality: unparsed 40/518 (no worse than parents),
verdict-agree 1.0, 0/1200 truncations.

**Gate verdict — roughly neutral at this threshold (n=2 gated problems, inconclusive):** hmmt10
recovered from M4's damage (24→26 ≈ M0 26) but not to M2's 35; hmmt5 paid the predicted cost
(M4 43 → 39 ≈ M2 38). The big M5 gain comes from the *combination*, not the gate. A stricter gate
(e.g. runner-up ≥7) or none at all are both defensible for the pilot; per-problem evidence is too
thin to tune further offline.

**Mention-suppression verdict — works, ~50–80% reduction:** population-citation excess over M0 base
fell 269→53 (385→169 raw); "feedback" 289/223→147; "verifier" 213→114. Not zero — keep the
instruction and add a post-filter for SFT data.

**One regression to know:** aime25-000027 (M4's star case) drops 36→26 under M5 (still +8 over M0,
above M2's 16) — on highly fragmented distributions the blanket "rejected" verdicts partially mute
the import channel. hmmt2 reaches 48/48 (perfect, above every single arm).

**Updated verdict:** M5 (verdict + distribution + suppression) is the frozen candidate config for a
math multi-loop Feedback-SE pilot — deployable signals only, closes ¾ of the oracle gap on mid
problems, both mechanism channels intact, traces mostly self-contained.

## Recommended next steps

1. ~~M2+M4 combined arm~~ **DONE — M5 section above** (+102, beats both parents, new frozen config).
2. ~~Multi-loop Feedback-SE on math~~ **LAUNCHED as the formal experiment (user-authorized
   2026-06-11) — see `docs/MATH_M5_FEEDBACK_SE_FORMAL.md`.** First paired AIME result: M5 holds
   SE-final at 15/18 (formal eroded to 14), density ahead every loop (+4.7% correct traces over
   loops 1–4, advantage mildly growing), reach unchanged; HMMT in flight.
3. For self-distillation data: M5 feedback text still phrase-leaks incidentally (~23%, self-generated
   values only); if feedback text feeds training traces, add an answer-redaction pass. Recombination
   outputs keep the suppression instruction + a post-filter on the residual ~5% citation excess.
4. Optional cheap ablation if pilot results are ambiguous: M5 without the gate (it was ~neutral) and
   stronger suppression wording.

## Caveats

- Single recombination step (loop-1 equivalent); compounding over loops unmeasured (→ pilot).
- 5 hard problems only — the M4-vs-M2 hard-tier gap (+33 vs +21) is suggestive, not conclusive.
- Exact-match grading (no math_verify); affects all arms symmetrically but may undercount.
- reach_floor used 1 sample/group (flip noise matters less at ~0 density).
- M3's reach_floor "solves" are answer-leak artifacts by design (ceiling measurement, never deployable).
