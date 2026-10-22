"""Lesson 9 tests. Each docstring names the real failure the test guards against."""

import random

import config
from config import RolloutLimits
from steps.s00_llm import LLM
from steps.s01_harness import load_harness
from steps.s03_tasks import Task
from steps.s09_pipeline import run_stream
from tests.routes import routed
from tests.scripted_api import ScriptedAPI

H0, _ = load_harness(config.BASE_HARNESS_DIR)
LIMITS = RolloutLimits(max_turns=3, subagent_max_turns=1, tool_timeout_s=3)
TASKS = [Task("t1", "Write report.md from input/orders.csv.", {"input/orders.csv": b"id,amount\n1,5\n"}),
         Task("t2", "Write summary.md from input/visits.csv.", {"input/visits.csv": b"day,visits\nMon,3\n"})]


def test_each_task_starts_from_h0_and_learns_only_through_the_library(sandbox, tmp_path):
    """Guards: a task starting from the previous task's adopted harness, when
    the paper restarts every task from H0 and reuses earlier components only
    through Propose; and the library not reaching the next task's editors, so
    harnessing-level recursion does nothing."""
    llm = LLM(ScriptedAPI(routed()).client(), config.LLM_SETTINGS)
    results = list(run_stream(llm, sandbox, TASKS, H0, tmp_path, k=1, prompts_dir=config.PROMPTS_DIR,
                              limits=LIMITS, max_turns=3, rng=random.Random(0)))

    assert [r.task.id for r in results] == ["t1", "t2"]
    assert all(r.recursion.step.refs[0].harness == H0 for r in results)
    first_saw = tmp_path / "t1" / "step" / "editors" / "inv1" / "context" / "library"
    later_saw = tmp_path / "t2" / "step" / "editors" / "inv1" / "context" / "library"
    assert not any(first_saw.rglob("*"))
    assert (later_saw / "entries" / "t1" / "harness" / "guardrails.md").read_text() == "Rule 1.\n"
    assert all(r.added_to_library for r in results)
    assert results[0].recursion.delivered.label == "composed1"
