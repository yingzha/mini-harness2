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
  `file_tools(read_root, write_root)` builds file tools for any folder.
* Code the model writes (run_python, plugin hooks) runs in a `Sandbox`: a fresh
  Docker container per call that sees only the workspace, with no network, no
  secrets, an unprivileged user and process and memory caps, removed with
  everything it started when the call ends. Our own code, which holds the API
  key, never runs model-written code (see README, "Safety").
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import json
import shutil
import socket
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import IO, Any, Callable, Mapping, Protocol

from config import RolloutLimits, SandboxSettings
from steps.s00_llm import LLM, text_of
from steps.s01_harness import PLUGIN_FILE, PLUGIN_HOOKS, SCRIPT_FILE, SKILL_SCRIPT, Document, Harness, validate

MAX_OUTPUT_CHARS = 20_000   # per tool result, so one big print can't flood the context
                            # (sandbox output is cut at this many bytes, never more characters)
MAX_NUDGES = 2              # how often before_finish hooks may keep the agent working


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
    deliverable: Mapping[str, str]    # y: every file the agent created or changed, by workspace path
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


# ---------------------------------------------------------------------------
# The sandbox: where code the model wrote runs
# ---------------------------------------------------------------------------

WORKDIR = "/work"                        # where a sandbox sees the workspace
SANDBOX_LABEL = "mini-harness2-sandbox"  # on every sandbox container; its value is the workspace
_PYTHON = ("python", "-I", "-u")         # -I: ignore env and user site. -u: unbuffered, so
                                         # what it printed before a timeout isn't lost


class SandboxError(RuntimeError):
    """Docker couldn't run the sandbox. That is our failure, not the model's, so it
    ends the rollout instead of reaching the agent as a tool error."""


@dataclass(frozen=True)
class HostFolder:
    """A folder mounted into this container, as the Docker daemon knows it."""
    source: str      # its path on the machine running Docker
    writable: bool


@dataclass(frozen=True)
class Completed:
    returncode: int | None   # None: killed at the timeout
    stdout: str
    stderr: str


class _HeadTail:
    """Keeps the start and the end of a stream, `limit` bytes in all, however much
    comes through. Output is read on our side of the sandbox, so how much of our
    memory it takes must not be up to the code that prints it. (`clip` does the
    same for text already in memory.)"""

    def __init__(self, limit: int) -> None:
        self._half = limit // 2
        self._head = bytearray()
        self._tail = bytearray()
        self._total = 0

    def read_all(self, stream: IO[bytes]) -> None:
        while chunk := stream.read1(1 << 16):
            self._total += len(chunk)
            room = self._half - len(self._head)
            self._head += chunk[:room]
            self._tail += chunk[room:]
            del self._tail[:-self._half]

    def text(self) -> str:
        decode = lambda b: bytes(b).decode(errors="replace")   # model code may print any bytes
        cut = self._total - len(self._head) - len(self._tail)
        if not cut:   # head and tail are one stream: decode them together, or a character between them breaks
            return decode(self._head + self._tail)
        return f"{decode(self._head)}\n[... {cut} bytes cut ...]\n{decode(self._tail)}"


def _feed(stream: IO[bytes], data: bytes) -> None:
    with contextlib.suppress(BrokenPipeError):   # the process exited without reading it all
        with stream:
            stream.write(data)


def host_path(mounts: Mapping[str, HostFolder], path: Path, *, writable: bool) -> str:
    """Where `path`, a path in this container, is for the Docker daemon.

    `docker create --mount` takes paths on the machine running Docker, not paths
    in our container, so a path is translated through the mount it lies on.
    `mounts` maps each mount point in this container to that folder."""
    path = path.resolve()
    points = [p for p in mounts if path.is_relative_to(p)]
    if not points:
        raise SandboxError(f"{path} is on no mounted folder, so no sandbox can be given it")
    point = max(points, key=len)   # the most specific mount: /app/runs, not /app
    folder = mounts[point]
    if writable and not folder.writable:
        raise SandboxError(f"{path} is read-only here, so a sandbox can't be given it to write")
    return str(PurePosixPath(folder.source) / path.relative_to(point))


@dataclass(frozen=True)
class Sandbox:
    """Runs each command in a fresh container that sees only the workspace it is
    given: no network, no environment from us (so no API key), an unprivileged
    user without capabilities, and caps on processes and memory. However the call
    ends, the container is removed, which kills whatever it left running."""
    settings: SandboxSettings
    mounts: Mapping[str, HostFolder]   # this container's mounts (see host_path)

    @classmethod
    def from_docker(cls, settings: SandboxSettings) -> Sandbox:
        """Ask Docker for this container's mounts. A container's hostname is its ID."""
        done = subprocess.run(["docker", "inspect", "--format", "{{json .Mounts}}", socket.gethostname()],
                              capture_output=True, text=True)
        if done.returncode != 0:
            raise SandboxError("can't inspect this container; run inside it, with the Docker socket "
                               f"mounted (see compose.yaml): {done.stderr.strip()}")
        return cls(settings, MappingProxyType({m["Destination"]: HostFolder(m["Source"], m["RW"])
                                               for m in json.loads(done.stdout)}))

    def run(self, cmd: list[str], workspace: Path, *, writable: bool, timeout_s: float, stdin: str = "",
            readonly: Mapping[str, Path] = MappingProxyType({}), env: Mapping[str, str] = MappingProxyType({}),
            max_output: int = MAX_OUTPUT_CHARS) -> Completed:
        """`workspace` is mounted at WORKDIR, the working directory. `readonly` maps
        more container paths to folders of ours, mounted read-only; `env` sets
        variables. Nothing else of ours reaches the container. Each output stream
        is cut to `max_output` bytes (start and end kept)."""
        source = host_path(self.mounts, workspace, writable=writable)
        mount = f"type=bind,src={source},dst={WORKDIR}"
        more = [arg for dst, path in readonly.items() for arg in
                ("--mount", f"type=bind,src={host_path(self.mounts, path, writable=False)},dst={dst},readonly")]
        variables = [arg for name, value in env.items() for arg in ("--env", f"{name}={value}")]
        made = subprocess.run([
            "docker", "create", "--interactive",
            "--label", f"{SANDBOX_LABEL}={source}",
            "--pull", "never",                     # only the image we built, never a download
            "--network", "none",
            "--user", self.settings.user,
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", str(self.settings.pids_limit),
            "--memory", self.settings.memory,
            "--mount", mount if writable else f"{mount},readonly", *more, *variables,
            "--workdir", WORKDIR,
            self.settings.image, *cmd,
        ], capture_output=True, text=True)
        if made.returncode != 0:
            raise SandboxError(f"Docker couldn't create the sandbox: {made.stderr.strip()}")
        container = made.stdout.strip()
        out, err = _HeadTail(max_output), _HeadTail(max_output)
        try:
            with subprocess.Popen(["docker", "start", "--attach", "--interactive", container],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as p:
                io = [threading.Thread(target=_feed, args=(p.stdin, stdin.encode())),
                      threading.Thread(target=out.read_all, args=(p.stdout,)),
                      threading.Thread(target=err.read_all, args=(p.stderr,))]
                for t in io:
                    t.start()
                try:
                    returncode = p.wait(timeout=timeout_s)
                except subprocess.TimeoutExpired:
                    p.kill()   # its streams close, so the threads finish
                    returncode = None
                for t in io:
                    t.join()
        finally:
            subprocess.run(["docker", "rm", "--force", container], capture_output=True)
        return Completed(returncode, out.text(), err.text())


def run_python_tool(sandbox: Sandbox, workspace: Path, timeout_s: float) -> Tool:
    def run(inp: Mapping[str, Any]) -> ToolResult:
        code, script, args = inp.get("code"), inp.get("script"), inp.get("args", [])
        if (code is None) == (script is None):
            return ToolResult("Give exactly one of `code` or `script`.", is_error=True)
        if not isinstance(args, list):  # a string would become one argument per character
            return ToolResult("`args` must be a list of strings.", is_error=True)
        target = ["-c", code] if code is not None else [script]
        done = sandbox.run([*_PYTHON, *target, *map(str, args)], workspace, writable=True, timeout_s=timeout_s)
        status = f"timed out after {timeout_s:g}s" if done.returncode is None else f"exit code {done.returncode}"
        parts = [status]   # the sandbox has already cut stdout and stderr to size
        if done.stdout:
            parts.append(f"stdout:\n{done.stdout}")
        if done.stderr:
            parts.append(f"stderr:\n{done.stderr}")
        return ToolResult("\n".join(parts), is_error=done.returncode != 0)

    return Tool(
        "run_python",
        f"Run Python with the workspace as the current directory ({timeout_s:g}s limit, standard "
        "library only, no network). Give `code` to run a snippet, or `script` (a .py path in the "
        "workspace) plus optional `args`.",
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


def subagent_tool(llm: LLM, sandbox: Sandbox, harness: Harness, workspace: Path,
                  limits: RolloutLimits) -> Tool | None:
    """C5: a worker in its own context that returns only its final text. It gets
    the file tools and run_python, but cannot delegate again (depth 1)."""
    agents = harness.subagents()
    if not agents:
        return None

    def run(inp: Mapping[str, Any]) -> ToolResult:
        agent = agents.get(inp["name"])
        if agent is None:
            return ToolResult(f"No subagent {inp['name']!r}. Available: {', '.join(sorted(agents))}.", is_error=True)
        tools = [*file_tools(workspace, workspace), run_python_tool(sandbox, workspace, limits.tool_timeout_s)]
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


# Runs in the sandbox: reads {source, path, hook, event} on stdin, writes the hook's result on stdout.
_HOOK_RUNNER = """
import json, os, sys
request = json.load(sys.stdin)
with os.fdopen(os.dup(1), "w") as result:
    os.dup2(2, 1)   # what the plugin prints, even from a subprocess, goes to stderr, not into its result
    plugin = {"__name__": "plugin"}
    exec(compile(request["source"], request["path"], "exec"), plugin)
    json.dump(plugin[request["hook"]](request["event"]), result)
"""


class PluginHooks:
    """Runs each plugin's hooks in the sandbox, with the workspace read-only: a
    plugin observes and advises, it never changes the deliverable behind the
    agent's back. A plugin that crashes, hangs or returns garbage is recorded,
    never fatal: it must not take the rollout down."""

    def __init__(self, sandbox: Sandbox, sources: Mapping[str, str], defined: Mapping[str, frozenset[str]],
                 workspace: Path, baseline: Mapping[str, str], timeout_s: float) -> None:
        self._sandbox = sandbox
        self._sources = sources      # plugin name -> its code
        self._defined = defined      # plugin name -> the hooks it defines
        self._workspace = workspace
        self._baseline = baseline    # the workspace as the rollout started (see changed_files)
        self._timeout_s = timeout_s

    def after_tool(self, event: dict[str, Any]) -> HookResult:
        return self._call("after_tool", event)

    def before_finish(self, event: dict[str, Any]) -> HookResult:
        return self._call("before_finish", event)

    def _call(self, hook: str, event: dict[str, Any]) -> HookResult:
        event = {**event, "changed_files": changed_files(self._workspace, self._baseline)}
        texts, errors = [], []
        for name, source in sorted(self._sources.items()):
            if hook not in self._defined[name]:
                continue
            request = json.dumps({"source": source, "path": f"plugin/{name}.py", "hook": hook, "event": event})
            done = self._sandbox.run([*_PYTHON, "-c", _HOOK_RUNNER], self._workspace, writable=False,
                                     timeout_s=self._timeout_s, stdin=request)
            if done.returncode != 0:
                why = "timed out" if done.returncode is None else (done.stderr.strip().splitlines() or ["crashed"])[-1]
                errors.append(f"plugin {name}.{hook}: {why}")
                continue
            try:
                value = json.loads(done.stdout)
            except ValueError:   # it called sys.exit(), or its result was cut to size
                errors.append(f"plugin {name}.{hook}: no readable result (it exited early, or returned too much)")
                continue
            if value is None:
                continue
            if isinstance(value, str):
                texts.append(f"[plugin {name}] {value}")
            else:
                errors.append(f"plugin {name}.{hook}: returned {type(value).__name__}, expected a string or None")
        return HookResult(tuple(texts), tuple(errors))


def plugin_hooks(harness: Harness, sandbox: Sandbox, workspace: Path, baseline: Mapping[str, str],
                 timeout_s: float) -> PluginHooks | None:
    """Hooks that run the harness's plugins, or None if it has none. Plugin code
    reaches the sandbox with each call, so it never sits in the workspace where
    the agent could edit it."""
    sources = {Path(path).stem: text for path, text in harness.files.items() if PLUGIN_FILE.fullmatch(path)}
    defined = {name: frozenset(n.name for n in ast.parse(text).body
                               if isinstance(n, ast.FunctionDef) and n.name in PLUGIN_HOOKS)
               for name, text in sources.items()}
    return PluginHooks(sandbox, sources, defined, workspace, baseline, timeout_s) if sources else None


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
    except SandboxError:
        raise  # our infrastructure failed: the rollout is void, and the model is not to blame
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

def _digests(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def changed_files(workspace: Path, baseline: Mapping[str, str]) -> list[str]:
    """Files the agent created or changed since `baseline`: what it produced,
    wherever the task asked for it (WorkBuddy captures a git diff the same way)."""
    return [path for path, digest in _digests(workspace).items() if baseline.get(path) != digest]


def prepare_workspace(workspace: Path, files_dir: Path, harness: Harness) -> dict[str, str]:
    """A fresh workspace: the task's files at their own paths (where they are is
    up to the benchmark, and its reference instructions say so), plus the
    harness's scripts at theirs, so text that names them is right. Skill bodies
    and plugins stay out: they reach the agent only through tools and hooks.
    Returns the starting state, to tell later what the agent produced."""
    if workspace.exists() and any(workspace.iterdir()):
        raise FileExistsError(f"{workspace} is not empty; every rollout starts fresh")
    shutil.copytree(files_dir, workspace, dirs_exist_ok=True)
    for path, text in harness.files.items():
        if SCRIPT_FILE.fullmatch(path) or SKILL_SCRIPT.fullmatch(path):
            (workspace / path).parent.mkdir(parents=True, exist_ok=True)
            (workspace / path).write_text(text, encoding="utf-8")
    return _digests(workspace)


def execute(llm: LLM, sandbox: Sandbox, harness: Harness, task: str, files_dir: Path, workspace: Path,
            limits: RolloutLimits, *, label: str) -> ExecutionRecord:
    """Run the agent once on a task and record what it did and produced."""
    if errors := validate(harness):
        raise ValueError("refusing to run an invalid harness: " + "; ".join(errors))
    baseline = prepare_workspace(workspace, files_dir, harness)
    tools = [*file_tools(workspace, workspace), run_python_tool(sandbox, workspace, limits.tool_timeout_s)]
    tools += [t for t in (skill_tool(harness), subagent_tool(llm, sandbox, harness, workspace, limits)) if t]
    hooks = plugin_hooks(harness, sandbox, workspace, baseline, limits.tool_timeout_s)
    result = run_agent_loop(llm, "executor", harness.always_on_text(), task, tools,
                            max_turns=limits.max_turns, hooks=hooks)
    deliverable = {path: (workspace / path).read_text(encoding="utf-8", errors="replace")
                   for path in changed_files(workspace, baseline)}
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
    files = "\n".join(f"- {p} ({len(t)} chars)" for p, t in record.deliverable.items()) or "- (none)"
    return f"{head}\n\nDeliverable:\n{files}\n\n## Trajectory\n\n{render_trajectory(record.steps)}"
