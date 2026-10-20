"""Lesson 2 tests. Each docstring names the real failure the test guards against."""

import time
from pathlib import Path

import pytest

import config
from config import RolloutLimits
from steps.s00_llm import LLM
from steps.s01_harness import Harness, load_harness
from steps.s02_executor import (MAX_NUDGES, MAX_OUTPUT_CHARS, execute, file_tools, prepare_workspace,
                                render_record, run_agent_loop, run_python_tool)
from tests.scripted_api import ScriptedAPI, reply, text, thinking, tool_use

H0, _ = load_harness(config.BASE_HARNESS_DIR)
EXECUTOR = config.LLM_SETTINGS.roles["executor"].model
LIMITS = RolloutLimits(max_turns=6, subagent_max_turns=3, tool_timeout_s=3)


def scripted(*replies: dict) -> tuple[LLM, ScriptedAPI]:
    api = ScriptedAPI(list(replies))
    return LLM(api.client(), config.LLM_SETTINGS), api


def calls(*blocks: dict, stop_reason: str = "tool_use") -> dict:
    return reply(*blocks, model=EXECUTOR, stop_reason=stop_reason)


def done(t: str = "done") -> dict:
    return reply(text(t), model=EXECUTOR)


def by_name(tools):
    return {t.name: t for t in tools}


def tool_results(api: ScriptedAPI, request: int) -> list[dict]:
    """The tool results sent in a given request (they are its last message)."""
    return api.requests[request].body["messages"][-1]["content"]


@pytest.fixture
def source(tmp_path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "data.csv").write_text("id,amount\n1,$5\n")
    return src


# --- Sandboxing the code and files the model touches ----------------------------

def test_file_tools_cannot_reach_outside_their_root(tmp_path):
    """Guards: the agent reading the API key. Rollout workspaces live under
    /app/runs, so `../../.env` (or a symlink) would otherwise reach /app/.env.
    Also: an editor (Lesson 4) writing outside the harness it is editing."""
    app = tmp_path / "app"
    ws = app / "runs" / "ws"
    ws.mkdir(parents=True)
    (app / ".env").write_text("ANTHROPIC_API_KEY=sk-secret")
    (ws / "link.txt").symlink_to(app / ".env")
    tools = by_name(file_tools(ws, ws))
    for path in ["../../.env", str(app / ".env"), "link.txt"]:
        with pytest.raises(ValueError):
            tools["read_file"].run({"path": path})
    with pytest.raises(ValueError):
        tools["list_files"].run({"path": ".."})
    with pytest.raises(ValueError):
        tools["write_file"].run({"path": "../escape.txt", "content": "x"})

    context = tmp_path / "context"
    (context / "harness").mkdir(parents=True)
    editor = by_name(file_tools(context, context / "harness"))
    editor["write_file"].run({"path": "harness/guardrails.md", "content": "ok"})
    with pytest.raises(ValueError):
        editor["write_file"].run({"path": "task.md", "content": "rewritten evidence"})


def test_model_code_does_not_inherit_the_api_key(tmp_path, monkeypatch):
    """Guards: code the model writes printing (or sending) the API key, which
    the container's environment holds for the SDK."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    result = run_python_tool(tmp_path, 5).run({"code": "import os; print(dict(os.environ))"})
    assert not result.is_error
    assert "sk-secret" not in result.output and "ANTHROPIC" not in result.output


def test_runaway_code_is_stopped_at_the_timeout(tmp_path):
    """Guards: one infinite loop hanging the whole rollout (and the pipeline)."""
    start = time.monotonic()
    result = run_python_tool(tmp_path, 1).run({"code": "while True: pass"})
    assert result.is_error and "timed out after 1s" in result.output
    assert time.monotonic() - start < 10


def test_long_output_is_clipped_keeping_head_and_tail(tmp_path):
    """Guards: printing a whole data file flooding the context window, and
    clipping that drops the end, where a traceback's actual error sits."""
    result = run_python_tool(tmp_path, 5).run({"code": "print('HEAD' + 'x' * 200_000 + 'TAIL')"})
    assert "HEAD" in result.output and "TAIL" in result.output and "characters cut" in result.output
    assert len(result.output) < MAX_OUTPUT_CHARS + 500


# --- The agent loop --------------------------------------------------------------

def test_loop_returns_responses_unchanged_and_all_results_in_one_message(tmp_path):
    """Guards: a 400 from the API when a thinking block comes back altered, and
    tool results split across messages (the API expects every result for a
    turn in the next user message)."""
    llm, api = scripted(
        calls(thinking("sig-1"), text("Write, then read back."),
              tool_use("t1", "write_file", {"path": "a.txt", "content": "hi"}),
              tool_use("t2", "read_file", {"path": "a.txt"})),
        done())
    result = run_agent_loop(llm, "executor", "sys", "task", file_tools(tmp_path, tmp_path), max_turns=5)

    sent = api.requests[1].body["messages"]
    assert len(sent) == 3  # task, the assistant turn, ONE message with both results
    assert sent[1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig-1"}
    assert [b["type"] for b in sent[1]["content"]] == ["thinking", "text", "tool_use", "tool_use"]
    assert [(r["tool_use_id"], r["is_error"], r["content"]) for r in sent[2]["content"]] == [
        ("t1", False, "Wrote 2 characters to a.txt"), ("t2", False, "hi")]
    assert result.stop_reason == "end_turn"


def test_tool_failures_become_error_results_and_the_loop_goes_on(tmp_path):
    """Guards: one bad tool call (unknown tool, missing file) ending the rollout
    instead of letting the agent recover."""
    llm, api = scripted(
        calls(tool_use("t1", "no_such_tool", {}), tool_use("t2", "read_file", {"path": "missing.txt"})),
        done())
    result = run_agent_loop(llm, "executor", "sys", "task", file_tools(tmp_path, tmp_path), max_turns=5)
    unknown, missing = tool_results(api, 1)
    assert unknown["is_error"] and "Unknown tool 'no_such_tool'" in unknown["content"]
    assert missing["is_error"] and "FileNotFoundError" in missing["content"]
    assert result.stop_reason == "end_turn"


def test_loop_stops_at_the_turn_cap(tmp_path):
    """Guards: an agent that never stops calling tools running up cost forever."""
    llm, api = scripted(*[calls(tool_use(f"t{i}", "list_files", {})) for i in range(3)])
    result = run_agent_loop(llm, "executor", "sys", "task", file_tools(tmp_path, tmp_path), max_turns=3)
    assert result.stop_reason == "max_turns"
    assert len(api.requests) == 3 and len(result.steps) == 3


def test_a_cut_off_tool_call_is_answered_but_not_run(tmp_path):
    """Guards: a reply cut off at max_tokens mid tool call. Leaving the call
    unanswered makes the next request fail; running it would act on input
    that may be incomplete."""
    llm, api = scripted(
        calls(tool_use("t1", "write_file", {"path": "big.txt", "content": "partial"}), stop_reason="max_tokens"),
        done())
    run_agent_loop(llm, "executor", "sys", "task", file_tools(tmp_path, tmp_path), max_turns=5)
    [answer] = tool_results(api, 1)
    assert answer["tool_use_id"] == "t1" and answer["is_error"]
    assert not (tmp_path / "big.txt").exists()


# --- Plugins (C8) ------------------------------------------------------------------

WATCH = (
    "def after_tool(event):\n"
    "    return f\"checked {event['tool']}\"\n"
    "def before_finish(event):\n"
    "    if not event['output_files']:\n"
    "        return 'output/ is empty: write the deliverable before finishing.'\n"
)


def test_plugin_notes_reach_the_model_and_nudges_are_bounded(tmp_path, source):
    """Guards: a plugin's text never reaching the model (so it enforces
    nothing), a before_finish hook trapping the agent forever, and hooks being
    told the wrong output files."""
    harness = Harness({**H0.files, "plugin/watch.py": WATCH})
    llm, api = scripted(calls(tool_use("t1", "list_files", {})), done(), done(), done("finished anyway"))
    record = execute(llm, harness, "task", source, tmp_path / "ws1", LIMITS, label="p1")
    assert "[plugin watch] checked list_files" in tool_results(api, 1)[0]["content"]
    nudges = [s.nudge for s in record.steps if s.nudge]
    assert len(nudges) == MAX_NUDGES and "output/ is empty" in nudges[0]
    assert record.stop_reason == "end_turn" and len(api.requests) == 2 + MAX_NUDGES

    llm, api = scripted(calls(tool_use("t1", "write_file", {"path": "output/x.csv", "content": "a"})), done())
    record = execute(llm, harness, "task", source, tmp_path / "ws2", LIMITS, label="p2")
    assert not any(s.nudge for s in record.steps), "a deliverable exists, so no nudge"


def test_a_broken_plugin_is_recorded_and_the_rollout_continues(tmp_path, source):
    """Guards: an editor's buggy plugin (crash, hang, wrong return type) taking
    down the rollout instead of showing up as evidence against that edit."""
    harness = Harness({
        **H0.files,
        "plugin/crash.py": "def after_tool(event):\n    raise RuntimeError('boom')\n",
        "plugin/slow.py": "import time\ndef before_finish(event):\n    time.sleep(30)\n",
        "plugin/wrong.py": "def after_tool(event):\n    return 42\n",
    })
    llm, _ = scripted(calls(tool_use("t1", "list_files", {})), done())
    record = execute(llm, harness, "task", source, tmp_path / "ws", RolloutLimits(6, 3, 1), label="b")
    errors = " | ".join(record.hook_errors)
    assert record.stop_reason == "end_turn"
    assert "crash.after_tool: RuntimeError: boom" in errors
    assert "slow.before_finish: timed out" in errors
    assert "wrong.after_tool: returned int" in errors


# --- Skills (C6), subagents (C5), the workspace, the record ---------------------

def test_skill_and_subagent_tools_follow_the_harness(tmp_path, source):
    """Guards: offering tools that can only fail (no skills to load), a
    subagent that can delegate again (unbounded recursion), and a subagent
    flooding the caller's context instead of returning only its answer."""
    llm, api = scripted(done())
    execute(llm, H0, "task", source, tmp_path / "ws0", LIMITS, label="h0")
    assert {t["name"] for t in api.requests[0].body["tools"]} == {"list_files", "read_file", "write_file", "run_python"}

    harness = Harness({
        **H0.files,
        "guardrails.md": "When amounts look like $5, load the `money` skill.\n",
        "skills/money/SKILL.md": "---\ndescription: Parse money strings.\n---\nStrip $ and commas.",
        "sub_agents/reader/AGENT.md": "---\ndescription: Summarises a file.\n---\nYou summarise files.",
    })
    llm, api = scripted(
        calls(tool_use("t1", "load_skill", {"name": "money"}),
              tool_use("t2", "run_subagent", {"name": "reader", "prompt": "Summarise source/data.csv"})),
        calls(tool_use("s1", "read_file", {"path": "source/data.csv"})),   # the subagent's session
        done("one row, amount $5"),
        done())                                                             # back in the main loop
    record = execute(llm, harness, "task", source, tmp_path / "ws1", LIMITS, label="h1")

    assert {"load_skill", "run_subagent"} <= {t["name"] for t in api.requests[0].body["tools"]}
    subagent = api.requests[1].body
    assert subagent["system"] == "You summarise files."
    assert "run_subagent" not in {t["name"] for t in subagent["tools"]}
    skill_result, subagent_result = tool_results(api, 3)
    assert skill_result["content"] == "Strip $ and commas."
    assert subagent_result["content"] == "one row, amount $5"
    assert record.steps[0].calls[1].subtrace[0].calls[0].name == "read_file"


def test_workspace_has_inputs_and_scripts_but_not_skill_text_or_plugins(tmp_path, source):
    """Guards: a script the harness names missing at runtime, the agent editing
    its own plugins, and one rollout starting in another's leftovers."""
    harness = Harness({
        **H0.files,
        "guardrails.md": "When parsing, load the `money` skill. Finish with scripts/check.py.\n",
        "scripts/check.py": "print('ok')",
        "skills/money/SKILL.md": "---\ndescription: d\n---\nRun skills/money/scripts/parse.py.",
        "skills/money/scripts/parse.py": "print('parse')",
        "plugin/watch.py": "def after_tool(event):\n    return None\n",
    })
    ws = tmp_path / "ws"
    prepare_workspace(ws, source, harness)
    assert sorted(p.relative_to(ws).as_posix() for p in ws.rglob("*") if p.is_file()) == [
        "scripts/check.py", "skills/money/scripts/parse.py", "source/data.csv"]
    assert (ws / "output").is_dir()

    used = tmp_path / "used"
    used.mkdir()
    (used / "leftover_from_another_rollout.txt").write_text("stale")
    with pytest.raises(FileExistsError):
        prepare_workspace(used, source, harness)


def test_execute_records_the_deliverable_and_stats(tmp_path, source):
    """Guards: the deliverable y missing what the agent wrote, the harness not
    actually reaching the model, and wrong Table 7 statistics."""
    llm, api = scripted(
        calls(tool_use("t1", "write_file", {"path": "output/summary.csv", "content": "id,amount\n1,5\n"}),
              tool_use("t2", "read_file", {"path": "nope.csv"})),
        done("Wrote output/summary.csv"))
    record = execute(llm, H0, "Sum the amounts.", source, tmp_path / "ws", LIMITS, label="base_1")
    assert record.deliverable == {"summary.csv": "id,amount\n1,5\n"}
    assert (record.turns, record.tool_calls, record.tool_errors) == (2, 2, 1)
    assert api.requests[0].body["system"] == H0.always_on_text()
    assert api.requests[0].body["messages"][0]["content"] == "Sum the amounts."
    assert "[ERROR]" in render_record(record)


def test_execute_refuses_an_invalid_harness(tmp_path, source):
    """Guards: paying for a rollout of a harness that breaks the rules, or
    crashing halfway through setup with a confusing error."""
    broken = Harness({**H0.files, "plugin/bad.py": "def after_tool(:\n"})
    llm, api = scripted()
    with pytest.raises(ValueError, match="invalid harness"):
        execute(llm, broken, "task", source, tmp_path / "ws", LIMITS, label="x")
    assert api.requests == []
