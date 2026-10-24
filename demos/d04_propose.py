"""Demo for Lesson 4 (steps/s04_propose.py): two editors watch H0 work on the
real task, and each proposes a changed harness.

    python -m demos.d04_propose          # what each editor is told (no API calls)
    python -m demos.d04_propose --live   # run H0 once (Haiku), then the INV and DOM editors (Opus: about $2.50, 5 to 30 minutes)

A live run is kept under runs/demo_l4_<time>/:
  h0/                         the reference run: workspace/ and trajectory.md
  editors/<label>/context/    exactly what that editor saw, with its harness/ as it left it
  editors/<label>.diff        its candidate against H0, and <label>.md its notes
  grade.md                    how H0 scored, for you: no editor ever sees it
  usage.jsonl                 every model call's tokens and cost, by session
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor

import config
from benchmarks import workbuddy
from steps.s00_llm import LLM
from steps.s01_harness import diff, load_harness
from steps.s02_executor import Sandbox, execute, render_record
from steps.s03_tasks import initial_harness, write_task
from steps.s04_propose import SCOPES, editor_prompt, propose

print(editor_prompt(config.PROMPTS_DIR, "inv", 1, 1))
dom = (config.PROMPTS_DIR / "editor_dom.md").read_text()
print(f"\n{'=' * 72}\nThat was the INV editor's prompt. The DOM editor's is the same, "
      f"except that its dimension section is:\n\n{dom}")

if "--live" not in sys.argv[1:]:
    print("Run with --live to watch both editors work on H0's run of the real task.")
    raise SystemExit

folder = config.WORKBUDDY_TASK
if not folder.is_dir():
    raise SystemExit(f"{folder.relative_to(config.ROOT)} not found: copy the task there first (see docs/running.md).")
task = workbuddy.load_task(folder)
stock, _ = load_harness(config.BASE_HARNESS_DIR)
h0 = initial_harness(stock, workbuddy.REFERENCE)
run_dir = config.RUNS_DIR / time.strftime("demo_l4_%Y%m%d-%H%M%S")
llm = LLM.from_env(config.LLM_SETTINGS, usage_log=run_dir / "usage.jsonl")
sandbox = Sandbox.from_docker(config.SANDBOX)

print("\nRunning H0 once: the reference run the editors learn from (a minute or two)...", flush=True)
files = write_task(task, run_dir / "task")
ref = execute(llm, sandbox, h0, task.prompt, files, run_dir / "h0" / "workspace", config.ROLLOUT_LIMITS, label="h0")
(run_dir / "h0" / "trajectory.md").write_text(render_record(ref))
print(f"H0: {ref.stop_reason} after {ref.turns} turns, {ref.tool_calls} tool calls ({ref.tool_errors} errors); "
      f"produced {', '.join(ref.deliverable) or 'nothing'}")

print("\nNow the INV and DOM editors, side by side (Opus; 5 to 30 minutes, "
      "and nothing prints until both finish)...", flush=True)
editors = run_dir / "editors"
with ThreadPoolExecutor(len(SCOPES)) as pool:
    jobs = [pool.submit(propose, llm, editor_prompt(config.PROMPTS_DIR, scope, 1, 1), task, h0, [ref],
                        editors / f"{scope}1", library=run_dir / "library", max_turns=config.IMPROVER_MAX_TURNS,
                        label=f"{scope}1")
            for scope in SCOPES]
    candidates = [job.result() for job in jobs]

for c in candidates:
    changed = sorted(p for p in h0.files.keys() | c.harness.files.keys() if h0.files.get(p) != c.harness.files.get(p))
    (editors / f"{c.label}.diff").write_text(diff(h0, c.harness))
    (editors / f"{c.label}.md").write_text(c.notes)
    print(f"\n--- {c.label}: {len(c.steps)} turns; "
          + (f"FELL BACK to H0: {c.fallback}" if c.fallback else f"changed {', '.join(changed) or 'nothing'}")
          + (f"\n    dropped (off the editable surface): {', '.join(c.dropped)}" if c.dropped else "")
          + f"\n{c.notes}")

g = workbuddy.grade(sandbox, folder, ref.workspace, final_reply=ref.final_text)
(run_dir / "grade.md").write_text("\n".join(f"- [{'x' if c.passed else ' '}] {c.name}: {c.detail}" for c in g.checks))
print(f"\nFor you only: H0 scored {g.score:.2f} ({sum(c.passed for c in g.checks)} of {len(g.checks)} checks). "
      "Compare grade.md's failures with what the editors noticed.")
print(f"Everything is under {run_dir.relative_to(config.ROOT)}/")
print("Usage meter:\n" + llm.meter.report())
