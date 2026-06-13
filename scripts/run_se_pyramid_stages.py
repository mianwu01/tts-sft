#!/usr/bin/env python3
"""Staged per-loop `groups` schedule driver for SqueezeEvolve (pyramid / funnel runs).

SqueezeEvolve's RoutingConfig has a SINGLE `groups` int (no per-loop schedule), but the local
resume-continue patch (orchestrator.run: start_loop = latest_checkpoint.loop + 1) lets us run
ONE loop per client invocation. This driver therefore executes a decreasing-width schedule by
invoking scripts/run_squeeze_evolve.py once per stage:

    stage t (t = 1..S):  routing.loops = t + 1     -> resumes at loop t, runs exactly loop t
                         routing.groups = schedule[t-1]
                         routing.seed  = base_seed + t   (per-stage reseed; a single-process run
                                                          seeds once — reusing the SAME seed each
                                                          stage would replay identical selection
                                                          index patterns across loops)

With `update: replace` the population entering loop t+1 equals schedule[t-1], so the schedule IS
the population funnel. Constraint enforced here: every loop must start from a population >= k
(selection.uniform uses random.sample without replacement and raises otherwise).

The feedback operator / prompts / env contract are untouched — this driver only sequences stock
client invocations and verifies checkpoints between stages. A pinned loop-0 checkpoint must already
sit in the config's checkpoint_dir (built by scripts/build_pinned_loop0.py).

Per stage the driver archives the wrapper outputs (se.jsonl + raw.json) under <outdir>/stage_raw/,
records the LCB_FB_LOG audit-line span, and verifies the new checkpoint's loop index + population
sizes. A machine-readable pyramid_run_report.json is written at the end (also on failure).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent


def _audit_lines(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    with path.open("rb") as f:
        return sum(1 for _ in f)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, type=Path, help="Seed JSONL (the pinned subset).")
    ap.add_argument("--output", required=True, type=Path, help="Normalized se.jsonl path (wrapper --output).")
    ap.add_argument("--base-config", required=True, type=Path, help="Base YAML; loops/groups/seed overridden per stage.")
    ap.add_argument("--squeeze-evolve-dir", required=True, type=Path)
    ap.add_argument("--schedule", required=True,
                    help="Comma-separated groups per loop, loop1 first. E.g. '16,8,4,2' or '4,2'.")
    ap.add_argument("--base-routing-seed", type=int, default=1234)
    ap.add_argument("--model", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--audit-log", type=Path, default=None,
                    help="LCB_FB_LOG path (already exported to the env); used only to record line spans.")
    args = ap.parse_args()

    schedule = [int(x) for x in args.schedule.split(",") if x.strip()]
    if not schedule:
        raise SystemExit("Empty --schedule")

    base = yaml.safe_load(args.base_config.read_text())
    k = int(base["routing"]["k"])
    pop0 = int(base["routing"]["population"])
    run_name = base["run_name"]
    ck_dir = Path(base["checkpoint_dir"])
    if not ck_dir.is_absolute():
        ck_dir = args.squeeze_evolve_dir.resolve() / ck_dir  # client runs with cwd=se_dir

    # Enforce: population entering every loop >= k (selection.uniform raises otherwise).
    entering = [pop0] + schedule[:-1]   # pop entering loop t = groups of loop t-1 (replace), loop1 <- pop0
    for t, (pin, g) in enumerate(zip(entering, schedule), start=1):
        if pin < k:
            raise SystemExit(
                f"Schedule invalid: loop {t} would select k={k} parents from a population of {pin} "
                f"(selection.uniform samples WITHOUT replacement). Adjust the schedule.")
        if g < 1:
            raise SystemExit(f"Schedule invalid: loop {t} groups={g} < 1.")
    if len(schedule) > 9 - 0:
        # LocalStorage.list_files sorts lexicographically; '<run>_loop10' < '<run>_loop2'.
        raise SystemExit("Schedules with final loop index > 9 break load_latest_checkpoint's "
                         "lexicographic 'latest' pick. Keep total loops <= 9.")

    pin_ck = ck_dir / f"{run_name}_loop0.json"
    if not pin_ck.exists():
        raise SystemExit(f"Pinned loop-0 checkpoint missing: {pin_ck} — run build_pinned_loop0.py first. "
                         "This driver NEVER generates loop 0.")

    outdir = args.output.parent
    stage_cfg_dir = outdir / "stage_configs"
    stage_raw_dir = outdir / "stage_raw"
    stage_cfg_dir.mkdir(parents=True, exist_ok=True)
    stage_raw_dir.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "run_name": run_name,
        "schedule": schedule,
        "k": k,
        "loop0_population": pop0,
        "population_funnel": [pop0] + schedule,
        "base_routing_seed": args.base_routing_seed,
        "per_stage_routing_seed": "base_seed + loop_index (per-stage reseed; see module docstring)",
        "stages": [],
        "status": "running",
    }
    report_path = outdir / "pyramid_run_report.json"

    def _flush():
        report_path.write_text(json.dumps(report, indent=2))

    _flush()
    for t, groups_t in enumerate(schedule, start=1):
        cfg = yaml.safe_load(args.base_config.read_text())
        cfg["routing"]["loops"] = t + 1
        cfg["routing"]["groups"] = groups_t
        cfg["routing"]["seed"] = args.base_routing_seed + t
        cfg["resume"] = True
        stage_cfg = stage_cfg_dir / f"stage_loop{t}.yaml"
        stage_cfg.write_text(yaml.safe_dump(cfg, sort_keys=False))

        prev_ck = ck_dir / f"{run_name}_loop{t-1}.json"
        if not prev_ck.exists():
            report["status"] = f"failed: missing previous checkpoint {prev_ck} before loop {t}"
            _flush()
            return 5

        audit_start = _audit_lines(args.audit_log)
        cmd = [sys.executable, str(REPO / "scripts" / "run_squeeze_evolve.py"),
               "--input", str(args.input),
               "--output", str(args.output),
               "--config", str(stage_cfg),
               "--squeeze-evolve-dir", str(args.squeeze_evolve_dir)]
        for flag, val in (("--model", args.model), ("--base-url", args.base_url), ("--api-key", args.api_key)):
            if val is not None:
                cmd += [flag, val]
        print(f"[pyramid] stage loop{t}: groups={groups_t} seed={args.base_routing_seed + t} -> {' '.join(cmd)}",
              flush=True)
        t0 = time.time()
        proc = subprocess.run(cmd)
        wall = round(time.time() - t0, 1)

        stage_rec: dict = {"loop": t, "groups": groups_t, "routing_seed": args.base_routing_seed + t,
                           "returncode": proc.returncode, "wall_s": wall,
                           "audit_lines": [audit_start, _audit_lines(args.audit_log)],
                           "stage_config": str(stage_cfg)}
        if proc.returncode != 0:
            stage_rec["error"] = "run_squeeze_evolve.py failed"
            report["stages"].append(stage_rec)
            report["status"] = f"failed at loop {t}"
            _flush()
            return proc.returncode or 6

        # Archive this stage's wrapper outputs (they get overwritten next stage).
        raw_src = args.output.with_suffix(args.output.suffix + ".raw.json")
        for src, dst in ((raw_src, stage_raw_dir / f"loop{t}.raw.json"),
                         (args.output, stage_raw_dir / f"loop{t}.se.jsonl")):
            if src.exists():
                shutil.copy2(src, dst)

        # Verify the new checkpoint: loop index + funnelled population size.
        new_ck = ck_dir / f"{run_name}_loop{t}.json"
        if not new_ck.exists():
            stage_rec["error"] = f"expected checkpoint not written: {new_ck}"
            report["stages"].append(stage_rec)
            report["status"] = f"failed at loop {t} (no checkpoint)"
            _flush()
            return 7
        ck = json.loads(new_ck.read_text())
        pops = [len(p.get("candidates") or []) for p in ck["problems"]]
        ck_loop = ck.get("metrics", {}).get("loop")
        stage_rec.update({"checkpoint": str(new_ck), "checkpoint_loop": ck_loop,
                          "n_problems": len(pops), "population_sizes": sorted(set(pops))})
        ok = (ck_loop == t) and pops and all(p == groups_t for p in pops)
        stage_rec["verified"] = ok
        report["stages"].append(stage_rec)
        if not ok:
            report["status"] = (f"failed verification at loop {t}: checkpoint loop={ck_loop} (want {t}), "
                                f"population sizes={sorted(set(pops))} (want all {groups_t})")
            _flush()
            return 8
        print(f"[pyramid] stage loop{t} OK: {len(pops)} problems, population -> {groups_t}, wall {wall}s",
              flush=True)
        _flush()

    report["status"] = "completed"
    _flush()
    print(f"[pyramid] all {len(schedule)} stages completed; report -> {report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
