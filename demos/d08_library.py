"""Demo for Lesson 8 (steps/s08_library.py): one task's recursion on the real
task, then the reflector reads the whole record and the library gets its entry.

    python -m demos.d08_library                # what the reflector is told (no API calls)
    python -m demos.d08_library --live         # k = 1 ($2 to $4, 10 to 45 minutes)
    python -m demos.d08_library --live --k 2   # with selection ($4 to $8, 15 to 60 minutes)

A live run is kept under runs/demo_l8_<time>/:
  base/, step/, selector/      the recursion, as in Lessons 6 and 7
  reflector/context/           exactly what the reflector saw: every candidate and run, and what was submitted
  library/                     the library after this task: index.md, entries/<task>/{harness/, EXPERIENCE.md}
  grade.md                     the delivered run's failed checks: for you only
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
from steps.s07_recursion import parallel_recursion
from steps.s08_library import reflect, reflector_prompt, update_library

print(reflector_prompt(config.PROMPTS_DIR))
if "--live" not in sys.argv[1:]:
    print("\nRun with --live to run one task's recursion and reflection on the real task.")
    raise SystemExit
k = int(sys.argv[sys.argv.index("--k") + 1]) if "--k" in sys.argv else 1

folder = config.WORKBUDDY_TASK
if not folder.is_dir():
    raise SystemExit(f"{folder.relative_to(config.ROOT)} not found: copy the task there first (see README).")
task = workbuddy.load_task(folder)
stock, _ = load_harness(config.BASE_HARNESS_DIR)
h0 = initial_harness(stock, workbuddy.REFERENCE)
run_dir = config.RUNS_DIR / time.strftime("demo_l8_%Y%m%d-%H%M%S")
library = run_dir / "library"   # a stream's library starts empty
llm = LLM.from_env(config.LLM_SETTINGS)
sandbox = Sandbox.from_docker(config.SANDBOX)

print(f"\nTask-level recursion at k = {k}, then the reflector (nothing prints until the end)...", flush=True)
result = parallel_recursion(llm, sandbox, task, h0, run_dir, k=k, library=library, prompts_dir=config.PROMPTS_DIR,
                            limits=config.ROLLOUT_LIMITS, max_turns=config.IMPROVER_MAX_TURNS, rng=random.Random())
reflection = reflect(llm, reflector_prompt(config.PROMPTS_DIR), task, h0, result, run_dir / "reflector",
                     max_turns=config.IMPROVER_MAX_TURNS)
added = update_library(library, task.id, h0, result.adopted, reflection)

print(f"\nDelivered: {result.chosen}'s output. H★ is " + ("H0 itself." if result.adopted == h0 else "an adapted harness."))
print(f"\nWhat each edit did, according to the reflector:\n{reflection.edits or '(no rows)'}")
print(f"\nThe lesson:\n{reflection.experience or 'NO_ENTRY: no concrete, reusable execution contrast.'}")
if added:
    print(f"\nThe library now holds, for the next task's editors to read:\n{(library / 'index.md').read_text()}")
else:
    print("\nNothing added to the library: H★ is H0 and no lesson was supported.")

g = workbuddy.grade(sandbox, folder, result.delivered.workspace)
(run_dir / "grade.md").write_text("".join(f"- {c.name}: {c.detail}\n" for c in g.checks if not c.passed))
print(f"For you only, never for the pipeline: the delivered output passed {sum(c.passed for c in g.checks)} "
      f"of {len(g.checks)} checks.")
print(f"Everything is under {run_dir.relative_to(config.ROOT)}/")
print("Usage meter:\n" + llm.meter.report())
