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
* A long stream can be cut short, and only the library carries over, so a
  checkpoint is that library as each finished task left it. `resume` puts it
  back: the task that was running may have added its entry already, and a
  rerun would read its own lesson and then fail to add its entry again.
"""

from __future__ import annotations

import json
import random
import re
import shutil
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
    same H0). The library is folder/library/ as it stands: missing for a new
    stream (it starts empty), or as `resume` put it back. Each task's sessions
    and runs are kept in folder/<task id>/."""
    library = folder / "library"
    for task in tasks:
        recursion = parallel_recursion(llm, sandbox, task, h0, folder / task.id, k=k, library=library,
                                       prompts_dir=prompts_dir, limits=limits, max_turns=max_turns, rng=rng)
        reflection = reflect(llm, reflector_prompt(prompts_dir), task, h0, recursion, folder / task.id / "reflector",
                             max_turns=max_turns)
        added = update_library(library, task.id, h0, recursion.adopted, reflection)
        yield TaskResult(task, recursion, reflection, added)


# ---------------------------------------------------------------------------
# Resuming a stream that was cut short
# ---------------------------------------------------------------------------

def save_checkpoint(folder: Path, finished: Sequence[str]) -> None:
    """Record that the stream's first tasks, `finished`, are done, with the
    library as they left it, in folder/checkpoints/<how many>/. It is written
    under another name and then renamed, so a checkpoint cut off mid-write is
    never taken for a whole one."""
    partial = folder / "checkpoints" / f"{len(finished)}.partial"
    shutil.rmtree(partial, ignore_errors=True)
    if (folder / "library").is_dir():
        shutil.copytree(folder / "library", partial / "library")
    else:
        (partial / "library").mkdir(parents=True)
    (partial / "finished.json").write_text(json.dumps(list(finished)), encoding="utf-8")
    partial.rename(folder / "checkpoints" / str(len(finished)))


def resume(folder: Path, task_ids: Sequence[str]) -> int:
    """Put a stream's folder back as its last checkpoint left it, and return how
    many of `task_ids` (the whole stream, in order) are done. The library is
    restored, and the folder of any task not done is moved aside, so that the
    rerun of the task that was running starts clean."""
    whole = [p for p in (folder / "checkpoints").glob("*") if p.name.isdigit()]
    last = max(whole, key=lambda p: int(p.name), default=None)
    finished = json.loads((last / "finished.json").read_text(encoding="utf-8")) if last else []
    if list(task_ids[:len(finished)]) != finished:
        raise ValueError(f"{folder} is another stream's run: it finished {finished}")
    shutil.rmtree(folder / "library", ignore_errors=True)
    if last:
        shutil.copytree(last / "library", folder / "library")
    for task_id in task_ids[len(finished):]:
        if (folder / task_id).exists():
            taken = [int(m[1]) for p in folder.glob(f"{task_id}.interrupted*")
                     if (m := re.fullmatch(rf"{re.escape(task_id)}\.interrupted(\d+)", p.name))]
            (folder / task_id).rename(folder / f"{task_id}.interrupted{max(taken, default=0) + 1}")
    return len(finished)
