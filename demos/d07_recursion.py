"""Demo for Lesson 7 (steps/s07_recursion.py): parallel recursion on the real
task, then the blind selection of H★.

    python -m demos.d07_recursion                # what the selector is told (no API calls)
    python -m demos.d07_recursion --live         # k = 2 (Opus and Haiku: $4 to $8, 15 to 60 minutes)
    python -m demos.d07_recursion --live --k 3   # wider, and dearer

A live run is kept under runs/demo_l7_<time>/:
  base/<label>/               the k runs of H0
  step/                       editors/, probes/, composers/, successors/ (as in Lesson 6, k wide)
  selector/context/           exactly what the selector saw: the request, the files, the outputs by id
  selection.md                its reasoning, and which run each id stood for
  adopted.diff                H★ against H0
  grade.md                    every run's failed checks: for you only
  usage.jsonl                 every model call's tokens and cost, by session
"""

import random
import sys
import time

import config
from benchmarks import workbuddy
from steps.s00_llm import LLM
from steps.s01_harness import diff, load_harness
from steps.s02_executor import Sandbox
from steps.s03_tasks import initial_harness
from steps.s07_recursion import parallel_recursion, selector_prompt

print(selector_prompt(config.PROMPTS_DIR, 4))
if "--live" not in sys.argv[1:]:
    print("\nRun with --live to run parallel recursion (k = 2) on the real task.")
    raise SystemExit
k = int(sys.argv[sys.argv.index("--k") + 1]) if "--k" in sys.argv else 2

folder = config.WORKBUDDY_TASK
if not folder.is_dir():
    raise SystemExit(f"{folder.relative_to(config.ROOT)} not found: copy the task there first (see docs/running.md).")
task = workbuddy.load_task(folder)
stock, _ = load_harness(config.BASE_HARNESS_DIR)
h0 = initial_harness(stock, workbuddy.REFERENCE)
run_dir = config.RUNS_DIR / time.strftime("demo_l7_%Y%m%d-%H%M%S")
llm = LLM.from_env(config.LLM_SETTINGS, usage_log=run_dir / "usage.jsonl")
sandbox = Sandbox.from_docker(config.SANDBOX)

print(f"\nParallel recursion at k = {k}: {k} runs of H0, {2 * k} editors, {2 * k} probes, {k} composers, "
      f"{k} successor runs, then the selector. 15 to 60 minutes; nothing prints until it ends...", flush=True)
result = parallel_recursion(llm, sandbox, task, h0, run_dir, k=k, library=run_dir / "library",
                            prompts_dir=config.PROMPTS_DIR,
                            limits=config.ROLLOUT_LIMITS, max_turns=config.IMPROVER_MAX_TURNS, rng=random.Random())

def changed(harness) -> int:
    return sum(h0.files.get(p) != harness.files.get(p) for p in h0.files.keys() | harness.files.keys())


for c in [*result.step.candidates, *result.step.composed]:
    print(f"  {c.label}: " + (f"FELL BACK to H0 ({c.fallback})" if c.fallback else f"changed {changed(c.harness)} file(s)"))
selection = result.selection
if selection:
    (run_dir / "selection.md").write_text(f"{selection.why}\n\n" + "".join(f"- {i}: {label}\n" for i, label in selection.ids.items())
                                          + (f"\nFell back: {selection.fallback}\n" if selection.fallback else ""))
    print(f"\nThe selector chose {next(i for i, label in selection.ids.items() if label == result.chosen)}, "
          f"which was {result.chosen}" + (f" (fell back: {selection.fallback})" if selection.fallback else "")
          + f":\n{selection.why}")
(run_dir / "adopted.diff").write_text(diff(h0, result.adopted))
print(f"\nH★ is the harness behind {result.chosen}" + (" (H0 itself)" if result.adopted == h0 else ""))

runs = {**{r.label: r for r in result.step.refs}, **result.step.probes, **result.step.successors}
grades = {label: workbuddy.grade(sandbox, folder, r.workspace, final_reply=r.final_text) for label, r in runs.items()}
passed = {label: f"{sum(c.passed for c in g.checks)} of {len(g.checks)}" for label, g in grades.items()}
(run_dir / "grade.md").write_text("\n\n".join(
    f"## {label}: {passed[label]} checks\n" + "".join(f"- {c.name}: {c.detail}\n" for c in g.checks if not c.passed)
    for label, g in grades.items()))
print("\nFor you only, never for the pipeline (checks passed): "
      + ", ".join(f"{label} {p}" + (" <- delivered" if label == result.chosen else "") for label, p in passed.items())
      + ". One run each, so a few checks either way can be chance.")
print(f"Everything is under {run_dir.relative_to(config.ROOT)}/")
print("Usage meter:\n" + llm.meter.report())
