"""Lesson 2 tests. Each docstring names the real failure the test guards against."""

import json
import subprocess
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

import config
from config import RolloutLimits
from steps.s00_llm import LLM
from steps.s01_harness import Harness, load_harness
from steps.s02_executor import (MAX_NUDGES, MAX_OUTPUT_CHARS, SANDBOX_LABEL, HostFolder, SandboxError, clip,
                                execute, file_tools, host_path, prepare_workspace, render_record, run_agent_loop,
                                run_python_tool)
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
    """A task's files, as write_task lays them out: here, one input under source/."""
    src = tmp_path / "src"
    (src / "source").mkdir(parents=True)
    (src / "source" / "data.csv").write_text("id,amount\n1,$5\n")
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


PROBE = r'''
import json, os
def holds_key(path):
    try:
        return b"sk-test-7f3a" in open(path, "rb").read()
    except OSError:
        return False
others = []
for folder, subfolders, files in os.walk("/"):
    if folder == "/":
        subfolders[:] = [d for d in subfolders if d not in ("proc", "sys", "dev")]
    others += [f for f in files if f.startswith("answers-7f3a")]
status = dict(line.split(":\t", 1) for line in open("/proc/self/status").read().splitlines() if ":\t" in line)
workspace = sorted(os.listdir("."))
open("written.txt", "w").write("ok")
print(json.dumps({
    "key in its env": any("sk-test-7f3a" in v for v in os.environ.values()),
    "key in any process": any(holds_key(f"/proc/{p}/environ") for p in os.listdir("/proc") if p.isdigit()),
    "files outside its workspace": others,
    "routes out of it": [line.split()[0] for line in open("/proc/net/route").read().splitlines()[1:]],
    "runs as root": os.getuid() == 0,
    "capabilities it could gain": status["CapBnd"],
    "can gain privileges": status["NoNewPrivs"] != "1",
    "workspace": workspace,
}))
'''


def sandboxes_for(sandbox, workspace: Path) -> list[str]:
    """IDs of the sandbox containers that exist for this workspace, running or stopped."""
    source = host_path(sandbox.mounts, workspace, writable=False)
    return subprocess.run(["docker", "ps", "--all", "--quiet", "--filter", f"label={SANDBOX_LABEL}={source}"],
                          capture_output=True, text=True, check=True).stdout.split()


def test_model_code_sees_only_its_workspace_and_holds_no_power(sandbox, tmp_path, monkeypatch):
    """Guards: model code reading the API key from its environment or from
    another process (ours holds it for the SDK); reading files outside its
    workspace, such as another rollout's output or the grader's answers
    (Lesson 3); using the network to send what it read anywhere; and running
    as root, or able to become root through a setuid program. Also: the
    workspace mounted read-only, so every script that writes output fails."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-7f3a")
    (tmp_path / "other_rollout").mkdir()
    (tmp_path / "other_rollout" / "answers-7f3a.json").write_text("{}")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "data.csv").write_text("id\n1\n")

    result = run_python_tool(sandbox, ws, 30).run({"code": PROBE})
    assert not result.is_error, result.output
    seen = json.loads(result.output.split("stdout:\n", 1)[1])
    assert seen == {
        "key in its env": False,
        "key in any process": False,
        "files outside its workspace": [],
        "routes out of it": [],
        "runs as root": False,
        "capabilities it could gain": "0000000000000000",
        "can gain privileges": False,
        "workspace": ["data.csv"],
    }
    assert (ws / "written.txt").read_text() == "ok"


def test_runaway_code_is_stopped_at_the_timeout_and_leaves_nothing_running(sandbox, tmp_path):
    """Guards: an infinite loop hanging the rollout (and the pipeline); a
    process the code started in the background still running after the tool
    returned; every call leaving a stopped container behind, which fills
    Docker's disk over a pipeline run; and losing what the code printed before
    it hung, the agent's only clue to where it got stuck."""
    tool = run_python_tool(sandbox, tmp_path, 1)
    assert tool.run({"code": "print('quick')"}).output == "exit code 0\nstdout:\nquick\n"
    assert sandboxes_for(sandbox, tmp_path) == []

    runaway = ("import subprocess, time\n"
               "subprocess.Popen(['sleep', '5'], start_new_session=True)\n"
               "print('started')\n"
               "time.sleep(5)\n")
    start = time.monotonic()
    with ThreadPoolExecutor(1) as pool:
        call = pool.submit(tool.run, {"code": runaway})
        seen_running = False
        while not call.done():
            seen_running = seen_running or bool(sandboxes_for(sandbox, tmp_path))
            time.sleep(0.05)
        result = call.result()
    assert time.monotonic() - start < 4
    assert result.is_error and "timed out after 1s" in result.output and "started" in result.output
    assert seen_running, "the next check would pass without looking at anything"
    assert sandboxes_for(sandbox, tmp_path) == []


def test_fork_bombs_and_memory_blowups_stay_inside_the_sandbox(sandbox, tmp_path):
    """Guards: a fork bomb, or a script that loads far too much into memory,
    taking down Docker's VM, and with it our container and every rollout
    running in parallel."""
    small = replace(sandbox, settings=replace(sandbox.settings, memory="128m", pids_limit=32))
    tool = run_python_tool(small, tmp_path, 20)
    forks = tool.run({"code": "import subprocess\nstarted = 0\ntry:\n"
                              "    for _ in range(100):\n"
                              "        subprocess.Popen(['sleep', '5'])\n        started += 1\n"
                              "except OSError:\n    pass\nprint(started)"})
    assert int(forks.output.split()[-1]) < 32
    memory = tool.run({"code": "data = b'x' * (512 << 20)\nprint('allocated')"})
    assert memory.output.startswith("exit code 137"), "killed (SIGKILL) for using too much memory"


def test_a_broken_sandbox_ends_the_rollout_instead_of_blaming_the_model(sandbox, tmp_path, source):
    """Guards: Docker failing to start the sandbox (image not built, socket
    unreachable) reaching the agent as a bug in its own code, so it spends its
    turns fixing code that is fine and the rollout becomes false evidence; an
    error that hides Docker's reason; and downloading an image of that name
    from the internet instead of only ever running the one we built."""
    broken = replace(sandbox, settings=replace(sandbox.settings, image="mini-harness2-not-built"))
    llm, api = scripted(calls(tool_use("t1", "run_python", {"code": "print(1)"})), done())
    with pytest.raises(SandboxError, match="No such image"):
        execute(llm, broken, H0, "task", source, tmp_path / "ws", LIMITS, label="x")
    assert len(api.requests) == 1, "the model must never see this as its own error"


def test_host_paths_follow_the_most_specific_mount_and_keep_it_read_only():
    """Guards: a workspace on a nested mount translated through its parent, so
    the sandbox gets a different folder than the one we prepared; a path on
    no mount (our own /tmp) failing later with a confusing Docker error; and a
    sandbox given write access through a mount we can only read (the lesson
    source), since a host path carries no read-only flag."""
    mounts = {"/app": HostFolder("/Users/u/project", writable=False),
              "/app/runs": HostFolder("/mnt/disk/runs", writable=True)}
    assert host_path(mounts, Path("/app/runs/r1/ws"), writable=True) == "/mnt/disk/runs/r1/ws"
    assert host_path(mounts, Path("/app/base_harness"), writable=False) == "/Users/u/project/base_harness"
    with pytest.raises(SandboxError, match="no mounted folder"):
        host_path(mounts, Path("/opt/ws"), writable=True)
    with pytest.raises(SandboxError, match="read-only"):
        host_path(mounts, Path("/app/base_harness"), writable=True)


def test_run_python_rejects_args_that_are_not_a_list(sandbox, tmp_path):
    """Guards: `args` sent as one string silently becoming one argument per
    character, so a script runs with garbage input and reports nothing wrong."""
    (tmp_path / "echo.py").write_text("import sys; print(sys.argv[1:])")
    tool = run_python_tool(sandbox, tmp_path, 5)
    assert tool.run({"script": "echo.py", "args": ["in.csv", "out.csv"]}).output.endswith("['in.csv', 'out.csv']\n")
    wrong = tool.run({"script": "echo.py", "args": "in.csv out.csv"})
    assert wrong.is_error and "must be a list" in wrong.output


def test_huge_output_is_cut_on_our_side_keeping_head_and_tail(sandbox, tmp_path):
    """Guards: a script printing a whole data file flooding the agent's
    context; cutting that drops the end, where a traceback's actual error
    sits; and output held in full in our own process while it streams in
    (60 s of printing is gigabytes, enough to bring down our container)."""
    code = ("import sys\nsys.stdout.write('HEAD')\n"
            "for _ in range(100):\n    sys.stdout.write('x' * (1 << 20))\n"
            "sys.stdout.write('TAIL')\n")
    tracemalloc.start()
    try:
        result = run_python_tool(sandbox, tmp_path, 30).run({"code": code})
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert "HEAD" in result.output and "TAIL" in result.output and "bytes cut" in result.output
    assert len(result.output) < MAX_OUTPUT_CHARS + 500
    assert peak < 20 << 20, f"held {peak >> 20} MB while 100 MB streamed through"


def test_output_in_any_encoding_reaches_the_model(sandbox, tmp_path):
    """Guards: a Latin-1 export (common for office data) printed raw crashing
    the tool call, so the model gets an error instead of its data; and a
    character garbled where the kept start of the output meets the kept end."""
    half = MAX_OUTPUT_CHARS // 2
    code = ("import sys\n"
            f"sys.stdout.buffer.write(b'x' * {half - 1} + '\\u00e9'.encode() + b'\\n')\n"
            "sys.stdout.buffer.write('Caf\\u00e9 total'.encode('latin-1'))\n")
    result = run_python_tool(sandbox, tmp_path, 10).run({"code": code})
    assert not result.is_error, result.output[-300:]
    assert "x" * (half - 1) + "\u00e9\n" in result.output
    assert "Caf\ufffd total" in result.output


def test_clip_keeps_head_and_tail():
    """Guards: a subagent's long answer, or a long tool output in the evidence
    editors read (Lesson 4), flooding the context; and cutting that drops the
    end, where a traceback's actual error sits."""
    clipped = clip("HEAD" + "x" * 200_000 + "TAIL")
    assert clipped.startswith("HEAD") and clipped.endswith("TAIL") and "characters cut" in clipped
    assert len(clipped) < MAX_OUTPUT_CHARS + 100


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
    result = run_agent_loop(llm, "executor", "sys", "task", file_tools(tmp_path, tmp_path), session="loop", max_turns=5)

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
    result = run_agent_loop(llm, "executor", "sys", "task", file_tools(tmp_path, tmp_path), session="loop", max_turns=5)
    unknown, missing = tool_results(api, 1)
    assert unknown["is_error"] and "Unknown tool 'no_such_tool'" in unknown["content"]
    assert missing["is_error"] and "FileNotFoundError" in missing["content"]
    assert result.stop_reason == "end_turn"


def test_loop_stops_at_the_turn_cap(tmp_path):
    """Guards: an agent that never stops calling tools running up cost forever."""
    llm, api = scripted(*[calls(tool_use(f"t{i}", "list_files", {})) for i in range(3)])
    result = run_agent_loop(llm, "executor", "sys", "task", file_tools(tmp_path, tmp_path), session="loop", max_turns=3)
    assert result.stop_reason == "max_turns"
    assert len(api.requests) == 3 and len(result.steps) == 3


def test_a_cut_off_tool_call_is_answered_but_not_run(tmp_path):
    """Guards: a reply cut off at max_tokens mid tool call. Leaving the call
    unanswered makes the next request fail; running it would act on input
    that may be incomplete."""
    llm, api = scripted(
        calls(tool_use("t1", "write_file", {"path": "big.txt", "content": "partial"}), stop_reason="max_tokens"),
        done())
    run_agent_loop(llm, "executor", "sys", "task", file_tools(tmp_path, tmp_path), session="loop", max_turns=5)
    [answer] = tool_results(api, 1)
    assert answer["tool_use_id"] == "t1" and answer["is_error"]
    assert not (tmp_path / "big.txt").exists()


# --- Plugins (C8) ------------------------------------------------------------------

WATCH = (
    "import subprocess, sys\n"
    "def after_tool(event):\n"
    "    print('debug: checking')\n"
    "    subprocess.run([sys.executable, '-c', 'print(1)'])\n"
    "    return f\"checked {event['tool']}\"\n"
    "def before_finish(event):\n"
    "    if not event['changed_files']:\n"
    "        return 'output/ is empty: write the deliverable before finishing.'\n"
)


def test_plugin_notes_reach_the_model_and_nudges_are_bounded(sandbox, tmp_path, source):
    """Guards: a plugin's text never reaching the model (so it enforces
    nothing), including when the plugin prints, or runs a command that prints,
    which must not corrupt what it returns; a before_finish hook trapping the
    agent forever; and hooks being told the wrong output files."""
    harness = Harness({**H0.files, "plugin/watch.py": WATCH})
    llm, api = scripted(calls(tool_use("t1", "list_files", {})), done(), done(), done("finished anyway"))
    record = execute(llm, sandbox, harness, "task", source, tmp_path / "ws1", LIMITS, label="p1")
    assert "[plugin watch] checked list_files" in tool_results(api, 1)[0]["content"]
    nudges = [s.nudge for s in record.steps if s.nudge]
    assert len(nudges) == MAX_NUDGES and "output/ is empty" in nudges[0]
    assert record.stop_reason == "end_turn" and len(api.requests) == 2 + MAX_NUDGES

    llm, api = scripted(calls(tool_use("t1", "write_file", {"path": "output/x.csv", "content": "a"})), done())
    record = execute(llm, sandbox, harness, "task", source, tmp_path / "ws2", LIMITS, label="p2")
    assert not any(s.nudge for s in record.steps), "a deliverable exists, so no nudge"


def test_a_broken_plugin_is_recorded_and_the_rollout_continues(sandbox, tmp_path, source):
    """Guards: an editor's buggy plugin (crash, hang, wrong return type, an
    early sys.exit) taking down the rollout instead of showing up as evidence
    against that edit; and a plugin rewriting the deliverable behind the
    agent's back, so the trajectory no longer explains the output."""
    harness = Harness({
        **H0.files,
        "plugin/crash.py": "def after_tool(event):\n    raise RuntimeError('boom')\n",
        "plugin/slow.py": "import time\ndef before_finish(event):\n    time.sleep(30)\n",
        "plugin/wrong.py": "def after_tool(event):\n    return 42\n",
        "plugin/quits.py": "import sys\ndef after_tool(event):\n    sys.exit(0)\n",
        "plugin/meddle.py": "def after_tool(event):\n    open('forged.csv', 'w').write('x')\n",
    })
    llm, _ = scripted(calls(tool_use("t1", "list_files", {})), done())
    record = execute(llm, sandbox, harness, "task", source, tmp_path / "ws", RolloutLimits(6, 3, 1), label="b")
    errors = " | ".join(record.hook_errors)
    assert record.stop_reason == "end_turn"
    assert "crash.after_tool: RuntimeError: boom" in errors
    assert "slow.before_finish: timed out" in errors
    assert "wrong.after_tool: returned int" in errors
    assert "quits.after_tool: no readable result" in errors
    assert "meddle.after_tool: OSError" in errors and record.deliverable == {}


# --- Skills (C6), subagents (C5), the workspace, the record ---------------------

def test_skill_and_subagent_tools_follow_the_harness(sandbox, tmp_path, source):
    """Guards: offering tools that can only fail (no skills to load), the agent
    not being told what each skill or subagent is for (Lesson 1 requires the
    descriptions for exactly this), a subagent that can delegate again
    (unbounded recursion), and a subagent flooding the caller's context
    instead of returning only its answer."""
    llm, api = scripted(done())
    execute(llm, sandbox, H0, "task", source, tmp_path / "ws0", LIMITS, label="h0")
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
    record = execute(llm, sandbox, harness, "task", source, tmp_path / "ws1", LIMITS, label="h1")

    offered = {t["name"]: t["description"] for t in api.requests[0].body["tools"]}
    assert "- money: Parse money strings." in offered["load_skill"]
    assert "- reader: Summarises a file." in offered["run_subagent"]
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

    used = tmp_path / "used"
    used.mkdir()
    (used / "leftover_from_another_rollout.txt").write_text("stale")
    with pytest.raises(FileExistsError):
        prepare_workspace(used, source, harness)


def test_execute_records_the_deliverable_and_stats(sandbox, tmp_path, source):
    """Guards: the deliverable y missing what the agent wrote (including a
    report at the workspace root, where the real task wants it), or padded
    with the task's untouched inputs and the harness's own scripts; the
    harness not actually reaching the model; and wrong Table 7 statistics."""
    harness = Harness({**H0.files, "scripts/check.py": "print('ok')"})
    llm, api = scripted(
        calls(tool_use("t1", "write_file", {"path": "output/summary.csv", "content": "id,amount\n1,5\n"}),
              tool_use("t2", "write_file", {"path": "report.md", "content": "# Report"}),
              tool_use("t3", "read_file", {"path": "nope.csv"})),
        done("Wrote the summary and the report"))
    record = execute(llm, sandbox, harness, "Sum the amounts.", source, tmp_path / "ws", LIMITS, label="base_1")
    assert record.deliverable == {"output/summary.csv": "id,amount\n1,5\n", "report.md": "# Report"}
    assert (record.turns, record.tool_calls, record.tool_errors) == (2, 3, 1)
    assert api.requests[0].body["system"] == harness.always_on_text()
    assert api.requests[0].body["messages"][0]["content"] == "Sum the amounts."
    assert "[ERROR]" in render_record(record)


def test_execute_refuses_an_invalid_harness(sandbox, tmp_path, source):
    """Guards: paying for a rollout of a harness that breaks the rules, or
    crashing halfway through setup with a confusing error."""
    broken = Harness({**H0.files, "plugin/bad.py": "def after_tool(:\n"})
    llm, api = scripted()
    with pytest.raises(ValueError, match="invalid harness"):
        execute(llm, sandbox, broken, "task", source, tmp_path / "ws", LIMITS, label="x")
    assert api.requests == []
