"""Lesson 1 tests. Each docstring names the real failure the test guards against."""

import pytest

import config
from steps.s01_harness import Harness, diff, load_harness, validate, write_harness

H0, H0_LEFT_OUT = load_harness(config.BASE_HARNESS_DIR)

SKILL = "---\ndescription: Reconcile two tables.\n---\nJoin on the normalised key."
TRIGGER = "\nWhen two files must be joined, load the `recon` skill.\n"


def edit(base: Harness, changes: dict[str, str | None]) -> Harness:
    """Copy of `base` with files set (str) or removed (None)."""
    files = dict(base.files)
    for path, text in changes.items():
        if text is None:
            files.pop(path, None)
        else:
            files[path] = text
    return Harness(files)


def test_base_harness_is_valid():
    """Guards: shipping a broken H0. Every task starts from it, so one bad
    file there breaks every rollout of every task."""
    assert H0_LEFT_OUT == []
    assert validate(H0) == []


def test_skill_needs_a_trigger_line_in_system_prompt_or_guardrails():
    """Guards: a skill the agent will never load, because nothing it reads on
    every call says when to load it (Prompt 1, discard rule 1)."""
    no_trigger = edit(H0, {"skills/recon/SKILL.md": SKILL})
    assert any("no trigger line" in e for e in validate(no_trigger))

    in_memory_only = edit(no_trigger, {"LongTermMEMORY.md": TRIGGER})
    assert any("no trigger line" in e for e in validate(in_memory_only)), \
        "the trigger must be in systemprompt.md or guardrails.md"

    in_guardrails = edit(no_trigger, {"guardrails.md": TRIGGER})
    assert validate(in_guardrails) == []


def test_trigger_line_must_name_a_skill_that_exists():
    """Guards: always-on text telling the agent to load a skill that isn't
    there, so it wastes a turn on a failed load_skill or assumes a procedure
    that doesn't exist. Typical cause: a composer keeps one candidate's
    guardrails edit but drops the skill that came with it."""
    ghost = edit(H0, {"guardrails.md": "When a CSV has money strings, load the `ghost` skill.\n"})
    assert validate(ghost) == ["guardrails.md says to load the `ghost` skill, which is not in the harness"]

    complete = edit(H0, {"guardrails.md": TRIGGER, "skills/recon/SKILL.md": SKILL})
    skill_dropped = edit(complete, {"skills/recon/SKILL.md": None})
    assert validate(skill_dropped) == ["guardrails.md says to load the `recon` skill, which is not in the harness"]

    # The runtime finds skills by exact folder name, so `Recon` won't load `recon`.
    wrong_case = edit(complete, {"guardrails.md": TRIGGER.replace("`recon`", "`Recon`")})
    assert sorted(validate(wrong_case)) == [
        "guardrails.md says to load the `Recon` skill, which is not in the harness",
        'skills/recon/SKILL.md: no trigger line. Add to systemprompt.md or guardrails.md: '
        '"When <situation>, load the `recon` skill."',
    ]
    assert validate(edit(complete, {"guardrails.md": TRIGGER.replace("load the", "Load The")})) == [], \
        "the surrounding words may be in any case"


def test_skills_and_subagents_need_a_description():
    """Guards: a load_skill / run_subagent listing entry the agent can't
    interpret, so it never knows when to use it."""
    h = edit(H0, {
        "guardrails.md": TRIGGER,
        "skills/recon/SKILL.md": "Join on the normalised key.",          # no frontmatter
        "sub_agents/reader/AGENT.md": "---\nmode: subagent\n---\nRead.",  # frontmatter, no description
    })
    errors = validate(h)
    assert any(e.startswith("skills/recon/SKILL.md: frontmatter needs a `description`") for e in errors)
    assert any(e.startswith("sub_agents/reader/AGENT.md: frontmatter needs a `description`") for e in errors)


def test_every_script_the_text_names_must_ship():
    """Guards: the agent told to run a script that doesn't exist (Prompt 1,
    discard rule 3). Paths resolve from the workspace root, so a skill naming
    `scripts/x.py` while shipping only `skills/<s>/scripts/x.py` is broken too."""
    base = edit(H0, {"guardrails.md": TRIGGER, "skills/recon/SKILL.md": SKILL})

    missing = edit(base, {"systemprompt.md": "Always run scripts/check.py first."})
    assert validate(missing) == ["systemprompt.md names scripts/check.py, which is not in the harness"]
    assert validate(edit(missing, {"scripts/check.py": "print('ok')"})) == []

    wrong_dir = edit(base, {
        "skills/recon/SKILL.md": SKILL + "\nRun scripts/merge.py.",
        "skills/recon/scripts/merge.py": "print('merge')",
    })
    assert validate(wrong_dir) == ["skills/recon/SKILL.md names scripts/merge.py, which is not in the harness"]

    other_folder = edit(base, {"systemprompt.md": "Inputs may include source/scripts/legacy.py."})
    assert validate(other_folder) == [], "a path under another folder is not a harness script"


def test_code_must_compile_and_plugins_must_define_a_hook():
    """Guards: a script that crashes on first run, and a plugin whose hook name
    is misspelt, which would load fine and then silently never fire."""
    h = edit(H0, {
        "scripts/bad.py": "def f(:\n",
        "scripts/return_outside.py": "return 1\n",   # parses as a tree, fails to compile
        "plugin/typo.py": "def after_tools(event):\n    return None\n",
        "plugin/ok.py": "def after_tool(event):\n    return None\n",
    })
    errors = validate(h)
    assert any(e.startswith("scripts/bad.py does not compile: line 1") for e in errors)
    assert any(e.startswith("scripts/return_outside.py does not compile") for e in errors)
    assert any(e.startswith("plugin/typo.py defines none of the plugin hooks") for e in errors)
    assert not any(e.startswith("plugin/ok.py") for e in errors)


def test_constructor_rejects_paths_off_the_surface():
    """Guards: a path that escapes the harness directory when written to disk."""
    for bad in ["../evil.py", "scripts/../../evil.py", "notes.txt", "skills/recon/check.py"]:
        with pytest.raises(ValueError):
            Harness({bad: ""})


def test_equal_harnesses_are_interchangeable_as_set_members():
    """Guards: de-duplicating identical candidate harnesses (e.g. two composers
    landing on the same tree) crashing with TypeError, or treating copies as
    different and paying for the same rollout twice."""
    copy = Harness(dict(H0.files))
    changed = Harness({**H0.files, "guardrails.md": "Inputs are read-only."})
    assert len({H0, copy}) == 1
    assert len({H0, changed}) == 2


def test_load_refuses_a_missing_directory(tmp_path):
    """Guards: a mistyped harness path silently loading as an empty harness,
    which even passes validation, so every run goes ahead with no system prompt."""
    with pytest.raises(FileNotFoundError):
        load_harness(tmp_path / "base_harnes")


def test_load_leaves_out_stray_files_and_symlinks(tmp_path):
    """Guards: a helper dropped loose in a skill folder, or a symlink to a file
    outside the workspace, silently becoming part of the harness."""
    write_harness(H0, tmp_path)
    (tmp_path / "skills" / "recon").mkdir()
    (tmp_path / "skills" / "recon" / "check.py").write_text("print('loose')")  # not under scripts/
    (tmp_path / "notes.txt").write_text("scratch")
    (tmp_path / "scripts" / "link.py").symlink_to("/etc/hosts")

    loaded, left_out = load_harness(tmp_path)
    assert loaded == H0
    assert sorted(left_out) == ["notes.txt", "scripts/link.py", "skills/recon/check.py"]


def test_write_then_load_round_trips_exactly(tmp_path):
    """Guards: an editor's edits altered or lost between disk and the next
    rollout, and stale files from an older harness merging into a new one."""
    h = edit(H0, {
        "systemprompt.md": "No trailing newline, unicode: café → ✓",
        "scripts/empty.py": "",
    })
    write_harness(h, tmp_path / "h")
    assert load_harness(tmp_path / "h") == (h, [])

    with pytest.raises(FileExistsError):
        write_harness(H0, tmp_path / "h")


def test_diff_shows_every_kind_of_change():
    """Guards: the composer or reflector reading an incomplete diff, e.g. a
    deleted component that is silently missing from the evidence."""
    new = edit(H0, {
        "guardrails.md": None,                                   # removed (and empty)
        "scripts/empty.py": "",                                 # added, empty
        "systemprompt.md": "Rewritten, no trailing newline",     # changed
    })
    d = diff(H0, new)
    assert "--- a/guardrails.md\n+++ /dev/null\n" in d
    assert "--- /dev/null\n+++ b/scripts/empty.py\n" in d
    assert "+Rewritten, no trailing newline\n" in d
    assert diff(H0, H0) == ""


def test_always_on_text_excludes_on_demand_components():
    """Guards: skills, subagents or placeholders leaking into every call. That
    costs context on every run, which Prompt 1 calls the most costly failure."""
    h = edit(H0, {
        "systemprompt.md": "SYSTEM",
        "guardrails.md": "GUARD" + TRIGGER,
        "LongTermMEMORY.md": "MEMORY",
        "tool_descriptions/tool_guidance.md": "TOOLS",
        "skills/recon/SKILL.md": SKILL,
        "sub_agents/reader/AGENT.md": "---\ndescription: Reads.\n---\nSUBAGENT BODY",
    })
    text = h.always_on_text()
    assert text.index("SYSTEM") < text.index("GUARD") < text.index("MEMORY") < text.index("TOOLS")
    for leaked in ["Join on the normalised key", "SUBAGENT BODY", "Skills (C6)"]:
        assert leaked not in text
