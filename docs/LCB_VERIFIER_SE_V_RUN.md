# LCB Verifier-SE (arm V) — full-verdict machinery on the pinned anchor

**Status: FULL RUN LAUNCHED 2026-06-11 20:29 (node3 box, wrapper PID 194194, log
`/tmp/node3_v_full.log`). User-authorized 2026-06-11 ("use the full test suite upfront and
implement the retention and elitism mechanisms keyed on the full verdict" → "Yes do it").
All 3 validation gates passed (unit 15/15-check smoke, empty-env discovery).**

**Loop-0 verdict sanity check PASSED:** in-loop precompute graded 2,016/2,016 in 288s →
**90/126 problems with ≥1 verified-correct (= the canonical post-hoc loop-0 reach exactly)**,
814 correct candidates total. In-loop verdicts ≡ offline grading at the problem level, as designed.
Smoke preview of the mechanism: lcbv6-001 went 1→6 verified-correct in one loop under
scaffold-mixed grouping; 0/16 problems stay on uniform fallback (the pre-registered reach caveat).

## Question & claim type

How much performance does a **real verifier in the loop** add to the evolutionary machinery
(limiters L2 selection + L3 update), beyond prompt-side feedback (C2)? This **simulates the SFT
data-generation regime** (every training problem ships a full test suite). Because verdicts come
from THESE problems' own hidden suites, results are *verifier-guided search* numbers — an
oracle/regime claim. **They are NOT deployable-TTS claims, NOT held-out eval results, and these
outputs must never become SFT data.** (Math precedent: the M5 formal run, same framing.)

## Design (pre-registered)

Sixth arm on the SAME pinned anchor (strip=false rerun #1 loop-0, sha16 `e41da9146d46c474`,
126 problems × 16): loops 1–4 resume-continue, pop16/k4/groups16, temp 1.0/top_p .95/top_k 20,
32k, seed 1234, fitness=diversity. Paired by construction with A/B/C/C2.

| component | V arm | rationale |
|---|---|---|
| recombination (prompts) | `livecodebench-feedback-disagreement-aggregate` — **C2 verbatim** | V−C2 isolates machinery; hidden-test **content never enters a prompt** (anti reward-hacking: candidates can't special-case tests they never see) |
| selection | `livecodebench-verifier-selection` (new, additive) | mixed groups: each k=4 group gets **exactly 1 verified-correct scaffold** (cycled over shuffled C) + 3 from the failer pool; \|C\|∈{0,pop} → uniform (audited) |
| update | `livecodebench-elitist-replace` (new, additive) | children replace pop EXCEPT ≤2 verified-correct elites carried into random child slots (constant pop 16) — targets L3 erosion |
| verdict source | seed `tests` (FULL suites) via the SAME harness + P5 cached grader as offline grading | in-loop verdicts ≡ post-hoc grades by construction; persistent cache `outputs/grading_cache/hidden_inloop.jsonl` makes elite regrades free |

Operators: `external/squeeze-evolve/benchmarks/livecodebench/_verifier_ops.py` (+ registrations in
`register.py`, additive; discovery-safe with no env — verified by empty-env exec of all 6 benchmark
registers). Orchestrator quirk handled: update is called twice back-to-back (texts, then aligned
candidate_groups) — the elite slot plan is stashed and replayed so the lists stay index-aligned.
Both operators fall back to native behavior (uniform / replace) on any error, audited.

## Pre-registered metrics (oracle-aware)

Elitist retention eliminates final-pop erosion **by construction** → final-pop density/SE-final are
mechanical wins: report, don't headline. The honest questions:
1. **Reach**: does V solve any of the 36 never-solved problems? Prediction logged up front: on 0/16
   problems the verdict gives selection no scaffold and elitism nothing to hold (uniform fallback) —
   V's lever there is weak; reach gains would be surprising and important.
2. **Correct-trace yield** (children loops 1–4, of 8,064): the SFT-relevant number. C beat A +8.9%;
   does verifier-keyed grouping (every group gets a working scaffold where one exists) widen it?
3. Loop-of-first-solve per problem; code-valid rate (does scaffold+failer grouping derail format?).
4. V−C2 (machinery value), V−C (machinery + disagreement), against B−A / C−B from the four-arm set.

## Validation gates before full launch

1. ✅ Unit (no GPU, real grading): 3 pinned problems × 8 candidates — verdict precompute 24/24,
   selection exactly-one-scaffold invariant, elitist double-call alignment, fallback paths.
   (`scripts/test_verifier_ops.py`)
2. ⏳ In-loop smoke (2 problems, loops 1–2, real SE client + local vLLM): verdict_precompute fires
   per loop incl. children grading at loop 2; selection policies audited; elites carried into the
   loop-1/2 checkpoints verbatim; C2 feedback audit unchanged; 0 fallbacks.
3. Empty-env discovery exec of all register.py files (protects node1's B launch tonight). ✅

## Confidence scores: not used, and the verifier supersedes their role

We have never used `fitness: confidence` (all runs `fitness: diversity`): confidence needs
prompt_logprobs / the vLLM fork (`CODE-SUPPORTED`: `validate_scoring_policy` rejects single-model
confidence without them), and fitness only drives model ROUTING — with one model there is nothing
to route. In V, the verdict replaces the *selection* role confidence could have played (a verdict
is strictly stronger than a logprob proxy), so confidence stays out. `fitness: diversity` remains
only as the no-op routing signal that keeps config validation off the scoring-model path.

## Launch / artifacts

`scripts/run_verifier_se_node3.sh {smoke|full}` → `outputs/node3_lcb_verifier_v{_smoke,}/`
(se.jsonl, checkpoints, loop_candidates, run_manifest, `verifier_operator_audit.jsonl`,
`feedback_operator_audit.jsonl`). Config `configs/squeeze_evolve_verifier_v{_smoke,}_node3.yaml`.
Log `/tmp/node3_v_{smoke,full}.log` (node3 box). ETA full: ~5h gen + ~5–10 min/loop verdict
precompute (96-core box; measured 24 gradings/16s in the unit test, cache-warm elites free).

## Live progress (in-loop P5 verdicts; cross-arm density comparisons wait for canonical grading)

**As of 2026-06-12 00:03 — loop 2 of 4 generating (selection done for all 126 at ~22:49). Zero
faults: 0 selection/update fallbacks, 0 misalignments, 0 skipped problems, 0 C2-feedback fallbacks
across 252 selection + 252 update events.**

| loop | pop correct (of 2016) | children correct | problems w/ ≥1 correct | selection policies | elites carried | gen wall |
|---|---|---|---|---|---|---|
| 0 (pinned) | 814 (40.4%) | — | **90 = canonical post-hoc reach exactly** (verdict sanity ✅) | 84 scaffold_mixed / 36 uniform_all_wrong / 6 uniform_all_correct | — | — |
| 1 | **1005 (+191, +23%)** | 831/1842 (45.1%) | 90 (no new solves) | loop-2 policies: scaffold_mixed where C>0 (unchanged stratum sizes) | 174 (cache-confirmed: loop-1 precompute graded exactly 2016−174) | 7264 s |
| 2 | **957 (−48 vs loop 1)** | 778/1837 (42.4%) | 90 (still no new solves; all 36 never-solved still 0/16) | 26 problems ↑ / 40 ↓; 24 problems saturated 16/16 | ~179 (cache-confirmed) | 4854 s (pace improved) |
| 3 | **937 (−20; equilibrating)** | — | 90 (all 36 never-solved still 0/16) | 24 ↑ / 31 ↓; 31 saturated 16/16 | cache-heavy (precompute 48 s) | 3670 s |
| 4 | generating (~01:30) | — | — | — | — | ETA ~02:45 (+ final dump) |

Loop-3 read: population correctness settling at the predicted equilibrium (children density +
elite floor), ~940–960; saturated problems 24→31; the elitist floor holds exactly (90 problems
with ≥1 correct every loop). Generation keeps accelerating (121→81→61 min) — cleaner populations
produce shorter completions; loop-3 verdicts were 97% cache hits (48 s), i.e. recombination on
near-saturated problems increasingly reproduces previously-seen code verbatim.

**Loop-2 dynamics note (pre-registered metrics unaffected):** population correctness receded
1005 → 957 (still ≫ loop-0's 814). Mechanism: update replaces 14 of 16 slots regardless of
verdicts, so a population's correctness equilibrates toward (children density + 2 locked elites) —
saturated/high-density problems from the loop-1 jump can only regress (24 problems sit at 16/16
ceiling; 40 problems down vs 26 up). Elites cap the floor (no problem lost its last correct:
problems_with_correct holds at 90 by construction). Design implication worth an ablation later:
`LCB_VF_ELITES=2` is conservative — carrying ALL verified-correct candidates would ratchet
final-pop density monotonically (the math-M5 analog), at the cost of exploration slots. For the
mission metric (SFT yield = union of correct CHILDREN across loops), what matters is per-loop child
correctness vs C2, which only the canonical grading pass can compare.

**Loop-1 per-stratum movement (population verdicts, before → after):**

| stratum at loop-0 | correct candidates | problems ↑ / ↓ | read |
|---|---|---|---|
| 36 never-solved (0/16) | 0 → 0 | 0 / 0 | no lever (uniform fallback) — matches the pre-registered prediction; reach must come from the C2 prompt channel in loops 2–4 if at all |
| **84 mixed (1–15 correct)** | **718 → 911 (+193, +27%)** | **60 ↑ / 17 ↓** | the verifier's home turf: scaffold-mixed groups + 2 elites convert sparse-correct populations to majority-correct fast |
| 6 all-correct (16/16) | 96 → 94 | 0 / 2 | minor churn; elites cap the downside |

Top gainers in one loop: lcbv6-126 **6→16** (saturated), lcbv6-108 6→15, lcbv6-093 6→14,
lcbv6-023 and lcbv6-010 both 2→10. Densification of solved problems is strong and immediate;
**reach is flat at 90/126 after loop 1** — the honest headline so far.

Notes: (a) loop pace ≈ 2h10m/loop (vs ~80 min in the vfonly pilot) → completion ETA ~05:20–05:40
incl. final candidates dump. (b) In-loop child density (45.1% vs 40.4% loop-0 base) is NOT
comparable to the pilots' canonical densities (different extractor/TLE policy) — only the final
canonical pass compares arms. (c) Verdict precompute cost: 288 s (loop 0, cold) / 547 s (loop 1,
1842 children) on 64 threads — ~5–9 min/loop overhead as estimated.

## Cross-node context (same anchor, converging ~05:30 on 2026-06-12)

- Node1 **C2 COMPLETE 23:57** (`outputs/node1_lcb_feedback_se_c2_disagreement/`, gradeable;
  node1's auto-monitor owns grading); **B auto-started 23:58** (`outputs/node1_lcb_stayclose_b/`),
  ETA ~05:00–05:30 at C2's pace.
- Node2 math M5 formal run **COMPLETE, verdict PASS** (reach tied identical sets, erosion
  eliminated AIME / halved HMMT, density +6.4% growing) — the math analog of V's machinery
  question (`docs/MATH_M5_FEEDBACK_SE_FORMAL.md`).
- Once V + B land: five-arm attribution on one pinned anchor —
  B−A (stay-close wording) · C−B (public-test feedback) · C2−C (disagreement add-on) ·
  **V−C2 (verifier-keyed machinery)** — headline quantities: reach on the 36 never-solved and
  child correct-trace yield (final-pop density is mechanical under elitism; report, don't headline).

## RESULTS (canonical `score_se_subset.py` grading, 2026-06-12 02:41; all `RESULT-DEPENDENT`,
artifacts `outputs/node3_lcb_verifier_v/{genlog,per_problem,summary,analysis_v}.json[l]`)

**Run integrity: 0 operator fallbacks across all 4 loops; in-loop verdicts matched canonical
grading at every loop (e.g. loop-0 814/814, loop-1 1004 vs in-loop 1005 — one TLE-flake).**

### The three pre-registered questions

| question | answer |
|---|---|
| **1. Reach** | **ZERO gain: union = 90 = loop-0; solved-late-only = ∅.** All 36 never-solved problems stayed 0/16 every loop. V did not reproduce C's {lcbv6-004, lcbv6-120} (single-seed caveat; C2's grading pending). Prediction confirmed: verdict machinery has no lever where no correct candidate exists. |
| **2. Child correct-trace yield (SFT metric)** | **NEGATIVE vs both C and A.** Children loops 1–4: V **3,126/7,353 observed (42.5%)** vs C 3,989/8,064 (**49.5%**) vs A 3,661/8,064 (45.4%). 711 children were dropped by elitist-replace before entering populations (generated but unobservable); crediting them at V's average density (~+299) still leaves V ≈ 3,425 < A < C. |
| **3. Final population** | **Erosion eliminated, mechanically: SE-final = 90** vs C 82, A 80; solved problems held at 90 every loop (elite floor). Largest final-pop quality of any arm, exactly as pre-registered ("report, don't headline"). |

Per-loop child density: V 45.1 → 42.3 → 41.4 → 41.3% vs C (pop=children under replace)
49.4 → 46.4 → 50.7 → 51.3%. V loop-1 children (831) < C loop-1 (996) **from the identical pinned
loop-0 and same seed** — the gap opens immediately and persists.

### Diagnosis: the scaffold-mixed policy is anti-yield by construction
C's uniform selection samples parents proportional to population correctness — on a 14/16-correct
problem the average group carries ~3.5 correct parents, and recombination overwhelmingly
reproduces correctness. V forces **exactly one** correct scaffold + 3 failers into every group,
deliberately maximizing failer exposure — that lowers per-group correct-signal share precisely on
the high-density problems where most yield lives, while buying nothing on the 0/16 tail (uniform
fallback there anyway). The verifier verdict was spent on an exploration-shaped policy; yield
follows the exploit-shaped one. (Loop-3 convergence signal supports this: 31 saturated problems,
~97% verdict-cache hits — populations reproduce verbatim code; the failer-heavy groups are where
the wrong children come from.)

### What this means
1. **The user's question "what gain does a verifier provide?" decomposes cleanly:**
   retention/elitism keyed on full verdicts → pure win (erosion gone, frontier preserved in-pop,
   zero cost); verdict-keyed GROUP COMPOSITION as implemented (1-scaffold mixing) → hurts yield;
   reach → verifier-indifferent (capability-limited tail, consistent with all prior arms + math).
2. **For SFT data generation the implied recipe is exploit-shaped:** keep elitist retention,
   but group by correctness-proportional (or all-correct) sampling on solved problems — C's
   uniform already approximates this, which is why C wins yield. A V2 policy (elites +
   uniform/exploit grouping) would likely dominate; cheap config-level follow-up.
3. **V−C2 (same prompts, machinery-only delta) becomes exact when node1's C2 grades.**

### Cross-arm table (graded so far; B/C2 pending on node1)

| arm | union (SE-all) | SE-final | children-correct loops 1–4 | note |
|---|---|---|---|---|
| A (plain) | 90 | 80 | 3,661/8,064 (45.4%) | erosion −10 |
| C (vfonly) | **92** | 82 | **3,989/8,064 (49.5%)** | +2 reach (004,120), best yield |
| **V (verifier machinery)** | 90 | **90** | 3,126/7,353 obs. (42.5%) | erosion 0, worst yield |
| B / C2 | — | — | — | grading pending (node1) |
