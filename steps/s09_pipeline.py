"""Lesson 9: The whole Harness² loop over a stream of tasks.

Paper anchors
-------------
* §2.1: the method runs over "a stream of N open-world tasks q1, …, qN,
  without ground-truth answers or labeled validation feedback".
* Fig. 3: for each task, task-level recursion refines a harness from H0 and
  delivers an output; then harnessing-level recursion updates the improvement
  harness. "Move to the next task."
* §2.3, Reuse: "The next task starts from the common execution harness H0, but
  refinement is guided by the updated improvement harness R_{t+1}. Earlier
  components are selectively reused or adapted through Propose, rather than
  automatically inherited."
* §3.1: "The harness improvement library starts empty for each benchmark
  stream and is updated after each task."

Design
------
* `run_stream` is the loop and nothing else: for each task, in order,
  parallel recursion from H0 with the library as it stands, then reflection,
  then the library update. Only the library carries from one task to the next.
* It yields each task's result as soon as that task is done, so an entry point
  can report progress and cost per task instead of going quiet for an hour.
* Nothing here grades. Scoring a stream is evaluation, and the method never
  sees it (demos/d09_pipeline.py does it, through benchmarks/).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from config import RolloutLimits
from steps.s00_llm import LLM
from steps.s01_harness import Harness
from steps.s02_executor import Sandbox
from steps.s03_tasks import Task
from steps.s07_recursion import Recursion, parallel_recursion
from steps.s08_library import Reflection, reflect, reflector_prompt, update_library


@dataclass(frozen=True)
class TaskResult:
    """One task of the stream: what was delivered, and how it came about."""
    task: Task
    recursion: Recursion          # H★, the delivered run (.delivered), and the record D_t
    reflection: Reflection        # what the reflector made of D_t
    added_to_library: bool        # whether the task left an entry for later tasks


def run_stream(llm: LLM, sandbox: Sandbox, tasks: Sequence[Task], h0: Harness, folder: Path, *, k: int,
               prompts_dir: Path, limits: RolloutLimits, max_turns: int, rng: random.Random) -> Iterator[TaskResult]:
    """Harness² over `tasks`, in order, all from the same benchmark (so the
    same H0). The stream's library starts empty in folder/library/; each
    task's sessions and runs are kept in folder/<task id>/."""
    library = folder / "library"
    for task in tasks:
        recursion = parallel_recursion(llm, sandbox, task, h0, folder / task.id, k=k, library=library,
                                       prompts_dir=prompts_dir, limits=limits, max_turns=max_turns, rng=rng)
        reflection = reflect(llm, reflector_prompt(prompts_dir), task, h0, recursion, folder / task.id / "reflector",
                             max_turns=max_turns)
        added = update_library(library, task.id, h0, recursion.adopted, reflection)
        yield TaskResult(task, recursion, reflection, added)
