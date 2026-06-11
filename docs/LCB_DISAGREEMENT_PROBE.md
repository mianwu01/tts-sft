# P1: Disagreement-Feedback Probe (M4-analog for code) — offline, one-step

**Question.** vfonly's binding limiter is the blind spot: candidates that pass all public tests but fail
hidden tests get **zero** feedback (≈44% of all_pass parents; 667/2016 loop-1 groups have *all four*
parents all_pass). Node2 showed label-free **population-consistency** feedback works on math (M4: +65 net
flips, p≈5e-9). This probe ports the idea to code via **differential testing**: do candidates *disagree
with each other* on extra inputs — and does showing those disagreements (facts only, no labels) help
recombination on exactly the groups vfonly can't touch?

**Leakage policy.** Probe inputs are model-proposed **inputs only** — no expected outputs are ever
generated, stored, or shown. The feedback states observable facts ("Solutions 1 and 3 produce different
outputs on input X; at most one can be correct") and never claims which is right. Hidden tests: post-hoc
grading + analysis-only stratification. Fully deployable signal.

## Pipeline (all new, offline)
1. `scripts/gen_probe_inputs.py` — one cached call/problem proposes ~6 small, constraint-valid extra
   inputs formatted like the public examples (125/126 problems got ≥2; median 6).
2. `scripts/lcb_probe_exec.py` — subprocess harness: run code on inputs **without expected outputs**,
   capture output/error/timeout per input.
3. `scripts/probe_lcb_disagreement.py` — select loop-1 groups (formal strip=false anchor) where ALL 4
   parents are all_pass; differential-exec the parents on the probe inputs; for groups with detected
   disagreement run paired arms (same per-group seed, temp 1.0, 32k):
   - **D0_no_feedback** — the vfonly operator's exact output on such groups (stay-close top, no blocks).
   - **D1_disagreement** — same + one factual `Cross-candidate execution comparison` section (≤2 most
     informative disagreeing inputs, behaviors clustered by who-outputs-what).
   Grading via the P5 hardened wrapper (persistent cache + timeout-only retry).

## Results
**Incidence:** 132/667 blind-spot groups (**19.8%**) show real cross-candidate disagreement on ~6 probe
inputs — the signal exists in 1 of 5 groups vfonly leaves untouched.

**Paired outcome (132 groups × 2 arms):**
| stratum | n | D0 correct | D1 correct | wins (D0✗→D1✓) | losses |
|---|---|---|---|---|---|
| **overall** | 132 | 41 | **46** | **5** | **0** |
| **all 4 parents hidden-WRONG (true blind spot)** | 58 | **0** | **2** | 2 | 0 |
| some parent hidden-correct | 74 | 41 | 44 | 3 | 0 |

- **5 wins / 0 losses** paired on identical seeds → one-sided sign test **p = 1/32 ≈ 0.031** (significant
  despite small n; zero regressions).
- **The blind-spot stratum is the headline: D0 solved 0/58, D1 solved 2/58.** These are groups where *no
  parent is correct* and no visible failure exists — the regime where vfonly is structurally blind and
  no-feedback recombination produced nothing. Disagreement feedback created solutions there.
- **code-valid 132/132 in both arms** — the comparison section does not derail output format.
- **Cost:** +0.1% prompt tokens; differential exec is CPU-cached; probe-input generation is 1 call/problem
  (cached forever).

### Example (blind-spot win, lcbv6-105 g5 — all 4 parents pass public tests yet all hidden-wrong)
```
Probe input:
[0]
[[0, 0, 1]]
Solution 1 output:
0
Solution 2, Solution 3, Solution 4 output:
1
```
D0 (no signal) produced another hidden-wrong child; D1's child passed the hidden tests. Note the model was
*not* told who is right — and the winning behavior here was reasoning it out (the majority isn't blindly
trusted; the prompt forbids assuming majority-correct). lcbv6-105 won in 3 separate groups.

## Decision (pre-registered gate: adopt only if D1 beats D0 on these groups)
**GATE PASSED — 5W/0L, p≈0.031, gains concentrated in the true blind spot, zero format cost.**
Recommended integration for the next in-loop run (C2): extend `livecodebench-feedback-aggregate` —
- visible-failed parents → CHECK-bearing V2-concise block (unchanged frozen vfonly);
- **groups with no visible failure → run differential testing on cached probe inputs; if disagreement
  exists, insert the comparison section; else no feedback** (true silence only when candidates are
  *behaviorally indistinguishable*);
- probe inputs precomputed once per problem (`data/filtered/lcbv6_probe_inputs.jsonl`), exec cached.
Expected effect: feedback coverage rises from ~28% of groups (visible-failed only) to ~28% + 20% of the
remainder, targeted at the blind spot. Run C2 on the same pinned anchor vs the existing C (and B for
attribution), per `FEEDBACK_SE_IMPROVEMENT_PLAN.md` §5. **Not launched — needs the usual sign-off.**

**Artifacts:** `outputs/node1_lcb_disagreement_probe/{group_records.jsonl, summary.json}`,
`data/filtered/lcbv6_probe_inputs.jsonl`, the three scripts above, `scripts/lcb_grading.py` (P5).
Caveats: probe inputs are model-proposed and not validity-checked (mitigated: disagreement is
behavior-relative, crash-vs-output is still factual; leading-whitespace formatting noise possible);
one-step probe — in-loop compounding unknown until C2.
