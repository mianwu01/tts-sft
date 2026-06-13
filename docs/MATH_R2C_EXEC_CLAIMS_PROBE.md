# R2c-math: Executable-Claim Feedback Probe (M6) — NEGATIVE RESULT

**Date 2026-06-11/12, Node 2. Offline diagnostic; no orchestrator change, no SFT.**
Script `scripts/probe_math_r2c_exec_claims.py`; outputs `outputs/node2_math_r2c_exec_probe/`
(claims.jsonl, feedback_records.jsonl, recomb_records.jsonl, summary.json). All numbers
`RESULT-DEPENDENT` on this run.

## Question

LCB feedback-SE showed (suggestive, ±noise) reach beyond loop-0 — recombination synthesizing a
correct solution from all-wrong parents. Math feedback (M5) never did. Hypothesis: code feedback
works because a failing test is a *counterexample with direction*; the math analog would be
**executable verification of the candidate's intermediate claims** (brute-force a small instance,
verify a recurrence/identity, substitute back into constraints) — localized, directional, gold-free.
Does adding it (M6 = M5 + "EXECUTABLE CHECKS" section) beat M5 where it matters — the reach floor?

## Design

17 problems (5 hard 1–4/16 + 12 reach_floor 0/16), 16 real loop-1 groups, **3 samples/group both
tiers**, paired seeds; M5 feedback text reused verbatim from the M5 run, existing M5 trials reused
(only missing reach-floor samples generated) — the paired M6−M5 delta isolates exactly the
executable-checks ingredient. Pipeline: claim-extractor call per candidate (temp 0.1; up to 3
claims, each a self-contained Python snippet that must *compare computed vs claimed* and print
`VERDICT: SUPPORTED/REFUTED — detail`) → sandbox (subprocess, 10s timeout) → deterministic section
appended to the M5 block. 269 extraction calls (~6.0M/2.1M tok), 355 claims (1.32/candidate;
59 candidates none): **287 supported / 41 refuted / 28 failed**.

## The pipeline itself worked — the refutations were precision strikes

On aime25-000012 (never solved by anything but the oracle), checks SUPPORTED the candidates'
genuinely-correct ingredients (P(chord crosses diameter)=2/3, E[diameter crossings]=4/3, verified
by Monte Carlo) and **REFUTED the exact shared erroneous step with the corrected value attached**
("expected chord-chord intersections = 1/3" → *computed 0.388*; "total = 50" → *computed 53.3*).
This is the manufactured partial-credit decomposition + direction signal the design called for.

## Result: it didn't help

| tier | M5 density | M6 density | paired flips (M6 vs M5) | solved |
|---|---|---|---|---|
| hard (240 trials) | 0.442 | 0.417 | 13w / 19l (**net −6**) | 4/5 both |
| reach_floor (576 trials) | 0.030 | 0.028 | 2w / 3l (net −1) | **2/12 both, same set** (hmmt24/28) |

- **No new reach.** Both arms solve only the borderline pair recombination always cracks.
  aime12: 0/48 both arms.
- **The signal was ignored, not used-and-insufficient.** Zero of 48 M6 aime12 outputs engage the
  refutation or corrected values; the answer distribution is unchanged vs M5 (same wrong attractors:
  79, 487/x, 247/x). Across all 816 M6 trials only 11 even mention a refutation. (Mention-suppression
  depresses *citation*, but identical answer distributions mean the reasoning itself didn't move.)
- **Mild net harm on hard** (−6): the checks section is SUPPORTED-heavy (7:1) — on mostly-wrong
  candidates it mostly certifies their locally-true parts, adding reinforcement/dilution.

## Interpretation (updates the working theory)

The reach bottleneck on math is **not step-level information** — we supplied the refuted step *and*
the corrected value, in-prompt, and nothing moved. Combined with the standing M3 result (given only
the final answer, the model solves 11/12 reach-floor problems), the picture is now sharp:

- **Answer-conditioning works; step-conditioning doesn't.** A failing public test constrains the
  *output* of the (mini-)task — it is answer-level information, which is why code feedback enables
  de novo repair. A corrected intermediate value still requires executing the full corrected forward
  derivation, and the model's prior collapses back to its attractor answers. Wrong conceptual frames
  survive the refutation of one of their steps.
- Therefore deployable in-prompt feedback (any of it: verdict, distribution, executable checks) buys
  **density and retention on reachable problems** — never reach. Reach on this model is bounded by
  forward-derivation capability, unlockable only by answer-level information.

## What this points to (proposals, not run)

1. **Tool-computed answers, not tool-checked steps.** For simulable problems (aime12 included), the
   same sandbox that computed 0.388 could Monte-Carlo the *entire* construction and estimate the
   final answer gold-free — then M3-style answer-conditioned derivation (which we know works) writes
   the trace. That is a different method class (tool-augmented generation, not recombination
   feedback), but it is the logical endpoint of this result and fully deployable for self-distillation.
2. **Iterative repair** (multi-turn: fix the refuted step → re-check → continue) instead of
   single-shot recombination — gives the corrected ingredient a chance to survive more than one
   forward pass. Costlier; untested.
3. Don't pursue: more loops (settled), richer in-prompt step feedback (this probe), bigger feedback
   sections (dilution measured here and in LCB all_pass).

Verdict for the program: **M5 stands as the frozen math feedback config**; executable claim-checking
is shelved as in-prompt feedback but its sandbox machinery is directly reusable for proposal #1.
