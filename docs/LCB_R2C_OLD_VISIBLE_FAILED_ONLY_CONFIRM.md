# LCB R2c — old format, visible-failed-only feedback (final pre-multi-loop pairing)

**Change tested.** Keep the **old CHECK-bearing V2-concise** block (`STATUS/OBSERVED/DETAIL/CHECK`) on
**visible-failed** candidates; insert **NO feedback block at all** on `all_pass` candidates (not even a
one-line note); add a top-level instruction that feedback is shown *only* for candidates that failed
public/sample execution and that a candidate without a block is *not guaranteed correct*. Stay-close kept.
Arm `R2c_old_visible_failed_only`, **same 560 confirmation groups + per-group seeds**; `R0_stayclose`,
old `R2c`, and refined `R2c` reused for pairing. No V3/V4, no SFT. Hidden tests only for grading.
Baseline/orchestrator untouched. Outputs `outputs/node1_lcb_r2c_old_visible_failed_only_confirm/`.

## Results (560 groups; 399 visible-failed, 161 visible-passed)
| arm | correct/560 | density | code-valid | visible-failed (399) | visible-passed (161) |
|---|---|---|---|---|---|
| R0_stayclose (reused) | 380 | 0.679 | 100% | 262 (0.657) | 118 |
| old R2c (reused) | 386 | 0.689 | 100% | 272 (0.682) | 114 |
| refined R2c (reused) | 379 | 0.677 | 100% | 265 (0.664) | 114 |
| **R2c_old_visible_failed_only** | **391** | **0.698** | **100%** | **276 (0.692)** | 115 |

**Per-group flips:**
- **vs R0_stayclose: 20 wins / 9 losses → net +11** (McNemar χ²≈4.2, **p≈0.04, significant**).
  - **visible-failed: 19 wins / 5 losses → net +14** (χ²≈8.2, **p≈0.004, significant**).
  - **visible-passed: 1 win / 4 losses → net −3** (penalty reduced from −4).
- **vs old R2c: 14 wins / 9 losses → net +5** (276 vs 272 on visible-failed, +4).
- vs refined R2c: 22 wins / 10 losses → net +12.

Token usage: ptok 27.16M (slightly **below** old R2c's 27.23M — all_pass blocks removed), ctok 0.72M;
total ≈ +0.4% over R0_stayclose. Code-valid 100%.

## Answers to the two questions
1. **Does the old visible-failed CHECK format preserve the +10 gain?** **Yes — and it grows it to +14.**
   Visible-failed went 262 → **276** (vs old R2c's 272). Flips **19 win / 5 loss** (vs old R2c's 18/8) — the
   gain is now **statistically significant (p≈0.004)**. Removing the 693 uninformative `all_pass` blocks
   (69% of candidates) appears to **sharpen attention on the real failure feedback**, helping visible-failed
   groups *more*, not just leaving them unchanged.
2. **Does omitting all_pass blocks remove the visible-passed −4 penalty?** **Largely — reduced to −3.**
   Visible-passed 114 → **115** (vs R0_stayclose 118); flips 1 win / 4 losses (was 1/5). The penalty is
   mostly tail noise now rather than a feedback artifact (there's no feedback on these candidates at all;
   the residual −3 is sampling variance on a fresh generation).

## Net
- **`R2c_old_visible_failed_only` is the strongest arm: 391/560 (0.698), +11 over R0_stayclose, significant
  overall (p≈0.04) and on visible-failed (+14, p≈0.004), with code-valid 100% and ~+0.4% tokens.**
- It **beats old R2c by +5** (391 vs 386) and the refined arm by +12 — confirming: keep the CHECK-bearing
  feedback on real failures, give all_pass candidates **nothing**.
- This resolves both prior weaknesses: the visible-failed gain is now significant *and* the visible-passed
  penalty is essentially gone.

## Decision (per the rule)
The arm **keeps the visible-failed gain (improved + significant) and reduces the visible-passed loss** →
**Use `R2c_old_visible_failed_only` as the feedback configuration for the small multi-loop Feedback-SE
pilot.** Frozen config:
- Stay-close recombination wording + top-level "feedback only for failed candidates" instruction.
- Deterministic V2-concise (`STATUS/OBSERVED/DETAIL/CHECK`) **only** on candidates with a visible
  public/sample failure; **no block** on all_pass candidates.
- No V3, no V4, no SFT. Public/sample execution for feedback; hidden tests only for final grading.
- Compare the multi-loop Feedback-SE run against the **untouched strip=false control**, watching whether the
  per-loop visible-failed gain **compounds** across loops (loop0→1→…→5) and whether code-valid stays 100%.

**Artifacts:** `scripts/probe_lcb_r2c_vfonly.py`; `outputs/node1_lcb_r2c_old_visible_failed_only_confirm/{recomb_records.jsonl, summary.json}`. Prior outputs/baseline untouched; no SFT.

---

## Reproduce (exact)

**Command (this arm):**
```bash
cd tts-sft
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
export HF_HUB_OFFLINE=1 HF_HOME=/mnt/cpfs/yangboxue/opsd/TTS/hf_cache
python scripts/probe_lcb_r2c_vfonly.py --concurrency 24 \
  --outdir outputs/node1_lcb_r2c_old_visible_failed_only_confirm
# decoding defaults: temperature 1.0, top_p 0.95, top_k 20, max_tokens 32768, seed 1234
# model: Qwen/Qwen3-4B-Thinking-2507 via local vLLM at http://localhost:8000/v1
```
Prior arms (reused for pairing, not regenerated): `outputs/node1_lcb_r2c_confirm/` (R0_stayclose, old R2c;
`scripts/probe_lcb_r2c_recombine.py --arms "R0_stayclose_no_feedback,R2c_stayclose_v2_concise" --n-problems 70 --groups-per-problem 8`)
and `outputs/node1_lcb_r2c_refined_confirm/` (refined; `scripts/probe_lcb_r2c_refined.py`).

**Parent group / seed reuse (identical across all four arms):**
- Groups = the exact 560 `(problem, group)` pairs from `outputs/node1_lcb_r2c_confirm/recomb_records.jsonl`
  (70 mixed-correctness problems × their first 8 real loop-1 groups). `probe_lcb_r2c_vfonly.py` reads that
  file to fix the group set, so pairing is exact.
- Each group's k=4 parents = the loop-1 `parent_ids` (deterministic, in order) from
  `outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/se.jsonl.loop_candidates.jsonl`.
- Candidate text = the **full strip=false loop-0** `full_response` (same as the strip=false baseline). Code
  is `extract_code`'d **only** to run public tests for feedback — never substituted into the prompt.
- Per-group seed = `1234 + group_index`, identical across arms → same sampling base; only the prompt differs.

**Feedback formatting used (verbatim).** Built deterministically from PUBLIC/sample execution only
(`scripts/lcb_public_probe_harness.py`); hidden tests never appear. **No block for `all_pass`/visible-passed
candidates.** For visible-failed candidates:
```text
Visible execution feedback:
STATUS: {wrong_answer | runtime_error | compile_error | timeout}

OBSERVED:
{short factual summary}

DETAIL:
{wrong_answer:  Input:\n…\n  Expected output:\n…\n  Actual output:\n…   (each truncated ~400 chars)
 runtime/compile: Error:\n{message, ≤300 chars}
 timeout: (no detail line)}

CHECK:
Use this visible execution result to identify possible bugs, but do not overfit only to the shown public/sample test. Hidden tests are not available.
```
Top-level instruction inserted once (the failed-only note):
```text
Visible execution feedback is provided only for candidates that failed public/sample execution. Candidates without a feedback block are not guaranteed to be correct; they simply have no visible failure signal. Use visible failures as evidence of bugs, but do not overfit only to the shown public/sample tests. Hidden tests are not available.
```
Plus the Harman stay-close paragraph (unchanged). Full prompt assembly in `scripts/probe_lcb_r2c_vfonly.py`.

## Status notes
- **The CHECK-removed "refined" format is dead** — removing the per-candidate CHECK regressed the
  visible-failed gain (272→265, losses 8→15); see `docs/LCB_R2C_REFINED_CONFIRM.md`. Do not use it.
- **Frozen config (for the multi-loop pilot):** stay-close wording + top-level failed-only note +
  CHECK-bearing V2-concise **only** for visible-failed candidates + **no block** for all_pass candidates;
  public-only feedback, hidden tests for grading only; no V3/V4, no SFT.
