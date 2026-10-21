"""Lesson 5: Probe. Run each candidate on the same task, and contrast its run
with the reference.

Paper anchors
-------------
* §2.2.1, Probe: "Each candidate harness is executed on the same task under
  matched model and environment configurations. Comparing its trajectory and
  deliverable with those of the reference execution yields a behavioral
  contrast, providing evidence of whether the edits mitigate the targeted
  deficiency, leave the relevant behavior unchanged, or introduce
  regressions. These contrasts inform subsequent composition rather than
  verify task correctness, as execution stochasticity and shared model biases
  limit the reliability of the evidence."
* Prompt 3 (the composer, Lesson 6): "Each candidate was rolled out ONCE and
  you have that rollout."

Design
------
* Matched conditions by construction: every probe is the same `execute` call
  with the same model, task files, limits and sandbox, each in a fresh
  workspace. Only the harness differs, so a difference in behaviour is the
  edit's doing, or chance (one run each can't tell which apart).
* A contrast states facts, never a verdict: the two runs side by side, which
  harness components the probe actually used, and how the deliverables
  differ. Judging better or worse is the composer's job, without a grade.
* Probes run side by side: they are independent, and each mostly waits on
  the API.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from typing import Mapping

from config import RolloutLimits
from steps.s00_llm import LLM
from steps.s01_harness import SCRIPT_FILE, SKILL_SCRIPT, Harness, diff_files
from steps.s02_executor import ExecutionRecord, Sandbox, clip, execute


def probe(llm: LLM, sandbox: Sandbox, harnesses: Mapping[str, Harness], task: str, files_dir: Path,
          folder: Path, limits: RolloutLimits) -> dict[str, ExecutionRecord]:
    """Run each harness once on the same task, side by side, the run labelled
    with its key and kept in folder/<label>/."""

    def run(label: str, harness: Harness) -> ExecutionRecord:
        return execute(llm, sandbox, harness, task, files_dir, folder / label, limits, label=label)

    with ThreadPoolExecutor(max(len(harnesses), 1)) as pool:
        return dict(zip(harnesses, pool.map(run, harnesses, harnesses.values())))


def _counts(items: list[str]) -> str:
    return ", ".join(f"{item} x{n}" if n > 1 else item for item, n in sorted(Counter(items).items())) or "none"


def _components_used(record: ExecutionRecord) -> str:
    """The harness components the run reached for: an edit can only act
    through these, so an unused skill is not evidence that it doesn't help."""
    calls = [c for s in record.steps for c in s.calls]
    used = [f"skill {c.input.get('name')}" for c in calls if c.name == "load_skill"]
    used += [f"subagent {c.input.get('name')}" for c in calls if c.name == "run_subagent"]
    scripts = [str(PurePosixPath(s)) for c in calls   # ./scripts/x.py is scripts/x.py
               if c.name == "run_python" and isinstance(s := c.input.get("script"), str)]
    used += [f"script {s}" for s in scripts if SCRIPT_FILE.fullmatch(s) or SKILL_SCRIPT.fullmatch(s)]
    used += ["plugin note"] * sum(len(c.notes) for c in calls)
    # A before_finish hook's message, as the loop sends it (not one about a cut-off reply)
    used += ["plugin nudge"] * sum(bool(s.nudge and s.nudge.startswith("[plugin ")) for s in record.steps)
    return _counts(used)


def contrast(ref: ExecutionRecord, other: ExecutionRecord) -> str:
    """How `other`'s run differed from the reference's: facts, not a verdict."""
    rows = [
        ("stopped", lambda r: r.stop_reason),
        ("turns", lambda r: str(r.turns)),
        ("tool calls", lambda r: _counts([c.name for s in r.steps for c in s.calls])),
        ("tool errors", lambda r: str(r.tool_errors)),
        ("harness components used", _components_used),
        ("deliverable", lambda r: ", ".join(f"{p} ({len(t):,} chars)" for p, t in sorted(r.deliverable.items()))
                                  or "NOTHING"),
    ]
    table = "\n".join(f"| {name} | {cell(ref)} | {cell(other)} |" for name, cell in rows)
    changes = diff_files(ref.deliverable, other.deliverable)
    return (f"# {other.label} against {ref.label}\n\n"
            f"| | {ref.label} | {other.label} |\n|---|---|---|\n{table}\n\n"
            f"## Deliverable diff (- {ref.label}, + {other.label})\n\n"
            + (f"```diff\n{clip(changes)}```\n" if changes else "Identical.\n"))
