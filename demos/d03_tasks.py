"""Demo for Lesson 3 (steps/s03_tasks.py), on one real WorkBuddy-Bench Office task.

    python -m demos.d03_tasks          # the task, and its checks on an empty workspace (no API calls)
    python -m demos.d03_tasks --live   # also run the base harness H0 on it (Haiku, a few cents)

Needs the task in data/ (see README). A live run is kept
under runs/demo_l3_<time>/: the task as the agent got it, the workspace, the
trajectory, and grade.md. grade.md holds expected values, so it is for you:
nothing in the pipeline may ever hand it to a model.
"""

import sys
import tempfile
import time
from pathlib import Path

import config
from benchmarks import workbuddy
from steps.s00_llm import LLM
from steps.s01_harness import load_harness
from steps.s02_executor import Sandbox, execute, render_record
from steps.s03_tasks import Grade, initial_harness, write_task

def summary(g: Grade) -> str:
    failed = [c.name for c in g.checks if not c.passed]
    return (f"score {g.score:.2f} ({len(g.checks) - len(failed)} of {len(g.checks)} checks pass)"
            + "".join(f"\n      FAIL {name}" for name in failed[:12])
            + (f"\n      ... and {len(failed) - 12} more" if len(failed) > 12 else ""))


folder = config.WORKBUDDY_TASK
if not folder.is_dir():
    raise SystemExit(f"{folder.relative_to(config.ROOT)} not found: copy the task there first (see README).")
task = workbuddy.load_task(folder)
stock, _ = load_harness(config.BASE_HARNESS_DIR)
h0 = initial_harness(stock, workbuddy.REFERENCE)
print(f"Task {task.id}. The agent gets this request:\n\n{task.prompt}\n")
print("and these files:\n" + "".join(f"  {path} ({len(data):,} bytes)\n" for path, data in sorted(task.files.items())))
print(f"H0's system prompt (the stock harness plus the benchmark's reference instructions):\n\n{h0.files['systemprompt.md']}")

sandbox = Sandbox.from_docker(config.SANDBOX)
with tempfile.TemporaryDirectory() as scratch:
    untouched = write_task(task, Path(scratch) / "task")
    print("Baseline: the task's own checks on its workspace before anyone works on it (0 is expected):\n  "
          + summary(workbuddy.grade(sandbox, folder, untouched)))

if "--live" not in sys.argv[1:]:
    print("\nRun with --live to see how H0 does.")
    raise SystemExit

run_dir = config.RUNS_DIR / time.strftime("demo_l3_%Y%m%d-%H%M%S")
llm = LLM.from_env(config.LLM_SETTINGS)
print("\nRunning H0 on the task; this takes a minute or two and prints when it's done...", flush=True)
files = write_task(task, run_dir / "task")
record = execute(llm, sandbox, h0, task.prompt, files, run_dir / "workspace", config.ROLLOUT_LIMITS, label="h0")
(run_dir / "h0.md").write_text(render_record(record))
g = workbuddy.grade(sandbox, folder, record.workspace)
(run_dir / "grade.md").write_text("\n".join(f"- [{'x' if c.passed else ' '}] {c.name}: {c.detail}" for c in g.checks))
print(f"\nH0: {record.stop_reason} after {record.turns} turns, {record.tool_calls} tool calls "
      f"({record.tool_errors} errors); produced {', '.join(record.deliverable) or 'nothing'}")
print("  " + summary(g))
print(f"\nTrajectory and grade: {run_dir.relative_to(config.ROOT)}/")
print("Usage meter:\n" + llm.meter.report())
