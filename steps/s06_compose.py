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
* Eq. 2 (Lesson 7) widens the same step: k candidates per scope, and k
  composers that each receive the whole pool. At k = 1 it is Eq. 1.
* Prompt 3: the composer's mission (prompts/composer.md), which shares
  Prompt 1's last four sections (prompts/harness_rules.md).

Design
------
* The composer runs the same editing session as the editors (`edit_session`)
  on more evidence: every candidate's tree, diff, notes, run and contrasts.
  Its copy starts as the current harness, so KEEP_BASE means leaving it alone.
* `contrastive_step` is Φ, k wide: propose k INV and k DOM candidates side by
  side, probe them all, compose k successors, run each. The reference runs
  (E) are passed in, so the caller decides how many there are.
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
from steps.s02_executor import ExecutionRecord, Sandbox
from steps.s03_tasks import Task, write_task
from steps.s04_propose import SCOPES, Candidate, build_context, edit_session, editor_prompt, propose, write_rollout
from steps.s05_probe import contrast, probe


@dataclass(frozen=True)
class StepRecord:
    """ξ (Eq. 1): what one contrastive step saw, decided and produced."""
    refs: tuple[ExecutionRecord, ...]           # runs of the current harness H
    candidates: tuple[Candidate, ...]           # the INV and DOM proposals
    probes: Mapping[str, ExecutionRecord]       # each candidate's run, by its label
    composed: tuple[Candidate, ...]             # each H′ (.harness) with its composer's decisions
    successors: Mapping[str, ExecutionRecord]   # each e′: its H′'s run, by the same label


def composer_prompt(prompts_dir: Path, j: int, k: int) -> str:
    """Prompt 3, for composer j of k composing from the same evidence."""
    template = (prompts_dir / "composer.md").read_text(encoding="utf-8")
    rules = (prompts_dir / "harness_rules.md").read_text(encoding="utf-8")
    return template.format(rules=rules.strip(), j=j, k=k)


def write_candidate(folder: Path, harness: Harness, candidate: Candidate, run: ExecutionRecord,
                    refs: Sequence[ExecutionRecord]) -> None:
    """A candidate as evidence, against the harness it edited:

        harness/               its full tree
        diff.patch             its edits against `harness`
        notes.md               its session's notes (an editor's reasons, a composer's decisions)
        rollout/               its run
        contrast-<ref>.md      that run beside each reference run
    """
    write_harness(candidate.harness, folder / "harness")
    (folder / "diff.patch").write_text(diff(harness, candidate.harness), encoding="utf-8")
    fell_back = f"This candidate fell back to the current harness: {candidate.fallback}\n\n" if candidate.fallback else ""
    (folder / "notes.md").write_text(fell_back + (candidate.notes or "(no notes)"), encoding="utf-8")
    write_rollout(run, folder / "rollout")
    for ref in refs:
        (folder / f"contrast-{ref.label}.md").write_text(contrast(ref, run), encoding="utf-8")


def compose(llm: LLM, system: str, task: Task, harness: Harness, refs: Sequence[ExecutionRecord],
            candidates: Sequence[Candidate], probes: Mapping[str, ExecutionRecord], session: Path, *,
            library: Path, max_turns: int, label: str) -> Candidate:
    """One composer session (system: from composer_prompt) in the folder
    `session`. Its evidence is the editors', plus each candidate with its probe
    run (write_candidate) under candidates/<label>/."""
    context = session / "context"
    build_context(context, task, harness, refs, library)
    for c in candidates:
        write_candidate(context / "candidates" / c.label, harness, c, probes[c.label], refs)
    return edit_session(llm, "composer", system, harness, session, max_turns=max_turns, label=label)


def contrastive_step(llm: LLM, sandbox: Sandbox, task: Task, harness: Harness, refs: Sequence[ExecutionRecord],
                     folder: Path, *, k: int, library: Path, prompts_dir: Path, limits: RolloutLimits,
                     max_turns: int) -> StepRecord:
    """Φ (Eq. 1), k wide (Eq. 2): from the reference runs of `harness`, propose
    k INV and k DOM candidates, probe each, compose k successors H′ (labels
    composed1..k) from the whole pool, and run each. Editors and composers see
    a copy of `library`, the improvement harness's library (Lesson 8). Every
    session and run is kept under `folder`."""
    files = write_task(task, folder / "task")
    with ThreadPoolExecutor(len(SCOPES) * k) as pool:
        jobs = [pool.submit(propose, llm, editor_prompt(prompts_dir, scope, i, k), task, harness, refs,
                            folder / "editors" / f"{scope}{i}", library=library, max_turns=max_turns,
                            label=f"{scope}{i}")
                for scope in SCOPES for i in range(1, k + 1)]
        candidates = tuple(job.result() for job in jobs)
    probes = probe(llm, sandbox, {c.label: c.harness for c in candidates}, task.prompt, files,
                   folder / "probes", limits)
    with ThreadPoolExecutor(k) as pool:
        jobs = [pool.submit(compose, llm, composer_prompt(prompts_dir, j, k), task, harness, refs, candidates,
                            probes, folder / "composers" / f"composed{j}", library=library, max_turns=max_turns,
                            label=f"composed{j}")
                for j in range(1, k + 1)]
        composed = tuple(job.result() for job in jobs)
    successors = probe(llm, sandbox, {c.label: c.harness for c in composed}, task.prompt, files,
                       folder / "successors", limits)
    return StepRecord(tuple(refs), candidates, probes, composed, successors)
