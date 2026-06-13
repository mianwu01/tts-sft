# LCB V4-Localizer Prompt-Quality Probe

**Goal.** Adopt **V2-concise** as the deterministic grounded feedback core, and decide whether a SHORT,
reliable, non-leaky **V4 localizer** can add usable bug-localization on top of it for feedback-aware
recombination. **No repair, no recombination, no in-loop run.** 26 case-study candidates, 78 V4 calls
(temp 0.1, max_tokens 6144). Public/sample execution only; hidden tests not used here. Prior outputs
untouched. Artifacts: `outputs/node1_lcb_v4_localizer_probe/{localizer_records.jsonl, summary.json}`.

## Step 1 — V2-concise (deterministic, no LLM) — ADOPTED
`scripts/probe_lcb_v4_localizer.py:v2_concise()` maps a public-exec result → a compact block:
- **wrong_answer:** `Wrong answer on a public/sample test.\nInput:\n<…>\nExpected output:\n<…>\nActual output:\n<…>` (each truncated ~400 chars).
- **runtime/compile:** `Runtime error on a public/sample test: <err>` / `Compile/syntax error: <err>` (≤300 chars).
- **timeout:** `Time limit exceeded on public/sample test <k>.`
- **all_pass / visible-pass:** exactly `Visible tests passed; no visible failure observed. Verify edge cases, constraints, and complexity.` — **never implies hidden failure.**
Compact (<~1k tokens), non-leaky, faithful. This is the grounded core.

## Step 2 — V4 localizer variants (exact prompts)
**V4a (execution-grounded, one line):** input problem + code + V2-concise; output exactly
`LOCALIZATION: <one sentence>` or `LOCALIZATION: No visible bug localization available.` (no code, no
multi-line, no hidden-test mention).
**V4b (execution-grounded, short structured):** output exactly `PRESERVE: …` / `FIX: …` / `CHECK: …`
(one sentence each; if no visible failure, `FIX: No visible failure to localize.`).
**V4c (verifier-free, one line):** input problem + code ONLY (no execution); output one `LOCALIZATION:` line.
(Full prompt text in `scripts/probe_lcb_v4_localizer.py`.)

## Step 3 — Results (26 cases: compile 10, wrong_answer 5, all_pass 7, runtime 3, timeout 1)
| variant | parsed | avg completion tok | truncated | all_pass abstained |
|---|---|---|---|---|
| V4a one-line | 20/26 (77%) | ~4,042 | 8 | **6/7** |
| V4b PRESERVE/FIX/CHECK | 20/26 (77%) | ~3,995 | 6 | 6/7 (but 7/26 = template junk) |
| V4c verifier-free | 11/26 (42%) | ~5,257 | 16 | **0/7** |

**Parse/truncate by category (the key finding):**
| category | V4a parsed | V4a truncated | V4c parsed |
|---|---|---|---|
| compile_error (10) | 10/10 | 1 | 10/10 |
| runtime_error (3) | 3/3 | 1 | 0/3 |
| **wrong_answer (5)** | **0/5** | **5/5** | 0/5 |
| all_pass (7) | 6/7 (abstain) | 1 | 1/7 |
| timeout (1) | 1/1 | 0 | 0/1 |

## Step 4 — Qualitative judgement
- **Grounded?** V4a/V4b: yes on the cases they parse, but those are dominated by **compile/runtime** where the localizer just **restates the V2-concise error** — **7/10 compile localizations are "unterminated string literal at line N"** = zero added signal over V2-concise. On **wrong_answer (the cases that need real analysis), V4a/V4b parse 0/5 — all truncated** (the thinking model reasons past 6144 tokens and never emits the line). So the localizer adds value *only where there's nothing to add*, and fails *exactly where it would help*.
- **Actionable / too generic?** Compile/runtime localizations are actionable but redundant with V2. The valuable logic-bug localizations never materialize (truncated).
- **Hallucinate?** **V4c (verifier-free) hallucinates confidently** — e.g. on a candidate with a line-1 *syntax error* it asserts "does not handle cases where the product might be zero" / "DP transition does not enforce two-child majority" (invented logic bugs, code doesn't even compile). **V4c never abstains on all_pass (0/7)** → always speculates.
- **Short & parseable?** Despite the strict one-line spec, outputs cost **~4–5k completion tokens** (thinking) and truncate **~25% (V4a/b) to ~60% (V4c)**. V4b additionally emits the **instruction placeholders verbatim in 7/26** ("PRESERVE=<which correct part to keep>", "[something]"), so its real usable rate is well below 77%.
- **Useful for recombination?** **No, as configured.** It either echoes V2-concise (compile/runtime) or truncates (wrong_answer), at ~4k tokens/candidate (× k=4 = ~16k/group/loop) — pure cost. V4c is worse (hallucinates).
- **all_pass non-leaky behavior:** V4a abstains correctly (6/7); V2-concise's fixed message is the right signal. Good.

## Answers / recommendation
- **V2-concise is the grounded core** and already carries the actionable signal (exact error, or input/expected/actual). **Adopt it.**
- **V4 localizers do not reliably add usable signal on top of V2-concise** with this (thinking) critic: redundant on easy cases, truncated on the hard wrong_answer cases, ~4k tokens each, and V4b/V4c are unreliable (placeholders / hallucination). **Do not add a V4 localizer to the first recombination probe.**
- **Drop V4c (verifier-free) entirely** — it hallucinates and never abstains.

**Recommended next recombination-probe arms (do NOT run yet):**
- ✅ **R0_no_feedback** (control)
- ✅ **R2c_v2_concise_only** ← primary feedback arm (V2-concise blocks interleaved into the original `livecodebench-aggregate` template, all_pass → the fixed non-leaky message)
- ⚠️ **R2c_plus_V4a_one_line_localizer** — only if V4a is first made reliable on wrong_answer: use a **non-thinking / `/no_think` critic** (or a much larger cap + forced format) AND **drop the localizer whenever it merely restates V2-concise**. Otherwise it adds cost without signal. Recommend **deferring** this arm.
- ❌ **Rvf_verifier_free_V4c_only** — drop (hallucinates).

**Net:** proceed (when ready) with **R0 vs R2c_v2_concise_only** as the core feedback-aware recombination
comparison; revisit V4 localizers only with a cheaper, non-thinking, format-reliable critic that actually
fires on logic-bug (wrong_answer) cases. Exact V2-concise formatter and V4 prompts are in
`scripts/probe_lcb_v4_localizer.py`; per-case outputs in `outputs/node1_lcb_v4_localizer_probe/`.
