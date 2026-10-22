"""Bugs to plant in steps/s04_propose.py, each with the test that must catch it.

Run with: python -m tools.mutate tests/mutations/s04_propose.py
"""

MUTATIONS = [
    {
        "label": "an editor may write anywhere in its session",
        "file": "steps/s04_propose.py",
        "replace": [("return [*file_tools(session, harness_dir),", "return [*file_tools(session, session),")],
        "expect": "test_an_editor_sees_the_evidence_and_edits_only_its_copy",
    },
    {
        "label": "an editor may delete the evidence",
        "file": "steps/s04_propose.py",
        "replace": [("if not path.is_relative_to(harness_dir.resolve()):", "if False:")],
        "expect": "test_an_editor_sees_the_evidence_and_edits_only_its_copy",
    },
    {
        "label": "the run's deliverable never reaches the editor",
        "file": "steps/s04_propose.py",
        "replace": [("for path, text in record.deliverable.items():", "for path, text in {}.items():")],
        "expect": "test_an_editor_sees_the_evidence_and_edits_only_its_copy",
    },
    {
        "label": "an invalid tree is never sent back",
        "file": "steps/s04_propose.py",
        "replace": [("if self._sent_back or not problems:", "if True:")],
        "expect": "test_an_invalid_tree_goes_back_to_its_editor_once",
    },
    {
        "label": "the first notes are kept, not the last",
        "file": "steps/s04_propose.py",
        "replace": [("for s in reversed(result.steps)", "for s in result.steps")],
        "expect": "test_an_invalid_tree_goes_back_to_its_editor_once",
    },
    {
        "label": "an editor is sent back without limit",
        "file": "steps/s04_propose.py",
        "replace": [("self._sent_back = True", "self._sent_back = False")],
        "expect": "test_a_proposal_still_invalid_or_unfinished_falls_back_to_the_start",
    },
    {
        "label": "an invalid tree is kept",
        "file": "steps/s04_propose.py",
        "replace": [("elif problems := validate(proposed):", "elif problems := []:")],
        "expect": "test_a_proposal_still_invalid_or_unfinished_falls_back_to_the_start",
    },
    {
        "label": "an unfinished session's tree is kept",
        "file": "steps/s04_propose.py",
        "replace": [('if result.stop_reason != "end_turn":', "if False:")],
        "expect": "test_a_proposal_still_invalid_or_unfinished_falls_back_to_the_start",
    },
    {
        "label": "both editors get the INV mission",
        "file": "steps/s04_propose.py",
        "replace": [('(prompts_dir / f"editor_{scope}.md")', '(prompts_dir / "editor_inv.md")')],
        "expect": "test_each_editor_gets_its_own_dimension",
    },
    {
        "label": "files off the editable surface vanish unrecorded",
        "file": "steps/s04_propose.py",
        "replace": [('return Candidate(label, proposed, notes, "", tuple(dropped), result.steps)',
                     'return Candidate(label, proposed, notes, "", (), result.steps)')],
        "expect": "test_an_editor_sees_the_evidence_and_edits_only_its_copy",
    },
    {
        "label": "copy_file may write outside the harness",
        "file": "steps/s04_propose.py",
        "replace": [('editable(inp["target"])', 'resolve_inside(session, inp["target"])')],
        "expect": "test_the_composer_sees_every_candidate_with_its_run_and_copies_exactly",
    },
]
