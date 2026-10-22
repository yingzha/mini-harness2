"""Lesson 4: Propose. Two editors, each changing its own copy of the harness.

Paper anchors
-------------
* §2.2.1, Propose: "The pipeline first obtains a reference execution
  e0 ~ A(q_t; M, H). … The reference reveals how the harness behaves, not
  whether its deliverable is correct." From the task, the current harness, the
  reference and the library, it proposes two candidates: the invariant one
  (INV) targets how the agent works, the domain one (DOM) what a practitioner
  knows. "Each candidate is an executable harness obtained by editing the
  current harness's component files."
* §D.2: every session "receives its evidence as files in a working directory
  rather than inlined in a prompt". "A session that returns an invalid tree …
  is retried once with the validator's message; if it fails again the stage
  inherits the tree it started from, and the fallback is recorded."
* Appendix H, Prompts 1 and 2: the editor's mission, in prompts/editor.md, with
  one dimension section per scope (prompts/editor_inv.md, editor_dom.md). Its
  last four sections, which the composer shares, are prompts/harness_rules.md.

Design
------
* An editor session is the Lesson 2 loop with other tools: it reads anything
  under context/, writes, copies into and deletes only in context/harness/,
  and runs no code. The composer (Lesson 6) runs the same session,
  `edit_session`, on more evidence.
* The files are the proposal: whatever is in context/harness/ when the session
  ends is loaded back as the candidate. The editor's reply is only its notes.
* Validation is a before_finish hook (`SendBackOnce`): when the editor says
  it's done, an invalid tree goes back to it with the validator's message, in
  the same session, once.
* No grade can reach an editor. The paper guards the folder; here the context
  is built only from a Task, a Harness and ExecutionRecords, and none of them
  can hold one.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from steps.s00_llm import LLM
from steps.s01_harness import Harness, load_harness, validate, write_harness
from steps.s02_executor import (ExecutionRecord, HookResult, Step, Tool, ToolResult, file_tools, render_record,
                                resolve_inside, run_agent_loop)
from steps.s03_tasks import Task, write_task

SCOPES = ("inv", "dom")   # how the agent works; what a practitioner knows

_START = "Begin with context/task.md."
_NOTES = re.compile(r"<notes>(.*?)</notes>", re.DOTALL)


@dataclass(frozen=True)
class Candidate:
    """The harness an editing session left, and why (§2.2.1): an editor's
    candidate to probe, or the composer's successor (Lesson 6)."""
    label: str                  # e.g. "inv1"
    harness: Harness            # the proposed tree; the tree it started from if it fell back
    notes: str                  # for each change, the moment in a trajectory behind it
    fallback: str               # why it fell back to the starting tree; "" if it didn't
    dropped: tuple[str, ...]    # files written off the editable surface, so left out
    steps: tuple[Step, ...]     # the editor's own session


def editor_prompt(prompts_dir: Path, scope: str, i: int, k: int) -> str:
    """Prompt 1 or 2: the shared mission with the scope's dimension section,
    for candidate i of k on that dimension."""
    shared = (prompts_dir / "editor.md").read_text(encoding="utf-8")
    dimension = (prompts_dir / f"editor_{scope}.md").read_text(encoding="utf-8")
    rules = (prompts_dir / "harness_rules.md").read_text(encoding="utf-8")
    return shared.format(dimension=dimension.strip(), rules=rules.strip(), i=i, k=k)


def build_context(context: Path, task: Task, harness: Harness, refs: Sequence[ExecutionRecord]) -> None:
    """Lay out an editor's evidence as files:

        task.md, files/          the task, as the agent got it
        harness/                 the harness it ran with: the editor's copy
        rollouts/<label>/        each reference run: trajectory.md, deliverable/
        library/                 finished harnesses from earlier tasks (filled from Lesson 8)
    """
    write_task(task, context)
    write_harness(harness, context / "harness")
    for record in refs:
        write_rollout(record, context / "rollouts" / record.label)
    (context / "library").mkdir()


def write_rollout(record: ExecutionRecord, folder: Path) -> None:
    """A run as evidence: folder/trajectory.md, and what it produced under folder/deliverable/."""
    folder.mkdir(parents=True)   # a second run with the same label would overwrite the first
    (folder / "trajectory.md").write_text(render_record(record), encoding="utf-8")
    for path, text in record.deliverable.items():
        target = resolve_inside(folder / "deliverable", path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def editor_tools(session: Path, harness_dir: Path) -> list[Tool]:
    """Read anything in the session; write, copy into or delete only in the
    harness copy. Nothing runs code: an editor reads scripts and plugins as text."""

    def editable(rel: str) -> Path:
        path = resolve_inside(session, rel)
        if not path.is_relative_to(harness_dir.resolve()):
            raise ValueError(f"{rel!r} is outside the harness you edit")
        return path

    def copy_file(inp: Mapping[str, Any]) -> ToolResult:
        source, target = resolve_inside(session, inp["source"]), editable(inp["target"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return ToolResult(f"Copied {inp['source']} to {inp['target']}")

    def delete_file(inp: Mapping[str, Any]) -> ToolResult:
        editable(inp["path"]).unlink()
        return ToolResult(f"Deleted {inp['path']}")

    path = {"type": "string"}
    return [*file_tools(session, harness_dir),
            Tool("copy_file", "Copy a file exactly, e.g. a component from another harness into yours.",
                 {"type": "object", "properties": {"source": path, "target": path}, "required": ["source", "target"]},
                 copy_file),
            Tool("delete_file", "Delete a file, to remove that component.",
                 {"type": "object", "properties": {"path": path}, "required": ["path"]}, delete_file)]


class SendBackOnce:
    """Hooks for a session whose result must be usable: when it says it's done,
    `problem` looks at its final reply and returns what is wrong, or None. A
    problem goes back to the session as a message, once (§D.2's retry)."""

    def __init__(self, problem: Callable[[str], str | None]) -> None:
        self._problem = problem
        self._sent_back = False

    def after_tool(self, event: dict[str, Any]) -> HookResult:
        return HookResult()

    def before_finish(self, event: dict[str, Any]) -> HookResult:
        if self._sent_back or (message := self._problem(event["final_text"])) is None:
            return HookResult()
        self._sent_back = True
        return HookResult((message,))


def _invalid(harness_dir: Path) -> str | None:
    """The validator's message for the tree in harness_dir, or None if it is valid."""
    problems = validate(load_harness(harness_dir)[0])
    if not problems:
        return None
    return ("Validation failed, so this harness would be discarded:\n" + "".join(f"- {p}\n" for p in problems)
            + "Fix it in context/harness/, then reply with your <notes> block again.")


def propose(llm: LLM, system: str, task: Task, harness: Harness, refs: Sequence[ExecutionRecord],
            session: Path, *, max_turns: int, label: str) -> Candidate:
    """One editor session (system: from editor_prompt) on the evidence, in the
    folder `session`."""
    build_context(session / "context", task, harness, refs)
    return edit_session(llm, "editor", system, harness, session, max_turns=max_turns, label=label)


def edit_session(llm: LLM, role: str, system: str, harness: Harness, session: Path, *, max_turns: int,
                 label: str) -> Candidate:
    """Run an editing session (as `role`: editor or composer) on the evidence in
    session/context/, whose harness/ holds `harness`. Returns the harness it left, or `harness` itself
    if that is invalid or the session didn't finish."""
    harness_dir = session / "context" / "harness"
    result = run_agent_loop(llm, role, system, _START, editor_tools(session, harness_dir),
                            max_turns=max_turns, hooks=SendBackOnce(lambda _: _invalid(harness_dir)))
    proposed, dropped = load_harness(harness_dir)
    notes = next((m[1].strip() for s in reversed(result.steps) if (m := _NOTES.search(s.text))), "")
    if result.stop_reason != "end_turn":   # a half-made edit is not a proposal
        fallback = f"the session ended unfinished ({result.stop_reason})"
    elif problems := validate(proposed):
        fallback = "still invalid after one retry: " + "; ".join(problems)
    else:
        return Candidate(label, proposed, notes, "", tuple(dropped), result.steps)
    return Candidate(label, harness, notes, fallback, tuple(dropped), result.steps)
