# se_patches — snapshot of the SqueezeEvolve-side method (Feedback-SE, LCB vfonly)

`external/` is gitignored and `external/squeeze-evolve/` is a nested git clone, so the in-loop method
files cannot be tracked in place. This directory snapshots them so the method survives with the repo.

## Contents
- `benchmarks/livecodebench/register.py` — LCB benchmark plugin: `livecodebench-aggregate` (original,
  untouched semantics), `livecodebench-none` (verifier-free eval), and the **additive**
  `livecodebench-feedback-aggregate` registration (loads `_feedback_aggregate.py` by file path because
  benchmark register modules are exec'd standalone).
- `benchmarks/livecodebench/_feedback_aggregate.py` — the **frozen vfonly feedback operator**:
  stay-close prompt + top-level failed-only note; per-parent PUBLIC/sample-test execution (cached,
  4-way parallel, subprocess-isolated); CHECK-bearing V2-concise block ONLY for visible-failed parents;
  NO block for all_pass; code extraction imported from the offline grader (env `LCB_FB_HARNESS` dir,
  verbatim-regex fallback); per-call audit log (`LCB_FB_LOG`); fully guarded (any error → no-feedback
  stay-close fallback). Env contract: `LCB_FB_SEED`, `LCB_FB_PUBLIC`, `LCB_FB_HARNESS`, `LCB_FB_LOG`.
- `squeeze-evolve-tracked-changes.patch` — `git diff` of the SE clone's tracked files:
  - `src/squeeze_evolve/algorithm/orchestrator.py` — resume-continue patch (resume from a loop-t
    checkpoint continues at loop t+1 instead of regenerating loop 0 → enables PINNED loop-0 runs).
  - `src/squeeze_evolve/common.py` — guard two `int()` calls against >4300-digit strings (code-path
    crash fix; pairs with `PYTHONINTMAXSTRDIGITS=0` in launchers).
  - `benchmarks/aime25/register.py`, `benchmarks/hmmt25/register.py` — math-side operator registrations
    (Node 2's line of work; included because the diff is repo-wide).
  - NOT included: `benchmarks/aime25/_m5_feedback_aggregate.py` (Node 2's in-progress math operator —
    theirs to version).

## Install into a fresh squeeze-evolve clone
```bash
cd external/squeeze-evolve
git apply ../../se_patches/squeeze-evolve-tracked-changes.patch
mkdir -p benchmarks/livecodebench
cp ../../se_patches/benchmarks/livecodebench/*.py benchmarks/livecodebench/
```
Then run via `scripts/run_feedback_vfonly_pilot.sh` (sets the env contract, pins loop-0 via
`scripts/build_pinned_loop0.py`, uses `configs/squeeze_evolve_feedback_vfonly_pilot_node1.yaml`).

Snapshot date: 2026-06-11 (post-pilot, includes the grader-extractor import fix).
