# LCB Feedback Case Study (V2 / V3 / V4) — qualitative

**Purpose.** One-step repair (`docs/LCB_FEEDBACK_REPAIR_PROBE.md`) measured *single-candidate* repair,
not the real goal: helping a **recombination** model combine multiple candidates into a better loop-1
solution. This is a **qualitative** study of *what V2/V3/V4 feedback actually say* and whether each
would help recombination preserve good parts and avoid known bugs. **No new repair/in-loop runs**;
reuses `outputs/node1_lcb_feedback_probe/{feedback_records,repair_records}.jsonl`. Baseline/orchestrator
untouched. Cases: `outputs/node1_lcb_feedback_case_study/cases.jsonl` (26 cases, stratified).

**Leakage policy (held):** V2/V3/V4 use **only public/sample** execution. Hidden results appear here as
**analysis-only labels**, never in feedback. For `all_pass`-but-hidden-fail, feedback says only that no
visible failure was observed.

**Feedback types.** V2 = raw public-exec result. V3 = deterministic template of that result (no LLM).
V4 = concise LLM diagnosis from problem + code + public-exec (no replacement code). Critic was capped at
**1024 tokens** (this matters — see V4 below).

## Stratified selection (26 cases)
compile_error ×4, wrong_answer ×4, all_pass ×4, runtime_error ×3, timeout ×1, + **V4-helped** (V0✗→V4✓,
7: lcbv6-001/0, 001/2, 006/15, 022/0, 027/6, 027/8, 037/5) + **V4-hurt** (V0✓→V4✗, 5: lcbv6-003/1, 021/8,
027/11, 034/1, 034/3).

## Representative cases (feedback verbatim + judgement)

### Case A — wrong_answer, **V4 helped** (lcbv6-001::cand0). Repaired: V2✓ V4✓ (V0/V1/V3 ✗)
- **V2:** `Failed public test 1. Input: 2 5 / 1 2 / 3 4 / 5 6  Expected: 31  Actual: 0` — concrete, faithful.
- **V3:** `wrong answer on public test / outputs 0 instead of 31 / inspect the code path…` — keeps verdict+values but **drops the input** and the hint is boilerplate.
- **V4:** traces the algorithm ("max-heap + visited, Dijkstra-like to get top-K; on N=2,K=5, A=[2,1] B=[4,3] C=[6,5] starts at (0,0,0)=2…") — a **real, localized diagnosis**.
- **Judgement:** V2 informative ✓; V3 generic & lost the input; V4 correct/actionable. Best: **V2 (anchor) or V4 (localization)**. Both repaired; V3 didn't.

### Case B — compile_error, **V4 hurt** (lcbv6-003::cand1). Repaired: **V0✓ V1✓**, V2✗ V3✗ V4✗
- **V2:** `SyntaxError: unterminated string literal (line 13)` — exact, useful.
- **V3:** same error + "fix the syntax error, then re-check logic" — fine.
- **V4:** restates the syntax error, then **meta-talks about format and TRUNCATES** ("They don't want a full…" — cut at the 1024 cap) → never delivers the fix.
- **Judgement:** for a trivial syntax bug the model fixes it **unaided (V0✓)**; **all feedback arms hurt** — verbose/duplicative feedback distracted the one-shot repair and (V4) ran past the cap without producing clean code. Best: **none** (no-feedback wins).

### Case C — wrong_answer, large I/O (lcbv6-000::cand0). Repaired: all ✗
- **V2:** dumps full multi-line input + expected (`Yes/Yes/No/Yes/No/Yes`) + actual (`…/Yes/Yes` — differs at line 5) — faithful but **verbose**.
- **V3:** "outputs Yes\nYes\nNo\nYes\nYes\nYes instead of …" — multi-line dumped inline → **garbled & input dropped**.
- **V4:** localizes precisely ("outputs Yes for the 5th query (3 4) but expected No; groups blocks by column…") — best signal, but verbose.
- **Judgement:** V2 has the signal but is bulky for big I/O; V3 garbles it; V4 pinpoints the failing query. Best: **V4 localization** (but none repaired — genuinely hard).

### Case D — all_pass (hidden-fail), lcbv6-000::cand5. Repaired: all ✗
- **V2:** "passes all shown public tests (no visible failure), but is still incorrect."
- **V3:** "passes public tests but incorrect / the failing case is not among the shown tests / re-examine edge cases."
- **V4:** re-derives the problem and starts **speculating** which unshown edge case fails — i.e. **guessing without evidence** (can't know without hidden tests).
- **Judgement:** the only honest non-leaky signal is "no visible failure" (V2/V3). V4 here is the **wrong tool** — it hallucinates a bug. Best: **V2/V3 honest statement; V4 should be suppressed for all_pass.**

### Case E — runtime_error (lcbv6-001::cand12). Repaired: all ✗
- **V2:** `IndexError: list index out of range` — error type, no location.
- **V3:** same + "handle the failing edge case." 
- **V4:** traces the heap init and localizes where the index goes out of range — most actionable.
- **Judgement:** V2/V3 give the error class; V4 localizes. Best: **V4** when concise; V2 as anchor.

## Cross-case judgement (all 26)
- **V2 (raw):** consistently the most **faithful, concrete** signal — for wrong_answer it carries *input → expected vs actual*, for errors the exact message. **Useful for recombination** (recombination needs "on input X this candidate gives A not B"). Weakness: **verbose for large I/O** (needs truncation).
- **V3 (structured):** preserves verdict + error class but **drops the failing input** and **garbles multi-line outputs**; hints are boilerplate. **Lossier than V2 with no compensating gain.** Least useful.
- **V4 (LLM):** **genuinely diagnoses** on visible-failure cases (traces the algorithm, localizes the failing query/step) — the richest when it lands. But as configured: (a) **verbose and frequently truncated** (1024 cap too small for a thinking model → often cut off before the actionable bullets); (b) **doesn't follow the concise bullet format**; (c) on **all_pass it speculates/hallucinates** a bug. Its verbosity also **hurt one-shot repair** (format derailment, lcbv6-003).

## Answers
1. **Most useful for recombination (not just repair)?** **V2 (raw execution) as the grounded core, optionally + a 1–2 line V4-style localization.** Recombination needs the concrete per-candidate fact "fails on input X: got A, expected B" (V2), which is also what V4 reasons *from*. V3 alone is too generic; raw-V4-dump is too long for k=4.
2. **Does V4 diagnose or give generic advice?** It **genuinely diagnoses** (localizes real bugs) on visible-failure cases — not generic — **but** is verbose, often **truncated** (config: 1024-token cap), off-format, and **speculative on all_pass**. Its value is real but currently unreliable to extract.
3. **Does V2 contain useful raw signal to preserve?** **Yes** — failing input + expected + actual (and exact error text) is the most faithful signal and should be preserved (V4 itself depends on it). Caveat: truncate large I/O.
4. **Does V3 lose too much?** **Yes** — it drops the failing input, garbles multi-line outputs, and adds only boilerplate hints. Not worth using as-is.
5. **all_pass hidden-fail — any useful non-leaky feedback?** **Essentially none.** The only honest statement is "passes shown tests; the failure is on an unshown case." V4 attempting a diagnosis here = hallucination. (39% of incorrect candidates are all_pass → feedback structurally can't help them.)
6. **What should the feedback-aware recombination prompt include?**
   - Per candidate, a **short non-leaky block**: `incorrect` + the **concrete public-exec signal** — for wrong_answer the **failing input + expected vs actual (truncated)**; for compile/runtime the **exact error (+line)**; for TLE "exceeds time limit on a shown test."
   - For **all_pass** candidates: only `passes all shown tests; likely fails an unshown edge case` — **no fabricated bug**.
   - Optionally a **single-line localization** (V4-style) *only if* it can be produced concisely and reliably (bigger critic budget + format enforcement, or a non-thinking critic) — never a multi-paragraph dump.
   - Keep total feedback **short** (k=4 candidates share the prompt); **truncate large I/O**; do **not** paste raw V4 reasoning.

## Net recommendation for in-loop Feedback-SE
Use **V2-concise** (faithful failing-test / error, truncated) as the per-candidate feedback core; **drop V3**;
treat **V4** as an optional concise localizer only after fixing its budget/format (and suppress it on
all_pass). This matches the repair-probe finding (V3 worst, V4 only marginal & format-fragile) and reframes
the deployable signal as "preserve V2's concrete execution facts, kept short," which is what a recombination
model can actually use to keep good candidates and avoid the observed failing case.

**Artifacts:** `outputs/node1_lcb_feedback_case_study/cases.jsonl` (26 cases, full V2/V3/V4 text + code
excerpt + analysis-only hidden/repair labels); this doc. No new generation; baseline/orchestrator/math
outputs untouched.
