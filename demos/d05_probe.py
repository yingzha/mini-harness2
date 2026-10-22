"""Demo for Lesson 5 (steps/s05_probe.py): run H0 and Lesson 4's candidates side
by side on the real task, and contrast each candidate's run with H0's. Live:
three Haiku runs, a few cents and a few minutes.

    python -m demos.d05_probe                       # candidates from the latest runs/demo_l4_*/
    python -m demos.d05_probe runs/demo_l4_<time>   # or from that run

It reuses Lesson 4's candidates rather than paying for the editors again. The
reference is a fresh H0 run in the same batch, so all three run under the same
conditions at the same time (in the pipeline, Lesson 6, the reference is the
run the editors read).

Kept under runs/demo_l5_<time>/: each run's workspace (workspaces/<label>/) and
trajectory (<label>.md), each contrast (<label>-vs-h0.md), and grade.md, every
run's failed checks: for you only.
"""

import sys
import time
from pathlib import Path

import config
from benchmarks import workbuddy
from steps.s00_llm import LLM
from steps.s01_harness import load_harness
from steps.s02_executor import Sandbox, render_record
from steps.s03_tasks import initial_harness, write_task
from steps.s05_probe import contrast, probe

folder = config.WORKBUDDY_TASK
if not folder.is_dir():
    raise SystemExit(f"{folder.relative_to(config.ROOT)} not found: copy the task there first (see docs/running.md).")
editors = Path(sys.argv[1]).resolve() / "editors" if sys.argv[1:] else max(config.RUNS_DIR.glob("demo_l4_*/editors"), default=None)
if editors is None or not editors.is_dir():
    raise SystemExit("No Lesson 4 candidates found: run `python -m demos.d04_propose --live` first.")

task = workbuddy.load_task(folder)
stock, _ = load_harness(config.BASE_HARNESS_DIR)
harnesses = {"h0": initial_harness(stock, workbuddy.REFERENCE)}
for proposal in sorted(editors.glob("*.diff")):
    label = proposal.stem
    if proposal.read_text():   # the candidate differs from H0, so its tree is what the editor left
        harnesses[label], _ = load_harness(editors / label / "context" / "harness")
    else:                      # it fell back to H0 or kept it: nothing new to probe
        print(f"Skipping {label}: Lesson 4 kept H0 for it")
print(f"Candidates from {editors.parent.relative_to(config.ROOT)}: {', '.join(list(harnesses)[1:]) or 'none'}")

run_dir = config.RUNS_DIR / time.strftime("demo_l5_%Y%m%d-%H%M%S")
llm = LLM.from_env(config.LLM_SETTINGS)
sandbox = Sandbox.from_docker(config.SANDBOX)
files = write_task(task, run_dir / "task")
print(f"\nProbing {', '.join(harnesses)} side by side (Haiku; a few minutes)...", flush=True)
records = probe(llm, sandbox, harnesses, task.prompt, files, run_dir / "workspaces", config.ROLLOUT_LIMITS)

for label, record in records.items():
    (run_dir / f"{label}.md").write_text(render_record(record))
    if label != "h0":
        text = contrast(records["h0"], record)
        (run_dir / f"{label}-vs-h0.md").write_text(text)
        print("\n" + text.split("\n## ")[0].strip())   # the table; the diff is in the file

grades = {label: workbuddy.grade(sandbox, folder, record.workspace) for label, record in records.items()}
passed = {label: f"{sum(c.passed for c in g.checks)} of {len(g.checks)} checks" for label, g in grades.items()}
(run_dir / "grade.md").write_text("\n\n".join(
    f"## {label}: {passed[label]}\n" + "".join(f"- {c.name}: {c.detail}\n" for c in g.checks if not c.passed)
    for label, g in grades.items()))
print("\nFor you only, never for the pipeline: " + ", ".join(f"{label} {p}" for label, p in passed.items())
      + ". One run each, so a few checks either way can be chance.")
print(f"Everything is under {run_dir.relative_to(config.ROOT)}/")
print("Usage meter:\n" + llm.meter.report())
