"""Bugs to plant in steps/s08_library.py, each with the test that must catch it.

Run with: python -m tools.mutate tests/mutations/s08_library.py
"""

MUTATIONS = [
    {
        "label": "the reflector sees only the adopted harness, not every candidate",
        "file": "steps/s08_library.py",
        "replace": [("    for c in step.candidates:\n", "    for c in ():\n")],
        "expect": "test_the_reflector_reads_every_candidate_and_what_was_submitted",
    },
    {
        "label": "the reflector never sees the composers' decisions",
        "file": "steps/s08_library.py",
        "replace": [("    for c in step.composed:\n", "    for c in ():\n")],
        "expect": "test_the_reflector_reads_every_candidate_and_what_was_submitted",
    },
    {
        "label": "the reflector doesn't know what was submitted",
        "file": "steps/s08_library.py",
        "replace": [('(context / "selection.md").write_text(_submitted(recursion)', '(context / "selection.md").write_text(""')],
        "expect": "test_the_reflector_reads_every_candidate_and_what_was_submitted",
    },
    {
        "label": "a reply without edit rows is never sent back",
        "file": "steps/s08_library.py",
        "replace": [("hooks=SendBackOnce(no_rows))", "hooks=None)")],
        "expect": "test_the_reflector_reads_every_candidate_and_what_was_submitted",
    },
    {
        "label": "NO_ENTRY is recorded as a lesson",
        "file": "steps/s08_library.py",
        "replace": [('experience = m[1].strip() if (m := _EXPERIENCE.search(result.final_text)) else ""',
                     "experience = m[1].strip() if (m := _EXPERIENCE.search(result.final_text)) else result.final_text")],
        "expect": "test_the_reflector_reads_every_candidate_and_what_was_submitted",
    },
    {
        "label": "the reflector can write",
        "file": "steps/s08_library.py",
        "replace": [('if t.name != "write_file"]   # it only reads', "if True]")],
        "expect": "test_the_reflector_reads_every_candidate_and_what_was_submitted",
    },
    {
        "label": "the library keeps the base tree instead of H*",
        "file": "steps/s08_library.py",
        "replace": [('write_harness(adopted, entry / "harness")', 'write_harness(base, entry / "harness")')],
        "expect": "test_the_library_keeps_the_adopted_tree_and_its_lesson",
    },
    {
        "label": "a task that adopted H0 and taught nothing gets an entry",
        "file": "steps/s08_library.py",
        "replace": [("if adopted == base and not reflection.experience:", "if False:")],
        "expect": "test_the_library_keeps_the_adopted_tree_and_its_lesson",
    },
    {
        "label": "the index leaves out the lesson's cue",
        "file": "steps/s08_library.py",
        "replace": [('cue = m[1].strip() if (m := _CUE.search(reflection.experience)) else "no lesson"', 'cue = "no lesson"')],
        "expect": "test_the_library_keeps_the_adopted_tree_and_its_lesson",
    },
    {
        "label": "editors never see the library",
        "file": "steps/s04_propose.py",
        "replace": [('        shutil.copytree(library, context / "library")\n', '        (context / "library").mkdir()\n')],
        "expect": "test_editors_read_the_library_but_cannot_change_it",
    },
]
