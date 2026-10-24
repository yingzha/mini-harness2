"""Lesson 8: Harnessing-level recursion. Reflect on the improvement record,
and update the library later tasks' editors read.

Paper anchors
-------------
* §2.3, Reflect: "After returning the deliverable, the pipeline reviews the
  complete improvement record, denoted by D_t. This record includes reference
  executions, candidate harnesses and probes, composition decisions, and the
  selected result. … Lessons are retained only when supported by execution
  contrasts; selecting an output alone does not establish transferability."
* Eq. 4: R_{t+1} = Update(R_t, H★_t, D_t). "Each library entry contains an
  executable harness and an EXPERIENCE.md recording the applicable situation,
  lessons, and supporting evidence. An index enables subsequent sessions to
  inspect relevant entries on demand. … When evidence is insufficient,
  reflection adds no new experience entry."
* §2.3, Reuse: "The next task starts from the common execution harness H0, but
  refinement is guided by the updated improvement harness R_{t+1}. Earlier
  components are selectively reused or adapted through Propose, rather than
  automatically inherited." Editors and composers read a copy of the library
  (Lesson 4's build_context).
* §D.2: "Executable components are retained rather than summarised as prose."
* Prompt 6: the reflector's mission (prompts/reflector.md).

Design
------
* The reflector reads everything, by name: every candidate (the rejected ones
  too), every composer's decisions, every run, and which output was submitted.
  It only reads; its reply is the record, and it never sees a grade.
* The library is a folder, one per stream ("The harness improvement library
  starts empty for each benchmark stream"):

      index.md                    one line per entry: what changed, and the lesson's cue
      entries/<task>/harness/     H★, the full tree
      entries/<task>/EXPERIENCE.md   the lesson (or why there is none), and what each edit did

  A task that adopted H0 itself and taught nothing adds nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from steps.s00_llm import LLM
from steps.s01_harness import Harness, write_harness
from steps.s02_executor import Step, file_tools, resolve_inside, run_agent_loop
from steps.s03_tasks import Task, write_task
from steps.s04_propose import SendBackOnce, write_rollout
from steps.s06_compose import write_candidate
from steps.s07_recursion import Recursion

_EDITS = re.compile(r"<edits>(.*?)</edits>", re.DOTALL)
_EXPERIENCE = re.compile(r"<experience>(.*?)</experience>", re.DOTALL)
_CUE = re.compile(r"^cue:\s*(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Reflection:
    """What the reflector wrote about one task's improvement record D_t."""
    edits: str                # one row per changed component: change, observed effect, verdict
    experience: str           # the one transferable lesson; "" for NO_ENTRY
    steps: tuple[Step, ...]   # the reflector's own session


def reflector_prompt(prompts_dir: Path) -> str:
    """Prompt 6."""
    return (prompts_dir / "reflector.md").read_text(encoding="utf-8")


def _submitted(recursion: Recursion) -> str:
    selection = recursion.selection
    if selection is None:
        return f"k = 1, so there was no selection: {recursion.chosen}'s output, the composed harness's run, was submitted.\n"
    return (f"Submitted: {recursion.chosen}'s output. The selector compared the outputs blind, under these ids:\n\n"
            + "".join(f"- {id_}: {label}\n" for id_, label in selection.ids.items())
            + f"\nIts reasoning:\n\n{selection.why or '(none given)'}\n")


def reflect(llm: LLM, system: str, task: Task, harness: Harness, recursion: Recursion, session: Path, *,
            max_turns: int) -> Reflection:
    """One reflector session (system: from reflector_prompt) over the whole
    record D_t, in the folder `session`. `harness` is the one every candidate
    edited (H0)."""
    context, step = session / "context", recursion.step
    write_task(task, context)
    write_harness(harness, context / "base_harness")
    for ref in step.refs:
        write_rollout(ref, context / "rollouts" / ref.label)
    for c in step.candidates:
        write_candidate(context / "candidates" / c.label, harness, c, step.probes[c.label], step.refs)
    for c in step.composed:
        write_candidate(context / "composed" / c.label, harness, c, step.successors[c.label], step.refs)
    (context / "selection.md").write_text(_submitted(recursion), encoding="utf-8")

    def no_rows(text: str) -> str | None:
        return None if _EDITS.search(text) else "End your reply with the <edits> block, then <experience> or NO_ENTRY."

    tools = [t for t in file_tools(session, session) if t.name != "write_file"]   # it only reads
    result = run_agent_loop(llm, "reflector", system, "Begin with context/task.md.", tools,
                            session=str(session), max_turns=max_turns, hooks=SendBackOnce(no_rows))
    edits = m[1].strip() if (m := _EDITS.search(result.final_text)) else ""
    experience = m[1].strip() if (m := _EXPERIENCE.search(result.final_text)) else ""
    return Reflection(edits, experience, result.steps)


def update_library(library: Path, task_id: str, base: Harness, adopted: Harness, reflection: Reflection) -> bool:
    """Eq. 4: add the task's entry, H★ and its EXPERIENCE.md, and a line in
    index.md. Returns whether it added one: not when H★ is the base harness and
    no lesson was supported. A task gets one entry; a second raises."""
    if adopted == base and not reflection.experience:
        return False
    entry = resolve_inside(library / "entries", task_id)
    write_harness(adopted, entry / "harness")   # raises if the task already has an entry
    lesson = reflection.experience or "NO_ENTRY: the record showed no concrete, reusable execution contrast."
    (entry / "EXPERIENCE.md").write_text(
        f"# {task_id}\n\n## Lesson\n\n{lesson}\n\n## What each edit did\n\n{reflection.edits or '(no rows)'}\n",
        encoding="utf-8")
    changed = sorted(p for p in base.files.keys() | adopted.files.keys() if base.files.get(p) != adopted.files.get(p))
    cue = m[1].strip() if (m := _CUE.search(reflection.experience)) else "no lesson"
    with (library / "index.md").open("a", encoding="utf-8") as index:
        index.write(f"- entries/{task_id}/: changed {', '.join(changed) or 'nothing'}. Cue: {cue}\n")
    return True
