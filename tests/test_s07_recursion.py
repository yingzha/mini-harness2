"""Lesson 7 tests. Each docstring names the real failure the test guards against."""

import random
import re
from pathlib import Path

import config
from config import RolloutLimits
from steps.s00_llm import LLM
from steps.s01_harness import Harness, load_harness
from steps.s02_executor import ExecutionRecord
from steps.s03_tasks import Task
from steps.s07_recursion import anonymize, parallel_recursion, select
from tests.routes import chooses, routed
from tests.scripted_api import ScriptedAPI, reply, text

H0, _ = load_harness(config.BASE_HARNESS_DIR)
EDITOR = config.LLM_SETTINGS.roles["editor"].model
EXECUTOR = config.LLM_SETTINGS.roles["executor"].model
LIMITS = RolloutLimits(max_turns=3, subagent_max_turns=1, tool_timeout_s=3)
TASK = Task("demo", "Write report.md from input/orders.csv.", {"input/orders.csv": b"id,amount\n1,5\n"})


def run(label: str, harness: Harness, deliverable: dict[str, str]) -> ExecutionRecord:
    return ExecutionRecord(label, harness, (), deliverable, "Done.", "end_turn", (), Path("unused"))


OUTPUTS = {"base1": run("base1", H0, {"report.md": "total 5\n"}),
           "composed1": run("composed1", Harness({**H0.files, "guardrails.md": "Rule 1.\n"}), {"report.md": "total 6\n"}),
           "composed2": run("composed2", Harness({**H0.files, "guardrails.md": "Rule 2.\n"}), {})}


def test_the_selector_sees_only_artifacts_and_its_choice_maps_back(tmp_path):
    """Guards: the selector learning which harness made an output (a label,
    harness or trajectory in its folder), so it can defer to adapted ones;
    ids in a fixed order (the base runs always first); a choice mapped back
    to the wrong run, so H★ is not the harness whose output is delivered;
    and a selector able to change the outputs it judges."""
    api = ScriptedAPI([chooses("c2")])
    selection = select(LLM(api.client(), config.LLM_SETTINGS), "mission", TASK, OUTPUTS, tmp_path, max_turns=3,
                       rng=random.Random(0))

    shown = {p.relative_to(tmp_path).as_posix(): p.read_text() for p in tmp_path.rglob("*") if p.is_file()}
    assert set(shown) == {"context/task.md", "context/files/input/orders.csv",
                          "context/candidates/c1.md", "context/candidates/c2.md", "context/candidates/c3.md"}
    assert not any(label in body for body in shown.values() for label in OUTPUTS)
    assert {t["name"] for t in api.requests[0].body["tools"]} == {"list_files", "read_file"}
    chosen = OUTPUTS[selection.chosen].deliverable.get("report.md", "no files")
    assert selection.chosen == selection.ids["c2"] and chosen in shown["context/candidates/c2.md"]
    assert (selection.why, selection.fallback) == ("c2 matches the request.", "")
    assert len({tuple(anonymize(list(OUTPUTS), random.Random(seed)).values()) for seed in range(10)}) > 1


def test_an_unreadable_choice_goes_back_once_then_falls_back_to_the_first(tmp_path):
    """Guards: a garbled final reply crashing the task at its last stage, or
    adopting an arbitrary run; and a selector sent back again and again."""
    api = ScriptedAPI([reply(text("I would submit the second one."), model=EDITOR), chooses("c9")])
    selection = select(LLM(api.client(), config.LLM_SETTINGS), "mission", TASK, OUTPUTS, tmp_path, max_turns=3,
                       rng=random.Random(0))

    assert "choice block" in api.requests[1].body["messages"][-1]["content"] and len(api.requests) == 2
    assert selection.chosen == "base1" and "no readable choice" in selection.fallback


def test_parallel_recursion_adopts_the_harness_whose_output_is_delivered(sandbox, tmp_path):
    """Guards: H★ not being the harness whose output is delivered; a pool
    without the base runs (picking an unmodified harness's output is valid
    and expected) or without some composed harness's run; and a step that is
    not k wide (one candidate per lane, or every editor told it is 1 of 1);
    and the selector told "which of {n}" with the count left unfilled."""
    pool = ["base1", "base2", "composed1", "composed2"]   # base runs, then each composer's run
    want = next(id_ for id_, label in anonymize(pool, random.Random(0)).items() if label == "composed2")
    api = ScriptedAPI(routed(selector_picks=want))
    result = parallel_recursion(LLM(api.client(), config.LLM_SETTINGS), sandbox, TASK, H0, tmp_path, k=2,
                                library=tmp_path / "no-library",
                                prompts_dir=config.PROMPTS_DIR, limits=LIMITS, max_turns=3, rng=random.Random(0))

    assert sorted(c.label for c in result.step.candidates) == ["dom1", "dom2", "inv1", "inv2"]
    assert any("candidate 2 of 2" in r.body["system"] for r in api.requests)
    assert sorted(result.selection.ids.values()) == pool
    [selector] = [r.body["system"] for r in api.requests if "candidate answers should be delivered" in r.body["system"]]
    assert "choosing which of 4 candidate answers" in selector and not re.search(r"\{\w*\}", selector)
    assert result.chosen == "composed2" and result.adopted.files["guardrails.md"] == "Rule 2.\n"


def test_at_k_1_the_composed_harness_is_adopted_without_selection(sandbox, tmp_path):
    """Guards: a selection session at k = 1, where the paper bypasses it, and
    the successor not being adopted there."""
    api = ScriptedAPI(routed())
    result = parallel_recursion(LLM(api.client(), config.LLM_SETTINGS), sandbox, TASK, H0, tmp_path, k=1,
                                library=tmp_path / "no-library",
                                prompts_dir=config.PROMPTS_DIR, limits=LIMITS, max_turns=3, rng=random.Random(0))

    assert result.selection is None and result.chosen == "composed1"
    assert result.adopted.files["guardrails.md"] == "Rule 1.\n"
    assert not any("candidate answers should be delivered" in r.body["system"] for r in api.requests)
