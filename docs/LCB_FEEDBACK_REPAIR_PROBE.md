# LCB Feedback-Repair Probe (one-step, non-leaky)

**Why we switched here.** The math feedback probe (`docs/FEEDBACK_SE_OFFLINE_PROBE.md`) is diagnostic
only: gold-aware math feedback leaks ~95% (oracle, undeployable) and gold-free math feedback is
neutral. LCB has **grounded, non-leaky public/sample execution**, so we test the smaller question
first: *given an incorrect LCB candidate, which non-leaky feedback type best helps a one-step repair?*
**Not** yet in-loop Feedback-SE. Baseline LCB strip=false SE loop/control untouched; new artifacts under
`outputs/node1_lcb_feedback_probe/`.

## Candidate source & counts
- **Source:** `outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/se.jsonl.loop_candidates.jsonl`, **loop-0** (BoN-style), 126 problems × 16 = 2016 candidates; full code in `full_response`.
- **Selection (hidden grader used for selection ONLY):** incorrect = fails hidden tests; among problems with ≥4 incorrect loop-0 candidates, took **24 problems**, up to **5 candidates each**, **stratified by public-exec category**. Final pilot = **118 incorrect candidates**. Excluded: 4 no-code, 2 public-exec-failed.
- **Public-exec category mix of the 118:** all_pass 46 · compile_error 33 · wrong_answer 30 · runtime_error 8 · timeout 1. (`all_pass` = passes the shown public tests but fails hidden → **no visible signal** for feedback; 39% of the pilot.)
- **Tests:** public `data/filtered/lcbv6_public_tests.jsonl` (median 3/problem) for feedback; hidden `tests` (seed) only for selection + final grading.
- **Grading/extraction:** `extract_code` (last ```python block); hidden via `scripts/lcb_exec_harness.py`; public via new `scripts/lcb_public_probe_harness.py`.

## Leakage policy (enforced in code)
Feedback (V2/V3/V4) built **only** from public/sample execution. **Hidden tests never appear** in any
feedback or repair prompt — used solely to select incorrect candidates and grade repaired code.

## Decoding
Repair: temp **0.1**, top_p 0.95, top_k 20, max_tokens 16384, same model/endpoint all arms (Qwen3-4B-Thinking,
local vLLM). V4 critic: temp 0.3, max_tokens 1024. seed 1234.

## Feedback arms (exact)
- **V0_no_feedback:** problem + candidate code only.
- **V1_verification_only:** `Verification: This solution is incorrect.`
- **V2_raw_execution_feedback:** verification + raw public-exec (`Failed public test k. Input/Expected/Actual`, or compile/runtime/TLE text).
- **V3_structured_execution_feedback:** deterministic templated (no LLM): `Feedback type: … / Observed behavior: … / Repair hint: …` (incl. "do not assume the shown test is the only failing case").
- **V4_llm_diagnosis_feedback:** critic LLM on (problem + code + public-exec result) → concise preserve/fix/check bullets; **no replacement code, no from-scratch solve** (constraints in the prompt).
- **Repair prompt:** the provided stay-close prompt ("Correctness is primary; stay as close as possible to the candidate; …Return only one corrected Python code block").

## Results — one-step repair (118 candidates/arm)
| arm | repair success | rate | solved problems | code-valid /118 | tok/success |
|---|---|---|---|---|---|
| V0_no_feedback | 10/118 | **8.5%** | 6 | 39 | 128k |
| V1_verification_only | 8/118 | 6.8% | 5 | 39 | 184k |
| V2_raw_execution_feedback | 8/118 | 6.8% | 4 | 26 | 176k |
| V3_structured_execution_feedback | 5/118 | **4.2%** | 2 | 26 | 286k |
| **V4_llm_diagnosis_feedback** | **12/118** | **10.2%** | 7 | **45** | 120k |

Per original public-exec error type (repaired / n):
| arm | all_pass(46) | compile(33) | wrong_ans(30) | runtime(8) | timeout(1) |
|---|---|---|---|---|---|
| V0 | 1 | **8** | 0 | 1 | 0 |
| V1 | 0 | 5 | 2 | 1 | 0 |
| V2 | 1 | 6 | 1 | 0 | 0 |
| V3 | 1 | 4 | 0 | 0 | 0 |
| V4 | **2** | 7 | **2** | 1 | 0 |

Restricting to **visible-signal** candidates (non-all_pass, 72): V0 9 · V1 8 · V2 7 · V3 4 · **V4 10**.
Head-to-head: **V4 repaired 7 that V0 failed; but feedback arms LOST 15 cases V0 solved** (V2/V3/V4
combined) — feedback hurt more often than it helped. Tokens (prompt/completion) similar across arms;
V4 prompt cost higher (critic) but most token-efficient per success (concise + format-safe).

## Key findings
1. **No feedback type substantially beats no-feedback at one-step repair.** V4 (concise LLM diagnosis)
   is marginally best (10.2% vs 8.5%, +2 candidates — within ±3 noise); V1/V2 ≈ V0; **V3 is the worst (4.2%)**.
2. **Verbose feedback derails the output format.** V2/V3 produced **valid code only 26/118** vs 39 (V0/V1)
   and 45 (V4). Much of V2/V3's lower success is the model responding to long/templated feedback with
   prose / running past the cap instead of emitting one clean code block — a real failure mode of raw/
   structured feedback in one-shot repair.
3. **39% of incorrect candidates are `all_pass`** (pass public, fail hidden) → feedback structurally
   has nothing to point at; ~1–2/46 repaired in every arm. This is exactly where feedback can't help.
4. **Even on the 72 visible-signal candidates, feedback didn't help** (V4 10 vs V0 9; V2/V3 worse).
5. **One-step repair of hard incorrect candidates is low-yield (4–10%)** regardless of feedback — these
   are non_saturated loop-0 failures, hard by construction.

### Examples
- **V4 helped (V0✗→V4✓), 7 cases** e.g. lcbv6-001 cand0 (wrong_answer): V4 correctly localized the bug
  ("uses a max-heap + visited Dijkstra-like approach … fails sample 1, outputs 0 …") → repair passed hidden.
- **No-feedback won (V0✓, feedback arm✗), 15 cases** e.g. lcbv6-003/021/027 — feedback (esp. V2/V3) steered
  the one-shot repair away from a fix V0 found unaided, often by breaking the code-block output.
- **Where feedback hurt:** V3 structured templates on compile_error (8/33 V0 → 4/33 V3) — the template
  added length without improving the fix and reduced clean-code emission.

## Answers
- **Does structured (V3) or LLM (V4) feedback substantially improve repair over V0/V1?** **No.** V3 is
  *worse*; V4 is only marginally better (+1.7pp, within noise) and loses 15 head-to-head cases. The
  pre-registered decision rule ("proceed only if V3 or V4 substantially improves over V0/V1") is **not met**.

## Recommendation
- **Do NOT wire in-loop Feedback-SE yet** — this probe does not show a non-leaky feedback type that
  reliably improves one-step repair. **V3 (raw/structured templated execution feedback) is not worth pursuing**
  (worst, and format-derailing).
- **If pursuing feedback at all, V4 (concise LLM diagnosis) is the only viable type** — it's the only arm
  not worse than no-feedback, it's the most format-safe (highest code-validity) and most token-efficient
  per success. But it must first clear a **real margin** before in-loop integration.
- **Before any in-loop step, re-test V4 on a fairer setup:** (a) a **repairable pool** that excludes
  `all_pass` (where feedback can't help) and over-weights compile/runtime/wrong-answer; (b) fix the
  output-format issue (stricter "return ONLY a code block" + larger cap) so feedback isn't penalized by
  derailment; (c) consider **multi-sample (pass@k) repair**, since one-shot at temp 0.1 is high-variance
  and low-yield. Only if V4 then clears a clear margin (e.g. ≥ +5pp on visible-signal candidates) should
  LCB strip=false Feedback-SE (8→4→2→1 pyramid, best feedback type, vs the untouched control) proceed.

## Artifacts
`scripts/probe_lcb_feedback_repair.py`, `scripts/lcb_public_probe_harness.py`,
`data/filtered/lcbv6_public_tests.jsonl`, `outputs/node1_lcb_feedback_probe/{feedback_records.jsonl,
repair_records.jsonl, summary.json}`. Baseline LCB SE loop, math probe outputs, and orchestrator
untouched. No SFT.
