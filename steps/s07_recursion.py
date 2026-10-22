"""Lesson 7: Task-level recursion, and the blind selection of H★.

Paper anchors
-------------
* §2.2.2, Parallel recursion (Eq. 2): "The pipeline collects k reference
  executions of the current harness H, then independently proposes and probes
  k invariant and k domain-specific candidates. … Each of k independent
  composition sessions receives the full pool", and each successor H′_j is
  executed. "k controls its width rather than its depth."
* §2.2.2, Final selection: "For k > 1, an agentic selector compares anonymized
  deliverables against the task request and source materials. It returns an
  existing output without access to its originating harness or synthesizing
  new content. The corresponding harness is denoted H★, where the star
  indicates adoption rather than verified optimality. … At k = 1, both forms
  reduce to the basic contrastive step and bypass selection."
* Prompt 5: the selector's mission (prompts/selector.md).

Design
------
* Parallel recursion is Lesson 6's step, k wide, after k runs of H.
* The selector sees artifacts only: the request, the files, and each output
  under a shuffled id. Which run (and so which harness) an id stands for
  stays on our side, so H★ is always the harness that produced the chosen
  output. The pool is H's own runs plus every composed harness's run.
* An unreadable choice goes back to the selector once (`SendBackOnce`, as for
  invalid trees). If it is still unreadable, the first output, a run of H,
  is chosen and the fallback recorded: adopting nothing new is the safe end.
* Not built: sequential recursion (Eq. 3), which the paper's main tables
  don't use. It would chain k one-wide steps, each also given every earlier
  round's evidence, with its own composer prompt (Prompt 4).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from config import RolloutLimits
from steps.s00_llm import LLM
from steps.s01_harness import Harness
from steps.s02_executor import ExecutionRecord, Sandbox, Step, file_tools, run_agent_loop
from steps.s03_tasks import Task, write_task
from steps.s04_propose import SendBackOnce
from steps.s05_probe import probe
from steps.s06_compose import StepRecord, contrastive_step

_CHOICE = re.compile(r"```choice\s*\n\s*(\S+)\s*\n\s*```")
_WHY = re.compile(r"<why>(.*?)</why>", re.DOTALL)


@dataclass(frozen=True)
class Selection:
    """Which output the selector chose, and what it saw."""
    chosen: str                  # the chosen run's label
    ids: Mapping[str, str]       # anonymous id -> run label, as shown to the selector
    why: str                     # its reasoning, for people
    fallback: str                # why it fell back to the first output; "" if it didn't
    steps: tuple[Step, ...]      # the selector's own session


@dataclass(frozen=True)
class Recursion:
    """One task's task-level recursion: H★, the step behind it, and the selection."""
    step: StepRecord             # the base runs, the pool, the composers and their runs
    chosen: str                  # the label of the run whose output is delivered
    adopted: Harness             # H★: the harness that produced it
    selection: Selection | None  # None at k = 1, where there is nothing to select

    @property
    def delivered(self) -> ExecutionRecord:
        """The run whose output is submitted: a run of H, or of a composed harness."""
        return {r.label: r for r in [*self.step.refs, *self.step.successors.values()]}[self.chosen]


def selector_prompt(prompts_dir: Path, n: int) -> str:
    """Prompt 5, for choosing among n outputs."""
    return (prompts_dir / "selector.md").read_text(encoding="utf-8").format(n=n)


def anonymize(labels: list[str], rng: random.Random) -> dict[str, str]:
    """Shuffled ids c1..cn for the labels: an id says nothing about its run."""
    return {f"c{i}": label for i, label in enumerate(rng.sample(labels, len(labels)), 1)}


def _render(record: ExecutionRecord) -> str:
    """An output as the selector reads it: every file the run created or changed."""
    if not record.deliverable:
        return "(This run produced no files.)\n"
    return "".join(f"## {path}\n\n````\n{text}\n````\n\n" for path, text in sorted(record.deliverable.items()))


def select(llm: LLM, system: str, task: Task, outputs: Mapping[str, ExecutionRecord], session: Path, *,
           max_turns: int, rng: random.Random) -> Selection:
    """Blind selection (Prompt 5; system: from selector_prompt): the selector
    reads the task and each output under a shuffled id, in the folder
    `session`, and names one. Returns the label of the run it chose."""
    ids = anonymize(list(outputs), rng)
    context = session / "context"
    write_task(task, context)
    (context / "candidates").mkdir()
    for id_, label in ids.items():
        (context / "candidates" / f"{id_}.md").write_text(_render(outputs[label]), encoding="utf-8")

    def choice(text: str) -> str | None:
        found = [m for m in _CHOICE.findall(text) if m in ids]
        return found[-1] if found else None

    def unreadable(text: str) -> str | None:
        return None if choice(text) else (
            f"End your reply with a choice block naming exactly one of: {', '.join(ids)}.")

    tools = [t for t in file_tools(session, session) if t.name != "write_file"]   # it only reads
    result = run_agent_loop(llm, "selector", system, "Begin with context/task.md.", tools,
                            max_turns=max_turns, hooks=SendBackOnce(unreadable))
    why = (m[1].strip() if (m := _WHY.search(result.final_text)) else "")
    if chosen := choice(result.final_text):
        return Selection(ids[chosen], ids, why, "", result.steps)
    first = next(iter(outputs))
    return Selection(first, ids, why, f"no readable choice ({result.stop_reason}); took {first}", result.steps)


def parallel_recursion(llm: LLM, sandbox: Sandbox, task: Task, harness: Harness, folder: Path, *, k: int,
                       library: Path, prompts_dir: Path, limits: RolloutLimits, max_turns: int,
                       rng: random.Random) -> Recursion:
    """Eq. 2 and the final selection: k runs of `harness` (base1..k), the
    contrastive step k wide, then (for k > 1) a blind choice among the base
    runs and every composed harness's run. Everything is kept under `folder`."""
    files = write_task(task, folder / "task")
    base = probe(llm, sandbox, {f"base{i}": harness for i in range(1, k + 1)}, task.prompt, files,
                 folder / "base", limits)
    step = contrastive_step(llm, sandbox, task, harness, tuple(base.values()), folder / "step", k=k,
                            library=library, prompts_dir=prompts_dir, limits=limits, max_turns=max_turns)
    if k == 1:
        [composed] = step.composed
        return Recursion(step, composed.label, composed.harness, None)
    produced_by = {**{label: harness for label in base}, **{c.label: c.harness for c in step.composed}}
    outputs = {**base, **step.successors}
    selection = select(llm, selector_prompt(prompts_dir, len(outputs)), task, outputs, folder / "selector",
                       max_turns=max_turns, rng=rng)
    return Recursion(step, selection.chosen, produced_by[selection.chosen], selection)
