"""Lesson 6: Compose, and the whole contrastive step Φ.

Paper anchors
-------------
* §2.2.1, Compose: "The pipeline reads the reference, candidate harnesses,
  their diffs against the current harness, and all available task-local
  execution evidence to form the successor H′. Composition is selective: it
  may merge supported changes, revise conflicting edits, adopt one candidate,
  or preserve the current harness. Each decision is tied to a concrete
  observation rather than a presumed score gain. The composed harness is then
  executed to produce e′, and the decisions and their evidence are recorded
  in ξ."
* Eq. 1: (H′, e′, ξ) = Φ(q_t, H, E; R_t). One contrastive step returns the
  successor harness, its execution record and the step record ξ.
* Prompt 3: the composer's mission (prompts/composer.md), which shares
  Prompt 1's last four sections (prompts/harness_rules.md).

Design
------
* The composer runs the same editing session as the editors (`edit_session`)
  on more evidence: every candidate's tree, diff, notes, run and contrasts.
  Its copy starts as the current harness, so KEEP_BASE means leaving it alone.
* `contrastive_step` is Φ: propose INV and DOM side by side, probe both,
  compose, run the successor. The reference runs (E) are passed in, so the
  caller decides how many there are and can reuse them.
* ξ is a value, `StepRecord`. Every session and run also stays on disk under
  the step's folder, for people (and, from Lesson 8, the reflector) to read.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from config import RolloutLimits
from steps.s00_llm import LLM
from steps.s01_harness import Harness, diff, write_harness
from steps.s02_executor import ExecutionRecord, Sandbox, execute
from steps.s03_tasks import Task, write_task
from steps.s04_propose import SCOPES, Candidate, build_context, edit_session, editor_prompt, propose, write_rollout
from steps.s05_probe import contrast, probe


@dataclass(frozen=True)
class StepRecord:
    """ξ (Eq. 1): what one contrastive step saw, decided and produced."""
    refs: tuple[ExecutionRecord, ...]        # runs of the current harness H
    candidates: tuple[Candidate, ...]        # the INV and DOM proposals
    probes: Mapping[str, ExecutionRecord]    # each candidate's run, by its label
    composed: Candidate                      # H′ (composed.harness) and the composer's decisions
    successor: ExecutionRecord               # e′: H′'s run


def composer_prompt(prompts_dir: Path, j: int, k: int) -> str:
    """Prompt 3, for composer j of k composing from the same evidence."""
    template = (prompts_dir / "composer.md").read_text(encoding="utf-8")
    rules = (prompts_dir / "harness_rules.md").read_text(encoding="utf-8")
    return template.format(rules=rules.strip(), j=j, k=k)


def compose(llm: LLM, system: str, task: Task, harness: Harness, refs: Sequence[ExecutionRecord],
            candidates: Sequence[Candidate], probes: Mapping[str, ExecutionRecord], session: Path, *,
            max_turns: int) -> Candidate:
    """One composer session (system: from composer_prompt) in the folder
    `session`. Its evidence is the editors' plus, for each candidate:

        candidates/<label>/harness/        its full tree
        candidates/<label>/diff.patch      its edits against the current harness
        candidates/<label>/notes.md        its editor's reasons
        candidates/<label>/rollout/        its probe run
        candidates/<label>/contrast-<ref>.md   that run beside each reference run
    """
    context = session / "context"
    build_context(context, task, harness, refs)
    for c in candidates:
        folder = context / "candidates" / c.label
        write_harness(c.harness, folder / "harness")
        (folder / "diff.patch").write_text(diff(harness, c.harness), encoding="utf-8")
        fell_back = f"This candidate fell back to the current harness: {c.fallback}\n\n" if c.fallback else ""
        (folder / "notes.md").write_text(fell_back + (c.notes or "(no notes)"), encoding="utf-8")
        write_rollout(probes[c.label], folder / "rollout")
        for ref in refs:
            (folder / f"contrast-{ref.label}.md").write_text(contrast(ref, probes[c.label]), encoding="utf-8")
    return edit_session(llm, "composer", system, harness, session, max_turns=max_turns, label="composed")


def contrastive_step(llm: LLM, sandbox: Sandbox, task: Task, harness: Harness, refs: Sequence[ExecutionRecord],
                     folder: Path, *, prompts_dir: Path, limits: RolloutLimits, max_turns: int) -> StepRecord:
    """Φ (Eq. 1): from the reference runs of `harness`, propose INV and DOM
    candidates, probe each, compose the successor H′, and run it. Every
    session and run is kept under `folder`."""
    files = write_task(task, folder / "task")
    with ThreadPoolExecutor(len(SCOPES)) as pool:
        jobs = [pool.submit(propose, llm, editor_prompt(prompts_dir, scope, 1, 1), task, harness, refs,
                            folder / "editors" / f"{scope}1", max_turns=max_turns, label=f"{scope}1")
                for scope in SCOPES]
        candidates = tuple(job.result() for job in jobs)
    probes = probe(llm, sandbox, {c.label: c.harness for c in candidates}, task.prompt, files,
                   folder / "probes", limits)
    composed = compose(llm, composer_prompt(prompts_dir, 1, 1), task, harness, refs, candidates, probes,
                       folder / "composer", max_turns=max_turns)
    successor = execute(llm, sandbox, composed.harness, task.prompt, files, folder / "successor", limits,
                        label="successor")
    return StepRecord(tuple(refs), candidates, probes, composed, successor)
