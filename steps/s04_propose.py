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
  one dimension section per scope (prompts/editor_inv.md, editor_dom.md).

Design
------
* An editor session is the Lesson 2 loop with other tools: it reads anything
  under context/, writes and deletes only in context/harness/, and runs no code.
* The files are the proposal: whatever is in context/harness/ when the session
  ends is loaded back as the candidate. The editor's reply is only its notes.
* Validation is a before_finish hook: when the editor says it's done, an
  invalid tree goes back to it with the validator's message, in the same
  session, once.
* No grade can reach an editor. The paper guards the folder; here the context
  is built only from a Task, a Harness and ExecutionRecords, and none of them
  can hold one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

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
    """One editor's proposal (§2.2.1): a harness to probe, and why."""
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
    return shared.format(dimension=dimension.strip(), i=i, k=k)


def build_context(context: Path, task: Task, harness: Harness, refs: Sequence[ExecutionRecord]) -> Path:
    """Lay out an editor's evidence as files and return the harness folder it edits:

        task.md, files/          the task, as the agent got it
        harness/                 the harness it ran with: the editor's copy
        rollouts/<label>/        each reference run: trajectory.md, deliverable/
        library/                 finished harnesses from earlier tasks (filled from Lesson 8)
    """
    write_task(task, context)
    write_harness(harness, context / "harness")
    for record in refs:
        rollout = context / "rollouts" / record.label
        rollout.mkdir(parents=True)   # a second run with the same label would overwrite the first
        (rollout / "trajectory.md").write_text(render_record(record), encoding="utf-8")
        for path, text in record.deliverable.items():
            target = resolve_inside(rollout / "deliverable", path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    (context / "library").mkdir()
    return context / "harness"


def editor_tools(session: Path, harness_dir: Path) -> list[Tool]:
    """Read anything in the session, write or delete only in the harness copy.
    Nothing runs code: an editor reads scripts and plugins as text."""

    def delete_file(inp: Mapping[str, Any]) -> ToolResult:
        path = resolve_inside(session, inp["path"])
        if not path.is_relative_to(harness_dir.resolve()):
            raise ValueError(f"{inp['path']!r} is outside the harness you edit")
        path.unlink()
        return ToolResult(f"Deleted {inp['path']}")

    return [*file_tools(session, harness_dir),
            Tool("delete_file", "Delete a file, to remove that component.",
                 {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
                 delete_file)]


class _ValidateOnFinish:
    """When the editor says it's done, send an invalid tree back with the
    validator's message, once (§D.2)."""

    def __init__(self, harness_dir: Path) -> None:
        self._harness_dir = harness_dir
        self._sent_back = False

    def after_tool(self, event: dict[str, Any]) -> HookResult:
        return HookResult()

    def before_finish(self, event: dict[str, Any]) -> HookResult:
        problems = validate(load_harness(self._harness_dir)[0])
        if self._sent_back or not problems:
            return HookResult()
        self._sent_back = True
        return HookResult((
            "Validation failed, so this harness would be discarded:\n"
            + "".join(f"- {p}\n" for p in problems)
            + "Fix it in context/harness/, then reply with your <notes> block again.",))


def propose(llm: LLM, system: str, task: Task, harness: Harness, refs: Sequence[ExecutionRecord],
            session: Path, *, max_turns: int, label: str) -> Candidate:
    """One editor session (system: from editor_prompt) on the evidence, in the
    folder `session`. Returns the harness it left, or the starting harness if
    that is invalid or the session didn't finish."""
    harness_dir = build_context(session / "context", task, harness, refs)
    result = run_agent_loop(llm, "editor", system, _START, editor_tools(session, harness_dir),
                            max_turns=max_turns, hooks=_ValidateOnFinish(harness_dir))
    proposed, dropped = load_harness(harness_dir)
    notes = next((m[1].strip() for s in reversed(result.steps) if (m := _NOTES.search(s.text))), "")
    if result.stop_reason != "end_turn":   # a half-made edit is not a proposal
        fallback = f"the session ended unfinished ({result.stop_reason})"
    elif problems := validate(proposed):
        fallback = "still invalid after one retry: " + "; ".join(problems)
    else:
        return Candidate(label, proposed, notes, "", tuple(dropped), result.steps)
    return Candidate(label, harness, notes, fallback, tuple(dropped), result.steps)
