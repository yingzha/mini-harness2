"""Lesson 8 tests. Each docstring names the real failure the test guards against."""

from pathlib import Path

import pytest

import config
from steps.s00_llm import LLM
from steps.s01_harness import Harness, load_harness
from steps.s02_executor import ExecutionRecord, Step, ToolCall
from steps.s03_tasks import Task
from steps.s04_propose import Candidate, propose
from steps.s06_compose import StepRecord
from steps.s07_recursion import Recursion, Selection
from steps.s08_library import Reflection, reflect, update_library
from tests.scripted_api import ScriptedAPI, reply, text, tool_use

H0, _ = load_harness(config.BASE_HARNESS_DIR)
EDITOR = config.LLM_SETTINGS.roles["editor"].model
TASK = Task("demo", "Write report.md from input/orders.csv.", {"input/orders.csv": b"id,amount\n1,5\n"})
RULE = "Before finishing, reopen the report and check every total.\n"


def run(label: str, harness: Harness, report: str) -> ExecutionRecord:
    wrote = ToolCall("write_file", {"path": "report.md"}, "Wrote", False)
    return ExecutionRecord(label, harness, (Step(1, "Writing.", (wrote,)),), {"report.md": report}, "Done.",
                           "end_turn", (), Path("unused"))


INV = Candidate("inv1", Harness({**H0.files, "guardrails.md": RULE}), "guardrails.md: h0 never reopened its report",
                "", (), ())
DOM = Candidate("dom1", H0, "added a recheck skill", "still invalid after one retry: no trigger line", (), ())
COMPOSED = Candidate("composed1", INV.harness, "kept -> inv1 guardrails.md -> base1 never reopened its report",
                     "", (), ())
STEP = StepRecord(refs=(run("base1", H0, "total 5\n"), run("base2", H0, "total 5\n")), candidates=(INV, DOM),
                  probes={"inv1": run("inv1", INV.harness, "total 6\n"), "dom1": run("dom1", H0, "total 5\n")},
                  composed=(COMPOSED,), successors={"composed1": run("composed1", INV.harness, "total 6\n")})
RECURSION = Recursion(STEP, "composed1", INV.harness,
                      Selection("composed1", {"c1": "base2", "c2": "composed1", "c3": "base1"},
                                "c2 rechecked its totals.", "", ()))
ROWS = ("component: guardrails.md\ncandidates: inv1, composed1\nchange: reopen the report before finishing\n"
        "observed: inv1 reread report.md at turn 2; base1 never did\nverdict: confounded")
LESSON = ("cue: a report whose totals are computed, then typed into prose\nlesson: guardrails.md: reopen the file "
          "and recompute each total before finishing\nevidence: the guardrails.md row\nconfidence: low, one run")


def test_the_reflector_reads_every_candidate_and_what_was_submitted(tmp_path):
    """Guards: the reflector seeing only the adopted harness (Prompt 6: "the
    adopted candidate is not the only evidence") or not knowing which output
    was submitted; a reply without its edit rows taken as is, instead of sent
    back once; NO_ENTRY recorded as a lesson; and a reflector able to write."""
    api = ScriptedAPI([reply(text(f"<edits>\n{ROWS}\n</edits>\n\n<experience>\n{LESSON}\n</experience>"),
                             model=EDITOR)])
    llm = LLM(api.client(), config.LLM_SETTINGS)
    reflection = reflect(llm, "mission", TASK, H0, RECURSION, tmp_path / "a", max_turns=3)

    context = tmp_path / "a" / "context"
    assert "fell back" in (context / "candidates" / "dom1" / "notes.md").read_text()   # rejected, still evidence
    assert (context / "composed" / "composed1" / "notes.md").read_text() == COMPOSED.notes
    assert (context / "rollouts" / "base2" / "trajectory.md").exists()
    submitted = (context / "selection.md").read_text()
    assert "Submitted: composed1" in submitted and "c2 rechecked its totals." in submitted
    assert {t["name"] for t in api.requests[0].body["tools"]} == {"list_files", "read_file"}
    assert (reflection.edits, reflection.experience) == (ROWS, LESSON)
    assert set(llm.meter.snapshot()) == {"reflector"}

    api = ScriptedAPI([reply(text("The record is thin."), model=EDITOR),
                       reply(text(f"<edits>\n{ROWS}\n</edits>\n\nNO_ENTRY"), model=EDITOR)])
    reflection = reflect(LLM(api.client(), config.LLM_SETTINGS), "mission", TASK, H0, RECURSION, tmp_path / "b",
                         max_turns=3)
    assert "<edits>" in api.requests[1].body["messages"][-1]["content"]
    assert (reflection.edits, reflection.experience) == (ROWS, "")


def test_the_library_keeps_the_adopted_tree_and_its_lesson(tmp_path):
    """Guards: the library keeping a summary instead of the executable tree
    (§D.2); a task's entry overwritten by a later run; an entry for a task that
    adopted H0 and taught nothing; and a lesson missing from the index, where
    later editors look first."""
    library, reflection = tmp_path / "library", Reflection(ROWS, LESSON, ())
    assert update_library(library, "ticket-daily", H0, INV.harness, reflection)

    entry = library / "entries" / "ticket-daily"
    assert load_harness(entry / "harness")[0] == INV.harness
    assert LESSON in (entry / "EXPERIENCE.md").read_text() and ROWS in (entry / "EXPERIENCE.md").read_text()
    assert (library / "index.md").read_text() == \
        "- entries/ticket-daily/: changed guardrails.md. Cue: a report whose totals are computed, then typed into prose\n"
    with pytest.raises(FileExistsError):
        update_library(library, "ticket-daily", H0, INV.harness, reflection)
    assert not update_library(library, "quiet-task", H0, H0, Reflection(ROWS, "", ()))
    assert not (library / "entries" / "quiet-task").exists()


def test_editors_read_the_library_but_cannot_change_it(tmp_path):
    """Guards: later tasks' editors never seeing what earlier ones learned (then
    harnessing-level recursion does nothing), and a session able to change the
    library every later task relies on."""
    library = tmp_path / "library"
    update_library(library, "earlier-task", H0, INV.harness, Reflection(ROWS, LESSON, ()))
    api = ScriptedAPI([
        reply(tool_use("r", "read_file", {"path": "context/library/index.md"}),
              tool_use("w", "write_file", {"path": "context/library/index.md", "content": "erased"}),
              model=EDITOR, stop_reason="tool_use"),
        reply(text("<notes>KEEP_BASE</notes>"), model=EDITOR)])
    propose(LLM(api.client(), config.LLM_SETTINGS), "mission", TASK, H0, [STEP.refs[0]], tmp_path / "session",
            library=library, max_turns=3, label="inv1")

    results = api.requests[1].body["messages"][-1]["content"]
    assert "entries/earlier-task/" in results[0]["content"] and results[1]["is_error"]
    assert "earlier-task" in (library / "index.md").read_text()
