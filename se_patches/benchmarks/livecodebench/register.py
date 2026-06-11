"""LiveCodeBench (code generation) operators for Squeeze-Evolve.

Follows the official benchmark-plugin pattern (cf. benchmarks/aime25/register.py):
auto-discovered by squeeze_evolve.api.cli._discover_benchmarks() at startup.

- `livecodebench-aggregate`: code-aware recombination (is_code=True) -> the loop>=1
  prompt asks the model to combine candidate *programs* and "Return your final code
  in a single Python code block enclosed with ```", matching the calibration CODE_PROMPT.
  Full parent solutions are embedded verbatim (strip_think handled by the orchestrator).
- `livecodebench-none`: no-op evaluator (verifier-free SE; tests are applied OFFLINE
  only, never inside SE selection/recombination).
"""

from squeeze_evolve import evaluation, recombination
from squeeze_evolve.common import eval_none, make_aggregate_prompt

_CODE_ANSWER_FORMAT = "a single Python code block enclosed with ```"


@recombination.register("livecodebench-aggregate")
def livecodebench_aggregate(query, candidates, **kwargs):
    return make_aggregate_prompt(
        "competitive programming problem",
        _CODE_ANSWER_FORMAT,
        is_code=True,
    )(query, candidates, **kwargs)


@evaluation.register("livecodebench-none")
def livecodebench_none(candidates, gt, **kwargs):
    return eval_none(candidates, gt, **kwargs)


# Additive vfonly feedback operator (loop>=1 augments the recombination prompt with deterministic
# PUBLIC/sample-test execution feedback on visible-failed candidates only). Original operator above
# is untouched. See _feedback_aggregate.py for the frozen config + leakage policy. Loaded by file path
# because benchmark register modules are exec'd standalone (no parent package -> no relative imports).
import importlib.util as _ilu  # noqa: E402
import os as _os  # noqa: E402

_fa_spec = _ilu.spec_from_file_location(
    "lcb_feedback_aggregate", _os.path.join(_os.path.dirname(__file__), "_feedback_aggregate.py"))
_fa_mod = _ilu.module_from_spec(_fa_spec)
_fa_spec.loader.exec_module(_fa_mod)
_feedback_aggregate = _fa_mod.feedback_aggregate


@recombination.register("livecodebench-feedback-aggregate")
def livecodebench_feedback_aggregate(query, candidates, **kwargs):
    return _feedback_aggregate(query, candidates, **kwargs)
