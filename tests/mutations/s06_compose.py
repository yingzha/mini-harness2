"""Bugs to plant in steps/s06_compose.py, each with the test that must catch it.

Run with: python -m tools.mutate tests/mutations/s06_compose.py
"""

MUTATIONS = [
    {
        "label": "the composer never sees how a probe compares with the reference",
        "file": "steps/s06_compose.py",
        "replace": [("for ref in refs:", "for ref in ():")],
        "expect": "test_the_composer_sees_every_candidate_with_its_run_and_copies_exactly",
    },
    {
        "label": "the composer never sees a candidate's diff",
        "file": "steps/s06_compose.py",
        "replace": [('(folder / "diff.patch").write_text(diff(harness, c.harness)', '(folder / "diff.patch").write_text(""')],
        "expect": "test_the_composer_sees_every_candidate_with_its_run_and_copies_exactly",
    },
    {
        "label": "a candidate that fell back looks like a proposal",
        "file": "steps/s06_compose.py",
        "replace": [('fell_back = f"This candidate fell back', 'fell_back = "" and f"This candidate fell back')],
        "expect": "test_the_composer_sees_every_candidate_with_its_run_and_copies_exactly",
    },
    {
        "label": "the composer runs as an editor",
        "file": "steps/s06_compose.py",
        "replace": [('edit_session(llm, "composer",', 'edit_session(llm, "editor",')],
        "expect": "test_the_composer_sees_every_candidate_with_its_run_and_copies_exactly",
    },
    {
        "label": "the successor run uses the current harness, not H′",
        "file": "steps/s06_compose.py",
        "replace": [("probe(llm, sandbox, {c.label: c.harness for c in composed}", "probe(llm, sandbox, {c.label: harness for c in composed}")],
        "expect": "test_a_contrastive_step_runs_the_harness_it_composed",
    },
    {
        "label": "a candidate is left unprobed",
        "file": "steps/s06_compose.py",
        "replace": [("{c.label: c.harness for c in candidates}", "{c.label: c.harness for c in candidates[:1]}")],
        "expect": "test_a_contrastive_step_runs_the_harness_it_composed",
    },
    {
        "label": "the composer is not given the editors' rules",
        "file": "steps/s06_compose.py",
        "replace": [("return template.format(rules=rules.strip(), j=j, k=k)", 'return template.format(rules="", j=j, k=k)')],
        "expect": "test_the_composer_is_bound_by_the_editors_rules",
    },
    {
        "label": "the composer never sees the editors' reasons",
        "file": "steps/s06_compose.py",
        "replace": [('write_text(fell_back + (c.notes or "(no notes)")', 'write_text(fell_back + "(no notes)"')],
        "expect": "test_the_composer_sees_every_candidate_with_its_run_and_copies_exactly",
    },
    {
        "label": "every editor is told it is candidate 1 of 1",
        "file": "steps/s06_compose.py",
        "replace": [("editor_prompt(prompts_dir, scope, i, k)", "editor_prompt(prompts_dir, scope, 1, 1)")],
        "expect": "test_parallel_recursion_adopts_the_harness_whose_output_is_delivered",
    },
    {
        "label": "every composer is told it is composer 1",
        "file": "steps/s06_compose.py",
        "replace": [("composer_prompt(prompts_dir, j, k)", "composer_prompt(prompts_dir, 1, k)")],
        "expect": "test_parallel_recursion_adopts_the_harness_whose_output_is_delivered",
    },
]
