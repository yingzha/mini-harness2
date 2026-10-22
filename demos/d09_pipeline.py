"""Demo for Lesson 9 (steps/s09_pipeline.py): Harness² over a stream of real
tasks, then a Table 1-style evaluation, for you only.

    python -m demos.d09_pipeline                 # the stream (no API calls)
    python -m demos.d09_pipeline --live          # k = 1 ($3 to $5 and 10 to 45 minutes per task)
    python -m demos.d09_pipeline --live --k 2    # with selection, roughly twice that

Needs the stream's tasks in data/ (see README). The evaluation needs no extra
runs: each task's base runs are H0's runs, so H0's score is theirs, and
Harness²'s is the delivered output's. A live run is kept under
runs/demo_l9_<time>/: library/ as it grew, <task>/ for each task's recursion
and reflection, and report.md, the evaluation.
"""

import random
import sys
import time

import config
from benchmarks import workbuddy
from steps.s00_llm import LLM
from steps.s01_harness import load_harness
from steps.s02_executor import Sandbox
from steps.s03_tasks import initial_harness
from steps.s09_pipeline import run_stream

missing = [f.relative_to(config.ROOT) for f in config.WORKBUDDY_STREAM if not f.is_dir()]
if missing:
    raise SystemExit(f"Not found: {', '.join(map(str, missing))}. Copy the stream's tasks there first (see README).")
tasks = [workbuddy.load_task(f) for f in config.WORKBUDDY_STREAM]
folders = {t.id: f for t, f in zip(tasks, config.WORKBUDDY_STREAM)}
print("The stream, in order. Each task starts from H0; only the library carries over:")
print("".join(f"  {i}. {t.id}: {t.prompt.strip().splitlines()[0][:100]}\n" for i, t in enumerate(tasks, 1)))
if "--live" not in sys.argv[1:]:
    print("Run with --live to run Harness² over it.")
    raise SystemExit
k = int(sys.argv[sys.argv.index("--k") + 1]) if "--k" in sys.argv else 1

stock, _ = load_harness(config.BASE_HARNESS_DIR)
h0 = initial_harness(stock, workbuddy.REFERENCE)
run_dir = config.RUNS_DIR / time.strftime("demo_l9_%Y%m%d-%H%M%S")
llm = LLM.from_env(config.LLM_SETTINGS)
sandbox = Sandbox.from_docker(config.SANDBOX)


def spent() -> float:
    return sum(r.cost_usd for r in llm.meter.snapshot().values())


def score(task_id: str, workspace) -> float:
    return workbuddy.grade(sandbox, folders[task_id], workspace).score


rows = ["| Task | H0 | Harness² | Delivered | Library entry | $ |", "|---|---|---|---|---|---|"]
before = spent()
print(f"Running at k = {k}; each task reports when it is done.", flush=True)
for result in run_stream(llm, sandbox, tasks, h0, run_dir, k=k, prompts_dir=config.PROMPTS_DIR,
                         limits=config.ROLLOUT_LIMITS, max_turns=config.IMPROVER_MAX_TURNS, rng=random.Random()):
    task_id, recursion = result.task.id, result.recursion
    base = [score(task_id, r.workspace) for r in recursion.step.refs]
    delivered = score(task_id, recursion.delivered.workspace)
    cost, before = spent() - before, spent()
    rows.append(f"| {task_id} | {sum(base) / len(base):.3f} | {delivered:.3f} | {recursion.chosen} | "
                f"{'yes' if result.added_to_library else 'no'} | {cost:.2f} |")
    print(f"\n{task_id}: delivered {recursion.chosen}'s output; " +
          ("left a library entry." if result.added_to_library else "left nothing in the library.")
          + f"\n  lesson: {result.reflection.experience.splitlines()[0] if result.reflection.experience else 'NO_ENTRY'}"
          + f"\n  for you only: H0 {sum(base) / len(base):.3f}, Harness² {delivered:.3f} (fraction of checks); ${cost:.2f}",
          flush=True)

report = "\n".join(rows)
(run_dir / "report.md").write_text(
    f"# Harness² on {len(tasks)} WorkBuddy-Bench Office tasks, k = {k}\n\n{report}\n\n"
    "Scores are the fraction of each task's deterministic checks that pass. H0 is the mean over the task's "
    "base runs. One stream, one run per harness: differences of a few checks can be chance.\n")
print(f"\n{report}\n\nEverything is under {run_dir.relative_to(config.ROOT)}/")
print("Usage meter:\n" + llm.meter.report())
