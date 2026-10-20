"""Lesson 2: The agent A(q; M, H) and its execution record e = (τ, y).

Paper anchors
-------------
* §2.1: the harness "composes with M to form an agent A(·; M, H)".
* §2.2.1: "Let e = (τ, y) denote an execution record, with trajectory τ and
  deliverable y." Running the agent once is written e ~ A(q; M, H).
* Table 5, activation: C1-C4 reach the model on every call; a skill loads
  through a tool; a script runs on demand; a subagent works in its own context
  and returns only its result; a plugin "enforces a behavior rather than
  instructs it".
* §D.1: every rollout starts in a fresh workspace with a turn cap and no memory
  of other tasks. Table 7 counts tool calls and tool errors per rollout.

Design
------
* `run_agent_loop` is the generic tool-use loop. Lesson 4 reuses it for the
  harness editors, with different tools and no plugins.
* A `Tool` is a value: the schema the model sees plus the handler we run.
  `file_tools(read_root, write_root)` builds file tools for any sandbox.
* Code the model writes (run_python, plugin hooks) runs in a subprocess with the
  workspace as its cwd, a timeout, and an environment without the API key.
  That is containment, not a security sandbox: the subprocess still shares the
  container with the executor (see README, "Safety").
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol

from config import RolloutLimits
from steps.s00_llm import LLM, text_of
from steps.s01_harness import PLUGIN_FILE, PLUGIN_HOOKS, SCRIPT_FILE, SKILL_SCRIPT, Document, Harness, validate

MAX_OUTPUT_CHARS = 20_000   # per tool result, so one big print can't flood the context
MAX_NUDGES = 2              # how often before_finish hooks may keep the agent working
_CHILD_ENV = MappingProxyType({"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"})


# ---------------------------------------------------------------------------
# Trajectory τ and execution record e = (τ, y)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolCall:
    name: str
    input: Mapping[str, Any]
    output: str                       # what the tool returned (before plugin notes)
    is_error: bool
    notes: tuple[str, ...] = ()       # text plugins appended for the model (C8 after_tool)
    subtrace: tuple[Step, ...] = ()   # a subagent's own steps (C5)


@dataclass(frozen=True)
class Step:
    """One model turn: its visible text and the tools it called."""
    turn: int
    text: str
    calls: tuple[ToolCall, ...] = ()
    nudge: str | None = None          # a message sent after this turn to keep it working


@dataclass(frozen=True)
class LoopResult:
    steps: tuple[Step, ...]
    final_text: str
    stop_reason: str                  # end_turn | max_turns | refusal
    hook_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionRecord:
    """e = (τ, y): one rollout's trajectory and deliverable."""
    label: str
    harness: Harness
    steps: tuple[Step, ...]           # τ
    deliverable: Mapping[str, str]    # y: every file in output/, by path
    final_text: str
    stop_reason: str
    hook_errors: tuple[str, ...]
    workspace: Path

    @property
    def turns(self) -> int:
        return len(self.steps)

    @property
    def tool_calls(self) -> int:
        return sum(len(s.calls) for s in self.steps)

    @property
    def tool_errors(self) -> int:
        return sum(c.is_error for s in self.steps for c in s.calls)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolResult:
    output: str
    is_error: bool = False
    subtrace: tuple[Step, ...] = ()


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    run: Callable[[Mapping[str, Any]], ToolResult]

    def definition(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


def clip(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """Keep the head and the tail (where tracebacks end) of an over-long text."""
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n[... {len(text) - 2 * half} characters cut ...]\n{text[-half:]}"


def resolve_inside(root: Path, rel: str) -> Path:
    """`rel` as a path inside `root`. Symlinks are resolved first, so a link can't lead out."""
    base = root.resolve()
    path = (base / rel).resolve()
    if not path.is_relative_to(base):
        raise ValueError(f"{rel!r} is outside {root.name}/")
    return path


def file_tools(read_root: Path, write_root: Path) -> list[Tool]:
    """list_files / read_file / write_file. Paths are relative to `read_root`;
    writes must also land inside `write_root`."""

    def list_files(inp: Mapping[str, Any]) -> ToolResult:
        base = resolve_inside(read_root, inp.get("path", "."))
        rows = [f"{p.relative_to(read_root.resolve()).as_posix()}  ({p.stat().st_size} bytes)"
                for p in sorted(base.rglob("*")) if p.is_file()]
        return ToolResult("\n".join(rows[:500]) or "(no files)")

    def read_file(inp: Mapping[str, Any]) -> ToolResult:
        text = resolve_inside(read_root, inp["path"]).read_text(encoding="utf-8", errors="replace")
        start = int(inp.get("offset", 0))
        chunk = text[start:start + MAX_OUTPUT_CHARS]
        if start + len(chunk) < len(text):
            chunk += (f"\n[showing characters {start}-{start + len(chunk)} of {len(text)}; "
                      f"call again with offset={start + len(chunk)}]")
        return ToolResult(chunk or "(empty file)")

    def write_file(inp: Mapping[str, Any]) -> ToolResult:
        path = resolve_inside(read_root, inp["path"])
        if not path.is_relative_to(write_root.resolve()):
            raise ValueError(f"{inp['path']!r} is outside the writable area {write_root.name}/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(inp["content"], encoding="utf-8")
        return ToolResult(f"Wrote {len(inp['content'])} characters to {inp['path']}")

    path_prop = {"type": "string", "description": "Path relative to the workspace root."}
    return [
        Tool("list_files", "List files (recursively) under a directory, with sizes.",
             {"type": "object", "properties": {"path": path_prop}}, list_files),
        Tool("read_file", f"Read a text file. Long files come in chunks of {MAX_OUTPUT_CHARS} characters.",
             {"type": "object", "properties": {"path": path_prop, "offset": {"type": "integer"}},
              "required": ["path"]}, read_file),
        Tool("write_file", "Create or overwrite a text file (parent directories are created).",
             {"type": "object", "properties": {"path": path_prop, "content": {"type": "string"}},
              "required": ["path", "content"]}, write_file),
    ]


@dataclass(frozen=True)
class Completed:
    returncode: int | None   # None: killed at the timeout
    stdout: str
    stderr: str


def run_confined(cmd: list[str], cwd: Path, timeout_s: float, stdin: str = "") -> Completed:
    """Run code the model wrote: cwd = its workspace, a timeout, and an
    environment that does not carry the API key."""
    env = {**_CHILD_ENV, "HOME": str(cwd)}
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, input=stdin, capture_output=True, text=True, timeout=timeout_s)
        return Completed(p.returncode, p.stdout, p.stderr)
    except subprocess.TimeoutExpired as e:
        as_text = lambda b: b.decode(errors="replace") if isinstance(b, bytes) else (b or "")
        return Completed(None, as_text(e.stdout), as_text(e.stderr))


def run_python_tool(workspace: Path, timeout_s: float) -> Tool:
    def run(inp: Mapping[str, Any]) -> ToolResult:
        code, script, args = inp.get("code"), inp.get("script"), inp.get("args", [])
        if (code is None) == (script is None):
            return ToolResult("Give exactly one of `code` or `script`.", is_error=True)
        if not isinstance(args, list):  # a string would become one argument per character
            return ToolResult("`args` must be a list of strings.", is_error=True)
        target = ["-c", code] if code is not None else [str(resolve_inside(workspace, script))]
        done = run_confined([sys.executable, "-I", *target, *map(str, args)], workspace, timeout_s)
        status = f"timed out after {timeout_s:g}s" if done.returncode is None else f"exit code {done.returncode}"
        parts = [status]
        if done.stdout:
            parts.append(f"stdout:\n{clip(done.stdout)}")
        if done.stderr:
            parts.append(f"stderr:\n{clip(done.stderr)}")
        return ToolResult("\n".join(parts), is_error=done.returncode != 0)

    return Tool(
        "run_python",
        f"Run Python with the workspace as the current directory ({timeout_s:g}s limit). "
        "Give `code` to run a snippet, or `script` (a .py path in the workspace) plus optional `args`.",
        {"type": "object", "properties": {
            "code": {"type": "string"},
            "script": {"type": "string"},
            "args": {"type": "array", "items": {"type": "string"}},
        }},
        run,
    )


def _listing(documents: Mapping[str, Document]) -> str:
    """One line per skill or subagent: what the agent reads to choose one."""
    return "\n".join(f"- {name}: {d.meta.get('description', '')}" for name, d in sorted(documents.items()))


def skill_tool(harness: Harness) -> Tool | None:
    """C6: offered only when the harness has skills."""
    skills = harness.skills()
    if not skills:
        return None

    def run(inp: Mapping[str, Any]) -> ToolResult:
        skill = skills.get(inp["name"])
        if skill is None:
            return ToolResult(f"No skill {inp['name']!r}. Available: {', '.join(sorted(skills))}.", is_error=True)
        return ToolResult(skill.body.strip() or "(this skill is empty)")

    return Tool("load_skill", f"Load a skill's procedure into context. Skills:\n{_listing(skills)}",
                {"type": "object", "properties": {"name": {"type": "string", "enum": sorted(skills)}},
                 "required": ["name"]}, run)


def subagent_tool(llm: LLM, harness: Harness, workspace: Path, limits: RolloutLimits) -> Tool | None:
    """C5: a worker in its own context that returns only its final text. It gets
    the file tools and run_python, but cannot delegate again (depth 1)."""
    agents = harness.subagents()
    if not agents:
        return None

    def run(inp: Mapping[str, Any]) -> ToolResult:
        agent = agents.get(inp["name"])
        if agent is None:
            return ToolResult(f"No subagent {inp['name']!r}. Available: {', '.join(sorted(agents))}.", is_error=True)
        tools = [*file_tools(workspace, workspace), run_python_tool(workspace, limits.tool_timeout_s)]
        sub = run_agent_loop(llm, "executor", agent.body, inp["prompt"], tools, max_turns=limits.subagent_max_turns)
        if sub.stop_reason != "end_turn" or not sub.final_text.strip():
            return ToolResult(f"The subagent stopped ({sub.stop_reason}) without an answer.",
                              is_error=True, subtrace=sub.steps)
        return ToolResult(clip(sub.final_text), subtrace=sub.steps)

    return Tool("run_subagent", f"Delegate a self-contained job; you get back only its final answer. Subagents:\n{_listing(agents)}",
                {"type": "object", "properties": {"name": {"type": "string", "enum": sorted(agents)},
                                                  "prompt": {"type": "string"}},
                 "required": ["name", "prompt"]}, run)


# ---------------------------------------------------------------------------
# Plugins (C8): hooks that run inside the loop
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HookResult:
    texts: tuple[str, ...] = ()    # what hooks returned
    errors: tuple[str, ...] = ()   # hooks that crashed, timed out or returned a non-string


class Hooks(Protocol):
    def after_tool(self, event: dict[str, Any]) -> HookResult: ...
    def before_finish(self, event: dict[str, Any]) -> HookResult: ...


_HOOK_RUNNER = """
import json, runpy, sys
hook = runpy.run_path(sys.argv[1])[sys.argv[2]]
result = hook(json.load(sys.stdin))
with open(sys.argv[3], "w") as f:
    json.dump(result, f)
"""


class PluginHooks:
    """Runs each plugin's hooks in a confined subprocess. A plugin that crashes
    or times out is recorded, never fatal: it must not take the rollout down."""

    def __init__(self, sources: Mapping[str, Path], defined: Mapping[str, frozenset[str]],
                 workspace: Path, timeout_s: float) -> None:
        self._sources = sources      # plugin name -> its .py file (outside the workspace)
        self._defined = defined      # plugin name -> the hooks it defines
        self._workspace = workspace
        self._timeout_s = timeout_s

    def after_tool(self, event: dict[str, Any]) -> HookResult:
        return self._call("after_tool", event)

    def before_finish(self, event: dict[str, Any]) -> HookResult:
        return self._call("before_finish", event)

    def _call(self, hook: str, event: dict[str, Any]) -> HookResult:
        output_dir = self._workspace / "output"
        event = {**event, "output_files": sorted(p.relative_to(output_dir).as_posix()
                                                 for p in output_dir.rglob("*") if p.is_file())}
        texts, errors = [], []
        for name, source in sorted(self._sources.items()):
            if hook not in self._defined[name]:
                continue
            result_file = source.with_suffix(f".{hook}.json")
            result_file.unlink(missing_ok=True)
            done = run_confined([sys.executable, "-I", "-c", _HOOK_RUNNER, str(source), hook, str(result_file)],
                                self._workspace, self._timeout_s, stdin=json.dumps(event))
            if done.returncode != 0:
                why = "timed out" if done.returncode is None else (done.stderr.strip().splitlines() or ["crashed"])[-1]
                errors.append(f"plugin {name}.{hook}: {why}")
                continue
            value = json.loads(result_file.read_text())
            if value is None:
                continue
            if isinstance(value, str):
                texts.append(f"[plugin {name}] {value}")
            else:
                errors.append(f"plugin {name}.{hook}: returned {type(value).__name__}, expected a string or None")
        return HookResult(tuple(texts), tuple(errors))


def plugin_hooks(harness: Harness, plugin_dir: Path, workspace: Path, timeout_s: float) -> PluginHooks | None:
    """Write the harness's plugins to `plugin_dir` (outside the workspace, so the
    agent can't edit them) and return hooks that run them. None if there are none."""
    sources, defined = {}, {}
    for path, text in harness.files.items():
        if PLUGIN_FILE.fullmatch(path):
            name = Path(path).stem
            sources[name] = plugin_dir / f"{name}.py"
            sources[name].write_text(text, encoding="utf-8")
            defined[name] = frozenset(n.name for n in ast.parse(text).body
                                      if isinstance(n, ast.FunctionDef) and n.name in PLUGIN_HOOKS)
    return PluginHooks(sources, defined, workspace, timeout_s) if sources else None


# ---------------------------------------------------------------------------
# The agent loop
# ---------------------------------------------------------------------------

_CUT_OFF_CALL = ("Not run: your reply hit the output limit before this call was complete. "
                 "Retry with less in one call, e.g. write a large file in parts.")
_CUT_OFF_TEXT = "Your reply hit the output limit. Continue where you stopped."


def _run_tool(tools: Mapping[str, Tool], name: str, inp: Mapping[str, Any]) -> ToolResult:
    tool = tools.get(name)
    if tool is None:
        return ToolResult(f"Unknown tool {name!r}. Available: {', '.join(sorted(tools))}.", is_error=True)
    try:
        return tool.run(inp)
    except Exception as e:  # a failing tool is reported to the model; it must not end the rollout
        return ToolResult(f"{name} failed: {type(e).__name__}: {e}", is_error=True)


def run_agent_loop(llm: LLM, role: str, system: str, task: str, tools: list[Tool], *,
                   max_turns: int, hooks: Hooks | None = None) -> LoopResult:
    """Call the model, run the tools it asks for, repeat until it stops or the turn cap.

    Two API rules hold throughout (see Lesson 0): each response is appended
    unchanged, and history is append-only. All tool results for one turn go
    back in a single user message.
    """
    by_name = {t.name: t for t in tools}
    definitions = [t.definition() for t in tools]
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    steps: list[Step] = []
    hook_errors: list[str] = []
    nudges = 0

    for turn in range(1, max_turns + 1):
        response = llm.call(role, system, messages, definitions)
        messages.append({"role": "assistant", "content": response.content})
        text = text_of(response)
        uses = [b for b in response.content if b.type == "tool_use"]

        if uses:
            calls, results = [], []
            for use in uses:
                if response.stop_reason == "max_tokens":
                    result = ToolResult(_CUT_OFF_CALL, is_error=True)  # its input may be incomplete
                else:
                    result = _run_tool(by_name, use.name, use.input)
                notes: tuple[str, ...] = ()
                if hooks:
                    h = hooks.after_tool({"tool": use.name, "input": use.input, "output": result.output,
                                          "is_error": result.is_error, "turn": turn})
                    notes = h.texts
                    hook_errors += [f"turn {turn}: {e}" for e in h.errors]
                results.append({"type": "tool_result", "tool_use_id": use.id, "is_error": result.is_error,
                                "content": "\n\n".join([result.output, *notes])})
                calls.append(ToolCall(use.name, use.input, result.output, result.is_error, notes, result.subtrace))
            messages.append({"role": "user", "content": results})
            steps.append(Step(turn, text, tuple(calls)))
            continue

        if response.stop_reason == "refusal":
            steps.append(Step(turn, text))
            return LoopResult(tuple(steps), text, "refusal", tuple(hook_errors))

        if response.stop_reason == "max_tokens":
            steps.append(Step(turn, text, nudge=_CUT_OFF_TEXT))
            messages.append({"role": "user", "content": _CUT_OFF_TEXT})
            continue

        # The model wants to finish. A before_finish hook may keep it working.
        if hooks and nudges < MAX_NUDGES:
            h = hooks.before_finish({"turn": turn, "final_text": text})
            hook_errors += [f"turn {turn}: {e}" for e in h.errors]
            if h.texts:
                nudges += 1
                nudge = "\n\n".join(h.texts)
                steps.append(Step(turn, text, nudge=nudge))
                messages.append({"role": "user", "content": nudge})
                continue
        steps.append(Step(turn, text))
        return LoopResult(tuple(steps), text, "end_turn", tuple(hook_errors))

    return LoopResult(tuple(steps), "", "max_turns", tuple(hook_errors))


# ---------------------------------------------------------------------------
# One rollout: e ~ A(q; M, H)
# ---------------------------------------------------------------------------

def prepare_workspace(workspace: Path, source_dir: Path, harness: Harness) -> None:
    """A fresh workspace: the task's inputs in source/, an empty output/, and the
    harness's scripts at their own paths so text that names them is right.
    Skill bodies and plugins stay out: they reach the agent only through tools and hooks."""
    if workspace.exists() and any(workspace.iterdir()):
        raise FileExistsError(f"{workspace} is not empty; every rollout starts fresh")
    shutil.copytree(source_dir, workspace / "source")
    (workspace / "output").mkdir()
    for path, text in harness.files.items():
        if SCRIPT_FILE.fullmatch(path) or SKILL_SCRIPT.fullmatch(path):
            (workspace / path).parent.mkdir(parents=True, exist_ok=True)
            (workspace / path).write_text(text, encoding="utf-8")


def execute(llm: LLM, harness: Harness, task: str, source_dir: Path, workspace: Path,
            limits: RolloutLimits, *, label: str) -> ExecutionRecord:
    """Run the agent once on a task and record what it did and produced."""
    if errors := validate(harness):
        raise ValueError("refusing to run an invalid harness: " + "; ".join(errors))
    prepare_workspace(workspace, source_dir, harness)
    tools = [*file_tools(workspace, workspace), run_python_tool(workspace, limits.tool_timeout_s)]
    tools += [t for t in (skill_tool(harness), subagent_tool(llm, harness, workspace, limits)) if t]
    with tempfile.TemporaryDirectory() as plugin_dir:
        hooks = plugin_hooks(harness, Path(plugin_dir), workspace, limits.tool_timeout_s)
        result = run_agent_loop(llm, "executor", harness.always_on_text(), task, tools,
                                max_turns=limits.max_turns, hooks=hooks)
    output = workspace / "output"
    deliverable = {p.relative_to(output).as_posix(): p.read_text(encoding="utf-8", errors="replace")
                   for p in sorted(output.rglob("*")) if p.is_file()}
    return ExecutionRecord(label, harness, result.steps, deliverable, result.final_text,
                           result.stop_reason, result.hook_errors, workspace)


# ---------------------------------------------------------------------------
# Rendering τ for people and for the editors (Lesson 4)
# ---------------------------------------------------------------------------

def render_trajectory(steps: tuple[Step, ...], *, clip_at: int = 1500, indent: str = "") -> str:
    lines = []
    for step in steps:
        lines.append(f"{indent}### Turn {step.turn}")
        if step.text.strip():
            lines.append(indent + step.text.strip().replace("\n", "\n" + indent))
        for call in step.calls:
            lines.append(f"{indent}-> {call.name} {clip(json.dumps(call.input, ensure_ascii=False), clip_at)}")
            mark = "ERROR" if call.is_error else "ok"
            lines.append(f"{indent}   [{mark}] " + clip(call.output, clip_at).replace("\n", "\n" + indent + "   "))
            lines += [f"{indent}   {note}" for note in call.notes]
            if call.subtrace:
                lines.append(render_trajectory(call.subtrace, clip_at=clip_at, indent=indent + "    | "))
        if step.nudge:
            lines.append(f"{indent}<- (sent to the model) {step.nudge}")
    return "\n".join(lines)


def render_record(record: ExecutionRecord) -> str:
    """The evidence an editor reads about one rollout."""
    head = (f"# Rollout {record.label}\n\nStopped: {record.stop_reason} after {record.turns} turns, "
            f"{record.tool_calls} tool calls ({record.tool_errors} errors).")
    if record.hook_errors:
        head += "\nPlugin errors: " + "; ".join(record.hook_errors)
    files = "\n".join(f"- output/{p} ({len(t)} chars)" for p, t in record.deliverable.items()) or "- (none)"
    return f"{head}\n\nDeliverable:\n{files}\n\n## Trajectory\n\n{render_trajectory(record.steps)}"
