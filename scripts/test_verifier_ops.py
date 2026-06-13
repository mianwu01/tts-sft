#!/usr/bin/env python3
"""Unit test (no GPU) for the V-arm verifier operators (_verifier_ops.py).

Builds a tiny real checkpoint (N problems x N_CAND candidates from the pinned loop-0), runs the
verdict engine (real harness, full hidden suites, P5 cache) in a temp dir, then asserts the
selection grouping invariants and the elitist double-call alignment contract.
"""
from __future__ import annotations
import importlib.util, json, os, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC_CKPT = REPO / ("outputs/node1_se_loop5_32k_temp1_lcbv6_non_saturated/se.jsonl.checkpoints/"
                   "tts_sft_se_loop5_32k_temp1_lcbv6_non_saturated_node1_loop0.json")
SEED = REPO / "data/filtered/lcbv6_non_saturated.jsonl"
N_PROBLEMS, N_CAND, K, M = 3, 8, 4, 8

tmp = Path(tempfile.mkdtemp(prefix="vf_ops_test_"))
ck = json.load(open(SRC_CKPT))
sub = {"problems": ck["problems"][:N_PROBLEMS], "metrics": {"loop": 0}}
for p in sub["problems"]:
    p["candidates"] = p["candidates"][:N_CAND]
    if p.get("candidate_groups"):
        p["candidate_groups"] = p["candidate_groups"][:N_CAND]
(tmp / "ckpts").mkdir()
json.dump(sub, open(tmp / "ckpts" / "vf_test_loop0.json", "w"))

os.environ.update({
    "LCB_VF_CKPT_DIR": str(tmp / "ckpts"), "LCB_VF_RUN": "vf_test",
    "LCB_VF_SEED": str(SEED),
    "LCB_VF_HARNESS": str(REPO / "scripts/lcb_exec_harness.py"),
    "LCB_VF_GRADING": str(REPO / "scripts/lcb_grading.py"),
    "LCB_VF_CACHE": str(REPO / "outputs/grading_cache/hidden_inloop.jsonl"),
    "LCB_VF_LOG": str(tmp / "audit.jsonl"), "LCB_VF_CONC": "24", "LCB_VF_ELITES": "2",
})
spec = importlib.util.spec_from_file_location(
    "vf_ops", REPO / "external/squeeze-evolve/benchmarks/livecodebench/_verifier_ops.py")
vf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vf)

import random
random.seed(1234)
n_checked = n_mixed = 0
for p in sub["problems"]:
    cands = p["candidates"]
    groups, indices = vf.verifier_selection(cands, K, M)
    assert len(groups) == len(indices) == M
    vs = [vf._STATE["vh"][vf._h(c)] for c in cands]  # engine's own verdicts; KeyError = engine hole
    C = {i for i, v in enumerate(vs) if v["passed"]}
    pid = vs[0]["pid"]
    for grp_idx, grp_txt in zip(indices, groups):
        assert len(grp_idx) == K and len(set(grp_idx)) == K
        assert [cands[i] for i in grp_idx] == grp_txt, "texts/indices misaligned"
        if 0 < len(C) < len(cands) and len(cands) - len(C) >= K - 1:
            assert sum(1 for i in grp_idx if i in C) == 1, \
                f"{pid}: group lacks exactly-one scaffold (C={sorted(C)}, grp={grp_idx})"
    n_checked += 1
    n_mixed += int(0 < len(C) < len(cands))

    # elitist double-call contract on this problem
    old_txt = list(cands)
    old_grp = [[f"g{i}"] for i in range(len(cands))]
    new_txt = [f"child-{pid}-{j}" for j in range(len(cands))]
    new_grp = [[f"ng{j}"] for j in range(len(cands))]
    out_txt = vf.elitist_replace(old_txt, new_txt)
    out_grp = vf.elitist_replace(old_grp, new_grp)
    assert len(out_txt) == len(new_txt) and len(out_grp) == len(new_grp)
    carried = [j for j, t in enumerate(out_txt) if t in old_txt]
    assert len(carried) == min(len(C), 2), f"{pid}: carried {len(carried)} != min(|C|,2)={min(len(C),2)}"
    for j in carried:
        oi = old_txt.index(out_txt[j])
        assert oi in C, f"{pid}: carried a non-verified-correct elite"
        assert out_grp[j] == old_grp[oi], f"{pid}: groups not aligned with texts at slot {j}"
    assert all(out_grp[j] == new_grp[j] for j in range(len(new_grp)) if j not in carried)

# fallback path: candidates the engine has never seen -> uniform selection, plain replace
g2, i2 = vf.verifier_selection(["unseen-a", "unseen-b", "unseen-c", "unseen-d", "unseen-e"], 2, 3)
assert len(g2) == 3 and all(len(x) == 2 for x in i2)
o2 = vf.elitist_replace(["unseen-a", "unseen-b"], ["n1", "n2"])
assert o2 == ["n1", "n2"]
_ = vf.elitist_replace([["x"], ["y"]], [["n1"], ["n2"]])  # paired groups call drains the stash

audit = [json.loads(l) for l in open(tmp / "audit.jsonl")]
pre = [a for a in audit if a["event"] == "verdict_precompute"]
assert len(pre) == 1 and pre[0]["total_cands"] == N_PROBLEMS * N_CAND
print(f"PASS: {n_checked} problems ({n_mixed} mixed-verdict), precompute "
      f"{pre[0]['graded']} graded / {pre[0]['total_correct']} correct in {pre[0]['wall_s']}s; "
      f"selection invariants + elitist alignment + fallbacks all hold. tmp={tmp}")
