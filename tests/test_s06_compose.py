"""Lesson 6 tests. Each docstring names the real failure the test guards against."""

import re
from pathlib import Path

import config
from config import RolloutLimits
from steps.s00_llm import LLM
from steps.s01_harness import Harness, diff, load_harness
from steps.s02_executor import ExecutionRecord, Step, ToolCall
from steps.s03_tasks import Task
from steps.s04_propose import Candidate, editor_prompt
from steps.s06_compose import compose, composer_prompt, contrastive_step
from tests.scripted_api import ScriptedAPI, reply, text, tool_use

H0, _ = load_harness(config.BASE_HARNESS_DIR)
EDITOR = config.LLM_SETTINGS.roles["editor"].model
EXECUTOR = config.LLM_SETTINGS.roles["executor"].model
LIMITS = RolloutLimits(max_turns=3, subagent_max_turns=1, tool_timeout_s=3)
TASK = Task("demo", "Write report.md from input/orders.csv.", {"input/orders.csv": b"id,amount\n1,5\n"})
RULE = "Before finishing, reopen the report and check every total.\n"


def record(label: str, harness: Harness, deliverable: dict[str, str]) -> ExecutionRecord:
    wrote = ToolCall("write_file", {"path": "report.md"}, "Wrote", False)
    return ExecutionRecord(label, harness, (Step(1, "Writing.", (wrote,)),), deliverable, "Done.", "end_turn", (),
                           Path("unused"))


REF = record("h0", H0, {"report.md": "total 5\n"})
INV = Candidate("inv1", Harness({**H0.files, "guardrails.md": RULE}), "guardrails.md: h0 never reopened its report",
                "", (), ())
DOM = Candidate("dom1", H0, "added a recheck skill", "still invalid after one retry: no trigger line", (), ())


def test_the_composer_sees_every_candidate_with_its_run_and_copies_exactly(tmp_path):
    """Guards: the composer judging a candidate blind (without its diff, its
    editor's reasons, its run, or how that run compares with the reference),
    so it can't check the moment an editor cites; a candidate that fell
    back read as if its notes described its tree, a component taken over by
    anything but an exact copy into the composer's own harness, and the
    composer's spend counted as an editor's."""
    api = ScriptedAPI([
        reply(tool_use("c1", "copy_file", {"source": "context/candidates/inv1/harness/guardrails.md",
                                            "target": "context/harness/guardrails.md"}),
              tool_use("c2", "copy_file", {"source": "context/candidates/inv1/harness/guardrails.md",
                                            "target": "context/rollouts/h0/trajectory.md"}),
              model=EDITOR, stop_reason="tool_use"),
        reply(text("<notes>kept -> inv1 guardrails.md -> h0 never reopened its report</notes>"), model=EDITOR)])
    llm = LLM(api.client(), config.LLM_SETTINGS)
    probes = {"inv1": record("inv1", INV.harness, {"report.md": "total 6\n"}), "dom1": record("dom1", H0, {})}
    composed = compose(llm, "mission", TASK, H0, [REF], [INV, DOM], probes, tmp_path, max_turns=3)

    candidates = tmp_path / "context" / "candidates"
    assert (candidates / "inv1" / "diff.patch").read_text() == diff(H0, INV.harness)
    assert (candidates / "inv1" / "rollout" / "deliverable" / "report.md").read_text() == "total 6\n"
    assert "| deliverable | report.md (8 chars) | NOTHING |" in (candidates / "dom1" / "contrast-h0.md").read_text()
    assert (candidates / "inv1" / "notes.md").read_text() == INV.notes
    assert "fell back" in (candidates / "dom1" / "notes.md").read_text()
    assert [r["is_error"] for r in api.requests[1].body["messages"][-1]["content"]] == [False, True]
    assert composed.harness == INV.harness and not composed.fallback
    assert set(llm.meter.snapshot()) == {"composer"}


def test_a_contrastive_step_runs_the_harness_it_composed(sandbox, tmp_path):
    """Guards: e′ coming from the wrong harness (the current one, or a
    candidate, instead of H′), so it says nothing about what was composed;
    and a candidate left unprobed, so the composer would judge it without a
    run."""
    keep, ran = reply(text("<notes>KEEP_BASE</notes>"), model=EDITOR), reply(text("done"), model=EXECUTOR)
    api = ScriptedAPI([
        keep, keep,   # the INV and DOM editors, side by side
        ran, ran,     # their probes, side by side
        reply(tool_use("w", "write_file", {"path": "context/harness/guardrails.md", "content": RULE}),
              model=EDITOR, stop_reason="tool_use"),
        reply(text("<notes>revised -> guardrails.md -> h0 never reopened its report</notes>"), model=EDITOR),
        ran])         # the successor
    xi = contrastive_step(LLM(api.client(), config.LLM_SETTINGS), sandbox, TASK, H0, [REF], tmp_path,
                          prompts_dir=config.PROMPTS_DIR, limits=LIMITS, max_turns=3)

    assert set(xi.probes) == {c.label for c in xi.candidates} == {"inv1", "dom1"}
    assert xi.composed.harness.files["guardrails.md"] == RULE
    assert xi.successor.harness == xi.composed.harness and RULE.strip() in api.requests[-1].body["system"]


def test_the_composer_is_bound_by_the_editors_rules():
    """Guards: the composer's prompt missing the rules that bound the editors
    (Prompt 3: "you are the last gate, and merging an edit launders it"), and
    a placeholder reaching the model unfilled."""
    rules = (config.PROMPTS_DIR / "harness_rules.md").read_text().strip()
    composer = composer_prompt(config.PROMPTS_DIR, 2, 3)
    assert rules in composer and rules in editor_prompt(config.PROMPTS_DIR, "inv", 1, 1)
    assert "composer 2 of 3" in composer
    assert not re.search(r"\{\w*\}", composer)
