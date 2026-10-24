"""Bugs to plant in benchmarks/workbuddy.py, each with the test that must catch it.

Run with: python -m tools.mutate tests/mutations/workbuddy.py
A control (expect=None) changes nothing observable, so no test may fail for it.
"""

MUTATIONS = [
    {
        "label": "workspace also mounted where their glue looks first",
        "file": "benchmarks/workbuddy.py",
        "replace": [
            ('"/workspace": Path(reply)}', '"/workspace": workspace}'),
        ],
        "expect": "test_an_agent_cannot_grade_itself",
    },
    {
        "label": "deliverable path not redirected",
        "file": "benchmarks/workbuddy.py",
        "replace": [
            ("    if default:\n",
             "    if False:\n"),
        ],
        "expect": "test_its_own_checks_grade_the_workspace",
    },
    {
        "label": "the bare /workspace not taken as a deliverable path",
        "file": "benchmarks/workbuddy.py",
        "replace": [
            ("""/workspace(/[^"']*)?["']""",
             """/workspace(/[^"']+)["']"""),
        ],
        "expect": "test_checks_find_the_deliverable_however_the_task_names_it[whole-workspace]",
    },
    {
        "label": "a DEFAULT_OUTPUT_PATH constant not read",
        "file": "benchmarks/workbuddy.py",
        "replace": [
            ("""|DEFAULT_OUTPUT_PATH\\s*=\\s*)""",
             """)"""),
        ],
        "expect": "test_checks_find_the_deliverable_however_the_task_names_it[module-constant]",
    },
    {
        "label": "check list cut at the tool-output size",
        "file": "benchmarks/workbuddy.py",
        "replace": [
            ("max_output=2_000_000)",
             ")"),
        ],
        "expect": "test_its_own_checks_grade_the_workspace",
    },
    {
        "label": "the whole task folder handed over",
        "file": "benchmarks/workbuddy.py",
        "replace": [
            ("if m.isfile()}",
             "if m.isfile()} | {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob('*') if p.is_file()}"),
        ],
        "expect": "test_a_task_is_its_request_and_starting_files_only",
    },
    {
        "label": "the final reply not given to the checks",
        "file": "benchmarks/workbuddy.py",
        "replace": [('(Path(reply) / "final_answer.md").write_text(final_reply, encoding="utf-8")',
                     '(Path(reply) / "final_answer.md").write_text("", encoding="utf-8")')],
        "expect": "test_checks_see_the_agents_final_reply",
    },
    {
        "label": "verifier.toml's /workspace paths passed through",
        "file": "benchmarks/workbuddy.py",
        "replace": [("_moved(str(value))", "str(value)")],
        "expect": "test_checks_find_the_deliverable_however_the_task_names_it[verifier-only]",
    },
    {
        "label": "a deliverable in an unknown form graded silently",
        "file": "benchmarks/workbuddy.py",
        "replace": [('if "WB_BENCH_OUTPUT_PATH" not in env and "WB_BENCH_OUTPUT_PATH" in verify:', "if False:")],
        "expect": "test_a_deliverable_named_in_an_unknown_form_is_an_error",
    },
]
