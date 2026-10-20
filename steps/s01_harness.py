"""Lesson 1: The harness H = (c¹, …, c⁸).

Paper anchors
-------------
* §2.1: "A harness H = (c¹, …, cᴷ) consists of K editable components … It
  composes with M to form an agent A(·; M, H) without changing its weights."
  Here K = 8.
* Table 5 / Fig. 2: the eight components. "Each is a file, so an edit is a
  diff; activation states when a component reaches the model."
* §D.1: the stock harness H₀. Always-on files hold only the environment's
  instructions; each on-demand directory holds a placeholder that names the
  lever, which is how an editor discovers that the component exists.
* §D.2 and Prompt 1: an edited harness is validated before any rollout. A tree
  that breaks a rule is sent back to its editor once, then discarded.

Design
------
A harness is an immutable value: a mapping from relative path to file text.
Every path must be on the *editable surface* (one of the eight components or a
placeholder), which also rules out path tricks like `../`. Everything except
`load_harness` and `write_harness` is a pure function of that value.
"""

from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

# ---------------------------------------------------------------------------
# The file layout, defined once
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = "systemprompt.md"
GUARDRAILS = "guardrails.md"
MEMORY = "LongTermMEMORY.md"
TOOL_GUIDANCE = "tool_descriptions/tool_guidance.md"

_NAME = r"[A-Za-z0-9_-]+"
SKILL_FILE = re.compile(rf"skills/(?P<name>{_NAME})/SKILL\.md")
SKILL_SCRIPT = re.compile(rf"skills/{_NAME}/scripts/{_NAME}\.py")
AGENT_FILE = re.compile(rf"sub_agents/(?P<name>{_NAME})/AGENT\.md")
SCRIPT_FILE = re.compile(rf"scripts/{_NAME}\.py")
PLUGIN_FILE = re.compile(rf"plugin/{_NAME}\.py")
PLACEHOLDER = re.compile(r"(skills|scripts|sub_agents|plugin)/README\.md")

ALWAYS_ON = (SYSTEM_PROMPT, GUARDRAILS, MEMORY, TOOL_GUIDANCE)  # Table 5 order
TRIGGER_FILES = (SYSTEM_PROMPT, GUARDRAILS)  # where a skill's trigger line must live
PLUGIN_HOOKS = ("after_tool", "before_finish")         # the hooks the executor calls (Lesson 2)

# A skill's trigger line: "When <situation>, load the `<name>` skill." The words
# may be in any case; the name must match exactly, because the runtime finds a
# skill by its folder name.
_TRIGGER = re.compile(rf"(?i:load the) `({_NAME})` (?i:skill)")

# A script path as written in prose: scripts/x.py or skills/<skill>/scripts/x.py
_SCRIPT_REF = re.compile(rf"(?<![\w/.-])(?:skills/{_NAME}/)?scripts/{_NAME}\.py")


# ---------------------------------------------------------------------------
# The eight components (Table 5)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Component:
    id: str            # C1..C8, as in Table 5
    name: str
    activation: str    # when it reaches the model
    pattern: re.Pattern[str]


def _exactly(path: str) -> re.Pattern[str]:
    return re.compile(re.escape(path))


COMPONENTS = (
    Component("C1", "system prompt", "every call", _exactly(SYSTEM_PROMPT)),
    Component("C2", "guardrails", "every call", _exactly(GUARDRAILS)),
    Component("C3", "memory", "every call", _exactly(MEMORY)),
    Component("C4", "tool guidance", "every call", _exactly(TOOL_GUIDANCE)),
    Component("C5", "subagent", "run_subagent tool", AGENT_FILE),
    Component("C6", "skill", "load_skill tool", re.compile(f"{SKILL_FILE.pattern}|{SKILL_SCRIPT.pattern}")),
    Component("C7", "script", "run_python tool", SCRIPT_FILE),
    Component("C8", "plugin", "inside the tool loop", PLUGIN_FILE),
)


def component_of(path: str) -> Component | None:
    """The component a path belongs to, or None (placeholders and off-surface paths)."""
    return next((c for c in COMPONENTS if c.pattern.fullmatch(path)), None)


def is_on_surface(path: str) -> bool:
    return component_of(path) is not None or PLACEHOLDER.fullmatch(path) is not None


# ---------------------------------------------------------------------------
# The harness value
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Document:
    """A skill (C6) or subagent (C5): a markdown file with frontmatter."""
    name: str                 # its folder name; the runtime looks it up by this
    path: str
    meta: Mapping[str, str]   # frontmatter
    body: str                 # a skill's procedure, or a subagent's system prompt


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split `---\\nkey: value\\n---\\nbody` into (meta, body). No frontmatter gives ({}, text)."""
    match = re.match(r"---\n(.*?)\n---[ \t]*(?:\n|$)", text, re.DOTALL)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta, text[match.end():]


def _documents(files: Mapping[str, str], pattern: re.Pattern[str]) -> dict[str, Document]:
    found = {}
    for path, text in files.items():
        if m := pattern.fullmatch(path):
            meta, body = parse_frontmatter(text)
            found[m["name"]] = Document(m["name"], path, MappingProxyType(meta), body)
    return found


@dataclass(frozen=True)
class Harness:
    files: Mapping[str, str]  # relative POSIX path -> text

    def __post_init__(self) -> None:
        off_surface = sorted(p for p in self.files if not is_on_surface(p))
        if off_surface:
            raise ValueError(f"not on the editable surface: {off_surface}")
        object.__setattr__(self, "files", MappingProxyType(dict(self.files)))

    def __hash__(self) -> int:
        # Equal harnesses must hash equal, e.g. to de-duplicate candidates.
        return hash(frozenset(self.files.items()))

    def always_on_text(self) -> str:
        """C1-C4, in Table 5 order: the text that reaches the model on every call."""
        return "\n\n".join(t.strip() for p in ALWAYS_ON if (t := self.files.get(p, "")).strip())

    def skills(self) -> dict[str, Document]:
        return _documents(self.files, SKILL_FILE)

    def subagents(self) -> dict[str, Document]:
        return _documents(self.files, AGENT_FILE)


# ---------------------------------------------------------------------------
# Validation (§D.2, Prompt 1): run before any rollout. One function per rule,
# each named for what it ensures.
# ---------------------------------------------------------------------------

def validate(harness: Harness) -> list[str]:
    """Every reason this tree would fail at runtime. Empty means valid."""
    return [
        *_skills_and_trigger_lines_pair_up(harness),
        *_on_demand_components_are_described(harness),
        *_named_scripts_ship(harness),
        *_code_compiles_and_plugins_hook_in(harness),
    ]


def _skills_and_trigger_lines_pair_up(harness: Harness) -> list[str]:
    """A skill without a trigger line is never opened. A trigger line without a
    skill sends the agent after something that doesn't exist (e.g. a composer
    kept one candidate's guardrails edit but dropped the skill it introduced)."""
    errors = []
    skills = harness.skills()
    triggered: set[str] = set()
    for path in TRIGGER_FILES:
        for name in sorted(set(_TRIGGER.findall(harness.files.get(path, "")))):
            triggered.add(name)
            if name not in skills:
                errors.append(f"{path} says to load the `{name}` skill, which is not in the harness")
    for name, skill in sorted(skills.items()):
        if name not in triggered:
            errors.append(f"{skill.path}: no trigger line. Add to systemprompt.md or guardrails.md: "
                          f"\"When <situation>, load the `{name}` skill.\"")
    return errors


def _on_demand_components_are_described(harness: Harness) -> list[str]:
    """The agent picks a skill or a subagent from its description alone."""
    documents = [*harness.skills().values(), *harness.subagents().values()]
    return [f"{d.path}: frontmatter needs a `description`"
            for d in sorted(documents, key=lambda d: d.path) if not d.meta.get("description")]


def _named_scripts_ship(harness: Harness) -> list[str]:
    """Text that tells the agent to run a script is only safe if the script exists."""
    errors = []
    for path, text in sorted(harness.files.items()):
        if path in ALWAYS_ON or SKILL_FILE.fullmatch(path) or AGENT_FILE.fullmatch(path):
            for ref in sorted(set(_SCRIPT_REF.findall(text))):
                if ref not in harness.files:
                    errors.append(f"{path} names {ref}, which is not in the harness")
    return errors


def _code_compiles_and_plugins_hook_in(harness: Harness) -> list[str]:
    """A script that doesn't compile crashes on first run; a plugin with no
    known hook (e.g. a misspelt `after_tools`) loads fine and never runs."""
    errors = []
    for path, text in sorted(harness.files.items()):
        if not path.endswith(".py"):
            continue
        try:
            compile(text, path, "exec")
        except SyntaxError as e:
            errors.append(f"{path} does not compile: line {e.lineno}: {e.msg}")
            continue
        if PLUGIN_FILE.fullmatch(path):
            defined = {n.name for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
            if not defined & set(PLUGIN_HOOKS):
                errors.append(f"{path} defines none of the plugin hooks "
                              f"({', '.join(PLUGIN_HOOKS)}), so it would never run")
    return errors


# ---------------------------------------------------------------------------
# Diffs: "each edit is a diff" (Table 5)
# ---------------------------------------------------------------------------

def diff(old: Harness, new: Harness) -> str:
    """A unified diff over the whole tree, including added, removed and empty files."""
    out: list[str] = []
    for path in sorted(old.files.keys() | new.files.keys()):
        a, b = old.files.get(path), new.files.get(path)
        if a == b:
            continue
        out.append(f"--- {'a/' + path if a is not None else '/dev/null'}\n")
        out.append(f"+++ {'b/' + path if b is not None else '/dev/null'}\n")
        body = list(difflib.unified_diff((a or "").splitlines(), (b or "").splitlines(), lineterm=""))
        out.extend(line + "\n" for line in body[2:])  # skip difflib's own ---/+++ header
    return "".join(out)


# ---------------------------------------------------------------------------
# Disk I/O: the only impure part
# ---------------------------------------------------------------------------

def load_harness(root: Path) -> tuple[Harness, list[str]]:
    """Read a harness from a directory. Returns it and the paths left out:
    anything off the editable surface, and symlinks (never followed)."""
    if not root.is_dir():
        # Otherwise a mistyped path yields an empty harness, which even validates.
        raise FileNotFoundError(f"no harness directory at {root}")
    files: dict[str, str] = {}
    left_out: list[str] = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            left_out.append(rel)
        elif p.is_file():
            if is_on_surface(rel):
                files[rel] = p.read_text(encoding="utf-8")
            else:
                left_out.append(rel)
    return Harness(files), left_out


def write_harness(harness: Harness, root: Path) -> None:
    """Write a harness into an empty (or new) directory."""
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"{root} is not empty; a harness must not mix with existing files")
    for rel, text in harness.files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
