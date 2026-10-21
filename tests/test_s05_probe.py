"""Lesson 5 tests. Each docstring names the real failure the test guards against."""

from pathlib import Path

import config
from config import RolloutLimits
from steps.s00_llm import LLM
from steps.s01_harness import Harness, load_harness
from steps.s02_executor import ExecutionRecord, Step, ToolCall
from steps.s05_probe import contrast, probe
from tests.scripted_api import ScriptedAPI, reply, text

H0, _ = load_harness(config.BASE_HARNESS_DIR)
EXECUTOR = config.LLM_SETTINGS.roles["executor"].model
LIMITS = RolloutLimits(max_turns=3, subagent_max_turns=1, tool_timeout_s=3)


def record(label: str, calls: list[ToolCall], deliverable: dict[str, str], nudge: str | None = None) -> ExecutionRecord:
    return ExecutionRecord(label, H0, (Step(1, "", tuple(calls), nudge),), deliverable, "", "end_turn", (),
                           Path("unused"))


def test_probes_run_the_same_task_under_the_same_conditions(sandbox, tmp_path):
    """Guards: a candidate credited with another's run (labels and harnesses
    mixed up), and probes run under conditions that differ (model, task or
    starting files), so a contrast would measure the setup, not the edit."""
    harnesses = {"h0": H0, "inv1": Harness({**H0.files, "guardrails.md": "Reopen the report before finishing.\n"})}
    files = tmp_path / "files"
    (files / "input").mkdir(parents=True)
    (files / "input" / "orders.csv").write_text("id,amount\n1,5\n")
    api = ScriptedAPI([reply(text("done"), model=EXECUTOR) for _ in harnesses])
    records = probe(LLM(api.client(), config.LLM_SETTINGS), sandbox, harnesses, "Write report.md.",
                    files, tmp_path / "probes", LIMITS)

    assert {label: (r.label, r.harness) for label, r in records.items()} == \
        {label: (label, h) for label, h in harnesses.items()}
    assert sorted(r.body["system"] for r in api.requests) == sorted(h.always_on_text() for h in harnesses.values())
    assert all(r.body["model"] == EXECUTOR and r.body["messages"][0]["content"] == "Write report.md."
               for r in api.requests)
    assert all((r.workspace / "input" / "orders.csv").read_text() == "id,amount\n1,5\n" for r in records.values())
    assert len({r.workspace for r in records.values()}) == len(harnesses)


def test_a_contrast_shows_what_changed_and_what_was_used():
    """Guards: a contrast hiding whether an edit was even used (a skill never
    loaded looks like a skill that didn't help; a script run as ./scripts/x.py
    or a plugin that kept the agent working must not look unused; the agent's
    own scratch script is not a harness script); a changed deliverable, or a
    file only one run produced, going unseen; and a run that produced nothing
    not standing out, when the composer must treat its edits as unsafe
    (Prompt 3)."""
    ref = record("h0", [ToolCall("read_file", {"path": "input/orders.csv"}, "id,amount", False),
                        ToolCall("write_file", {"path": "report.md"}, "Wrote", False)],
                 {"report.md": "total 5\n"}, nudge="Your reply hit the output limit. Continue where you stopped.")
    other = record("inv1", [
        ToolCall("load_skill", {"name": "recheck"}, "Reopen the report.", False),
        ToolCall("run_python", {"script": "./skills/recheck/scripts/check.py"}, "exit code 1", True,
                 notes=("[plugin verify] report.md has no header",)),
        ToolCall("run_python", {"script": "scratch.py"}, "exit code 0", False),
        ToolCall("write_file", {"path": "report.md"}, "Wrote", False),
    ], {"report.md": "total 6\n", "notes.txt": "checked\n"}, nudge="[plugin verify] Reopen report.md first.")
    text = contrast(ref, other)

    assert "| tool errors | 0 | 1 |" in text
    assert ("| harness components used | none | "
            "plugin note, plugin nudge, script skills/recheck/scripts/check.py, skill recheck |") in text
    assert "-total 5\n+total 6" in text and "+++ b/notes.txt" in text
    assert "| deliverable | report.md (8 chars) | NOTHING |" in contrast(ref, record("dom1", [], {}))
