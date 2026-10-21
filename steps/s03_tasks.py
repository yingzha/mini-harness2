"""Lesson 3: tasks, and how one is handed to the agent.

Paper anchors
-------------
* §2.1: harness evolution runs over "a stream of N open-world tasks q1, …, qN,
  without ground-truth answers or labeled validation feedback". Every task
  starts from H0.
* §D.1: H0 is the agent's stock harness "extended with the benchmark's
  reference instructions".
* Appendix B: a benchmark grades with its own checks; "the score of a task is
  the fraction of its checks that pass", and "the verifier never exposes its
  expected values to any model in our pipeline".

Design
------
* A task is the request plus the files the agent starts with. Nothing in it
  says how it will be graded: the method (Lessons 4 to 9) never sees a score.
* Grading belongs to the benchmark (benchmarks/workbuddy.py runs a real task's
  own checks) and is only for watching the method work: demos, smoke tests,
  evaluation. `Check` and `Grade` are the shape a benchmark reports in.
* `initial_harness` builds a benchmark's H0, so the stock harness assumes no
  folder layout: where inputs are and where results go is the benchmark's to say.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from steps.s01_harness import Harness
from steps.s02_executor import resolve_inside


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str                  # task.md: the request
    files: Mapping[str, bytes]   # what the agent starts with, by workspace path


def write_task(task: Task, folder: Path) -> Path:
    """What the requester hands over: folder/task.md, and the task's files under
    folder/files/, the workspace a rollout starts from. Returns that files
    folder. A path that would land outside it is refused: task files can come
    from a downloaded archive."""
    if folder.exists() and any(folder.iterdir()):
        raise FileExistsError(f"{folder} is not empty; a task is written into a fresh folder")
    files = folder / "files"
    files.mkdir(parents=True)
    (folder / "task.md").write_text(task.prompt, encoding="utf-8")
    for path, data in task.files.items():
        target = resolve_inside(files, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return files


def initial_harness(stock: Harness, reference: str) -> Harness:
    """H0 for a benchmark (§D.1): the stock harness with the benchmark's reference
    instructions added to its system prompt, the one file every call sees."""
    prompt = stock.files.get("systemprompt.md", "").rstrip()
    return Harness({**stock.files, "systemprompt.md": f"{prompt}\n\n{reference.strip()}\n"})


@dataclass(frozen=True)
class Check:
    name: str            # the requirement, in words
    passed: bool
    detail: str = ""     # what was wrong; it may hold expected values, so it is for people only


@dataclass(frozen=True)
class Grade:
    checks: tuple[Check, ...]

    @property
    def score(self) -> float:
        """Appendix B: the fraction of checks that pass."""
        return sum(c.passed for c in self.checks) / len(self.checks)
