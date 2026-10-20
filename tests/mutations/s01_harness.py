"""Bugs to plant in steps/s01_harness.py, each with the test that must catch it.

Run with: python -m tools.mutate tests/mutations/s01_harness.py
A control (expect=None) changes nothing observable, so no test may fail for it.
"""

MUTATIONS = [
    {
        "label": "trigger read from any always-on file",
        "file": "steps/s01_harness.py",
        "replace": [
            ("for path in TRIGGER_FILES:",
             "for path in ALWAYS_ON:"),
        ],
        "expect": "test_skill_needs_a_trigger_line_in_system_prompt_or_guardrails",
    },
    {
        "label": "dangling trigger not reported",
        "file": "steps/s01_harness.py",
        "replace": [
            ("if name not in skills:",
             "if False:"),
        ],
        "expect": "test_trigger_line_must_name_a_skill_that_exists",
    },
    {
        "label": "missing trigger not reported",
        "file": "steps/s01_harness.py",
        "replace": [
            ("if name not in triggered:",
             "if False:"),
        ],
        "expect": "test_skill_needs_a_trigger_line_in_system_prompt_or_guardrails",
    },
    {
        "label": "skill names compared case-insensitively",
        "file": "steps/s01_harness.py",
        "replace": [
            ("triggered.add(name)",
             "triggered.add(name.lower())"),
            ("if name not in skills:",
             "if name.lower() not in {s.lower() for s in skills}:"),
        ],
        "expect": "test_trigger_line_must_name_a_skill_that_exists",
    },
    {
        "label": "trigger words case-sensitive",
        "file": "steps/s01_harness.py",
        "replace": [
            ("(?i:load the) `({_NAME})` (?i:skill)",
             "load the `({_NAME})` skill"),
        ],
        "expect": "test_trigger_line_must_name_a_skill_that_exists",
    },
    {
        "label": "description never required",
        "file": "steps/s01_harness.py",
        "replace": [
            ("if not d.meta.get(\"description\")]",
             "if False]"),
        ],
        "expect": "test_skills_and_subagents_need_a_description",
    },
    {
        "label": "subagents skip description check",
        "file": "steps/s01_harness.py",
        "replace": [
            ("documents = [*harness.skills().values(), *harness.subagents().values()]",
             "documents = [*harness.skills().values()]"),
        ],
        "expect": "test_skills_and_subagents_need_a_description",
    },
    {
        "label": "script-ref lookbehind removed",
        "file": "steps/s01_harness.py",
        "replace": [
            ("(?<![\\w/.-])(?:skills",
             "(?:skills"),
        ],
        "expect": "test_every_script_the_text_names_must_ship",
    },
    {
        "label": "missing scripts not reported",
        "file": "steps/s01_harness.py",
        "replace": [
            ("if ref not in harness.files:",
             "if False:"),
        ],
        "expect": "test_every_script_the_text_names_must_ship",
    },
    {
        "label": "SKILL.md not scanned for scripts",
        "file": "steps/s01_harness.py",
        "replace": [
            ("if path in ALWAYS_ON or SKILL_FILE.fullmatch(path) or AGENT_FILE.fullmatch(path):",
             "if path in ALWAYS_ON:"),
        ],
        "expect": "test_every_script_the_text_names_must_ship",
    },
    {
        "label": "ast.parse instead of compile",
        "file": "steps/s01_harness.py",
        "replace": [
            ("compile(text, path, \"exec\")",
             "ast.parse(text)"),
        ],
        "expect": "test_code_must_compile_and_plugins_must_define_a_hook",
    },
    {
        "label": "plugin hook check removed",
        "file": "steps/s01_harness.py",
        "replace": [
            ("if not defined & set(PLUGIN_HOOKS):",
             "if False:"),
        ],
        "expect": "test_code_must_compile_and_plugins_must_define_a_hook",
    },
    {
        "label": "constructor accepts any path",
        "file": "steps/s01_harness.py",
        "replace": [
            ("if off_surface:",
             "if False:"),
        ],
        "expect": "test_constructor_rejects_paths_off_the_surface",
    },
    {
        "label": "load follows symlinks",
        "file": "steps/s01_harness.py",
        "replace": [
            ("if p.is_symlink():",
             "if False:"),
        ],
        "expect": "test_load_leaves_out_stray_files_and_symlinks",
    },
    {
        "label": "load keeps off-surface files",
        "file": "steps/s01_harness.py",
        "replace": [
            ("if is_on_surface(rel):",
             "if True:"),
        ],
        "expect": "test_load_leaves_out_stray_files_and_symlinks",
    },
    {
        "label": "missing dir loads as empty harness",
        "file": "steps/s01_harness.py",
        "replace": [
            ("if not root.is_dir():",
             "if False:"),
        ],
        "expect": "test_load_refuses_a_missing_directory",
    },
    {
        "label": "write into non-empty dir",
        "file": "steps/s01_harness.py",
        "replace": [
            ("if root.exists() and any(root.iterdir()):",
             "if False:"),
        ],
        "expect": "test_write_then_load_round_trips_exactly",
    },
    {
        "label": "diff hides empty add/remove",
        "file": "steps/s01_harness.py",
        "replace": [
            ("if a == b:",
             "if (a or \"\") == (b or \"\"):"),
        ],
        "expect": "test_diff_shows_every_kind_of_change",
    },
    {
        "label": "always-on includes every file",
        "file": "steps/s01_harness.py",
        "replace": [
            ("for p in ALWAYS_ON if",
             "for p in sorted(self.files) if"),
        ],
        "expect": "test_always_on_text_excludes_on_demand_components",
    },
    {
        "label": "hash by identity",
        "file": "steps/s01_harness.py",
        "replace": [
            ("return hash(frozenset(self.files.items()))",
             "return id(self)"),
        ],
        "expect": "test_equal_harnesses_are_interchangeable_as_set_members",
    },
    {
        "label": "hash method deleted (dataclass default)",
        "file": "steps/s01_harness.py",
        "replace": [
            ("    def __hash__(self) -> int:\n        # Equal harnesses must hash equal, e.g. to de-duplicate candidates.\n        return hash(frozenset(self.files.items()))\n\n",
             ""),
        ],
        "expect": "test_equal_harnesses_are_interchangeable_as_set_members",
    },
    {
        "label": "equivalent: whole regex (?i)",
        "file": "steps/s01_harness.py",
        "replace": [
            ("(?i:load the) `({_NAME})` (?i:skill)",
             "(?i)load the `({_NAME})` skill"),
        ],
        "expect": None,
    },
]
