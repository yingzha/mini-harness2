"""Lesson 4 tests. Each docstring names the real failure the test guards against."""

import re
from pathlib import Path

import config
from steps.s00_llm import LLM
from steps.s01_harness import load_harness
from steps.s02_executor import ExecutionRecord, Step, ToolCall
from steps.s03_tasks import Task
from steps.s04_propose import SCOPES, editor_prompt, propose
from tests.scripted_api import ScriptedAPI, reply, text, tool_use

H0, _ = load_harness(config.BASE_HARNESS_DIR)
EDITOR = config.LLM_SETTINGS.roles["editor"].model
TASK = Task("demo", "Write out/report.md from input/orders.csv.", {"input/orders.csv": b"id,amount\n1,5\n"})
REPORT = "# Orders\n\n1 order.\n"
REF = ExecutionRecord(
    "h0", H0,
    (Step(1, "Writing the report.", (ToolCall("write_file", {"path": "out/report.md", "content": REPORT},
                                              "Wrote 20 characters to out/report.md", False),)),),
    {"out/report.md": REPORT}, "Done.", "end_turn", (), Path("unused"))
RULE = "Before finishing, reopen the report and check every total.\n"
SKILL = "---\ndescription: re-check a finished report\n---\nReopen the report; recompute each total.\n"


def scripted(*replies: dict) -> tuple[LLM, ScriptedAPI]:
    api = ScriptedAPI(list(replies))
    return LLM(api.client(), config.LLM_SETTINGS), api


def calls(*blocks: dict) -> dict:
    return reply(*blocks, model=EDITOR, stop_reason="tool_use")


def done(t: str) -> dict:
    return reply(text(t), model=EDITOR)


def write(path: str, content: str, id: str = "w") -> dict:
    return tool_use(id, "write_file", {"path": path, "content": content})


def test_an_editor_sees_the_evidence_and_edits_only_its_copy(tmp_path):
    """Guards: an editor not getting what the run produced, so it can't see
    where the output went wrong; and an editor "fixing" the task's files or
    the evidence instead of the harness: an edit that would vanish without a
    word, since only harness/ becomes the candidate; and a file the runtime
    never loads (a skill helper outside its scripts/ folder) vanishing without
    a trace."""
    llm, api = scripted(
        calls(tool_use("r", "read_file", {"path": "context/rollouts/h0/deliverable/out/report.md"}),
              write("context/files/input/orders.csv", "id,amount\n1,6\n", "w1"),
              tool_use("d", "delete_file", {"path": "context/rollouts/h0/trajectory.md"}),
              write("context/harness/guardrails.md", RULE, "w2"),
              write("context/harness/skills/recheck/helper.py", "print(1)\n", "w3")),
        done("<notes>guardrails.md: h0 never reopened its report (turn 1)</notes>"))
    c = propose(llm, "mission", TASK, H0, [REF], tmp_path, library=tmp_path / "no-library", max_turns=4, label="inv1")

    results = api.requests[1].body["messages"][-1]["content"]
    assert results[0]["content"] == REPORT
    assert [r["is_error"] for r in results] == [False, True, True, False, False]
    assert (tmp_path / "context" / "files" / "input" / "orders.csv").read_bytes() == TASK.files["input/orders.csv"]
    assert (tmp_path / "context" / "rollouts" / "h0" / "trajectory.md").exists()
    assert c.harness.files == {**H0.files, "guardrails.md": RULE}
    assert c.dropped == ("skills/recheck/helper.py",)
    assert (c.notes, c.fallback) == ("guardrails.md: h0 never reopened its report (turn 1)", "")


def test_an_invalid_tree_goes_back_to_its_editor_once(tmp_path):
    """Guards: a fixable slip (here a skill without its trigger line) throwing
    away a whole proposal without the one retry §D.2 gives, and the notes
    written before the fix being kept instead of the final ones."""
    llm, api = scripted(
        calls(write("context/harness/skills/recheck/SKILL.md", SKILL)),
        done("<notes>added a skill</notes>"),
        calls(write("context/harness/guardrails.md", "Before finishing, load the `recheck` skill.\n")),
        done("<notes>added the recheck skill and its trigger line</notes>"))
    c = propose(llm, "mission", TASK, H0, [REF], tmp_path, library=tmp_path / "no-library", max_turns=6, label="inv1")

    assert "no trigger line" in api.requests[2].body["messages"][-1]["content"]
    assert "skills/recheck/SKILL.md" in c.harness.files and c.fallback == ""
    assert c.notes == "added the recheck skill and its trigger line"


def test_a_proposal_still_invalid_or_unfinished_falls_back_to_the_start(tmp_path):
    """Guards: an invalid tree reaching the probe, where it would crash or waste
    a rollout; an editor sent back again and again; and a session cut off at
    its turn cap passing a half-made edit off as a proposal."""
    llm, _ = scripted(calls(write("context/harness/skills/recheck/SKILL.md", SKILL)),
                      done("<notes>a</notes>"), done("<notes>b</notes>"))
    invalid = propose(llm, "mission", TASK, H0, [REF], tmp_path / "a", library=tmp_path / "no-library", max_turns=6, label="inv1")
    llm, _ = scripted(calls(write("context/harness/guardrails.md", RULE)))
    unfinished = propose(llm, "mission", TASK, H0, [REF], tmp_path / "b", library=tmp_path / "no-library", max_turns=1, label="inv1")

    assert invalid.harness == H0 and "no trigger line" in invalid.fallback
    assert unfinished.harness == H0 and "max_turns" in unfinished.fallback


def test_each_editor_gets_its_own_dimension():
    """Guards: both editors getting the same mission, so the two candidates
    aren't contrastive at all; and a placeholder like "candidate {i} of {k}"
    reaching the model unfilled."""
    inv, dom = (editor_prompt(config.PROMPTS_DIR, scope, 2, 3) for scope in SCOPES)
    assert "YOUR DIMENSION: INV" in inv and "YOUR DIMENSION: INV" not in dom
    assert "YOUR DIMENSION: DOM" in dom and "YOUR DIMENSION: DOM" not in inv
    assert "candidate 2 of 3" in inv and "candidate 2 of 3" in dom
    assert not re.search(r"\{\w*\}", inv + dom)
