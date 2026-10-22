"""Demo for Lesson 6 (steps/s06_compose.py): one whole contrastive step Φ on the
real task. H0 runs once; then two editors propose, both candidates are probed,
the composer writes the successor H′, and H′ runs.

    python -m demos.d06_compose          # what the composer is told (no API calls)
    python -m demos.d06_compose --live   # the whole step (Opus and Haiku: $2 to $4, 10 to 45 minutes)

A live run is kept under runs/demo_l6_<time>/:
  h0/                       the reference run
  step/editors/<label>/     each editor's session; step/probes/<label>/ its candidate's run
  step/composers/composed1/context/   what the composer saw, with harness/ as it left it: H′
  step/successors/composed1/          H′'s run (its workspace); successor.md its trajectory
  composed.diff, composed.md   H′ against H0, and the composer's decisions
  grade.md                  every run's failed checks: for you only
"""

import sys
import time

import config
from benchmarks import workbuddy
from steps.s00_llm import LLM
from steps.s01_harness import diff, load_harness
from steps.s02_executor import Sandbox, execute, render_record
from steps.s03_tasks import initial_harness, write_task
from steps.s05_probe import contrast
from steps.s06_compose import composer_prompt, contrastive_step

rules = (config.PROMPTS_DIR / "harness_rules.md").read_text().strip()
print(composer_prompt(config.PROMPTS_DIR, 1, 1).replace(rules, "[prompts/harness_rules.md: the same rules the editors get]"))

if "--live" not in sys.argv[1:]:
    print("\nRun with --live to run one whole contrastive step on the real task.")
    raise SystemExit

folder = config.WORKBUDDY_TASK
if not folder.is_dir():
    raise SystemExit(f"{folder.relative_to(config.ROOT)} not found: copy the task there first (see docs/running.md).")
task = workbuddy.load_task(folder)
stock, _ = load_harness(config.BASE_HARNESS_DIR)
h0 = initial_harness(stock, workbuddy.REFERENCE)
run_dir = config.RUNS_DIR / time.strftime("demo_l6_%Y%m%d-%H%M%S")
llm = LLM.from_env(config.LLM_SETTINGS)
sandbox = Sandbox.from_docker(config.SANDBOX)

print("\nRunning H0 once, the reference (a minute or two)...", flush=True)
ref = execute(llm, sandbox, h0, task.prompt, write_task(task, run_dir / "task"), run_dir / "h0",
              config.ROLLOUT_LIMITS, label="h0")
print("Now the step: editors, probes, composer, successor (10 to 45 minutes; nothing prints until it ends)...",
      flush=True)
xi = contrastive_step(llm, sandbox, task, h0, [ref], run_dir / "step", k=1, library=run_dir / "library",
                      prompts_dir=config.PROMPTS_DIR,
                      limits=config.ROLLOUT_LIMITS, max_turns=config.IMPROVER_MAX_TURNS)

for c in xi.candidates:
    probe_table = contrast(ref, xi.probes[c.label]).split("\n## ")[0].strip()
    print(f"\n--- {c.label}: " + (f"FELL BACK to H0: {c.fallback}" if c.fallback else "proposed edits")
          + f"\n{probe_table}")
[composed] = xi.composed
successor = xi.successors[composed.label]
(run_dir / "composed.diff").write_text(diff(h0, composed.harness))
(run_dir / "composed.md").write_text(composed.notes)
(run_dir / "successor.md").write_text(render_record(successor))
print("\n--- composer: " + (f"FELL BACK to H0: {composed.fallback}" if composed.fallback else "decisions")
      + f"\n{composed.notes}")
print("\n" + contrast(ref, successor).split("\n## ")[0].strip())

runs = {"h0": ref, **xi.probes, "successor": successor}
grades = {label: workbuddy.grade(sandbox, folder, r.workspace) for label, r in runs.items()}
passed = {label: f"{sum(c.passed for c in g.checks)} of {len(g.checks)} checks" for label, g in grades.items()}
(run_dir / "grade.md").write_text("\n\n".join(
    f"## {label}: {passed[label]}\n" + "".join(f"- {c.name}: {c.detail}\n" for c in g.checks if not c.passed)
    for label, g in grades.items()))
print("\nFor you only, never for the pipeline: " + ", ".join(f"{label} {p}" for label, p in passed.items())
      + ". One run each, so a few checks either way can be chance.")
print(f"Everything is under {run_dir.relative_to(config.ROOT)}/")
print("Usage meter:\n" + llm.meter.report())
