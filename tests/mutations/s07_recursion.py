"""Bugs to plant in steps/s07_recursion.py, each with the test that must catch it.

Run with: python -m tools.mutate tests/mutations/s07_recursion.py
"""

MUTATIONS = [
    {
        "label": "ids follow the runs' order instead of a shuffle",
        "file": "steps/s07_recursion.py",
        "replace": [("enumerate(rng.sample(labels, len(labels)), 1)", "enumerate(labels, 1)")],
        "expect": "test_the_selector_sees_only_artifacts_and_its_choice_maps_back",
    },
    {
        "label": "an output shows which run made it",
        "file": "steps/s07_recursion.py",
        "replace": [(".write_text(_render(outputs[label])", '.write_text(f"{label}\\n" + _render(outputs[label])')],
        "expect": "test_the_selector_sees_only_artifacts_and_its_choice_maps_back",
    },
    {
        "label": "the selector can change the outputs it judges",
        "file": "steps/s07_recursion.py",
        "replace": [('if t.name != "write_file"]', "if True]")],
        "expect": "test_the_selector_sees_only_artifacts_and_its_choice_maps_back",
    },
    {
        "label": "the choice maps back to the wrong run",
        "file": "steps/s07_recursion.py",
        "replace": [('return Selection(ids[chosen], ids, why, "", result.steps)',
                     'return Selection(ids["c1"], ids, why, "", result.steps)')],
        "expect": "test_the_selector_sees_only_artifacts_and_its_choice_maps_back",
    },
    {
        "label": "an unreadable choice is never sent back",
        "file": "steps/s07_recursion.py",
        "replace": [("hooks=SendBackOnce(unreadable))", "hooks=None)")],
        "expect": "test_an_unreadable_choice_goes_back_once_then_falls_back_to_the_first",
    },
    {
        "label": "the fallback takes an arbitrary run",
        "file": "steps/s07_recursion.py",
        "replace": [("first = next(iter(outputs))", "first = list(outputs)[-1]")],
        "expect": "test_an_unreadable_choice_goes_back_once_then_falls_back_to_the_first",
    },
    {
        "label": "the base runs are left out of the pool",
        "file": "steps/s07_recursion.py",
        "replace": [("outputs = {**base, **step.successors}", "outputs = dict(step.successors)")],
        "expect": "test_parallel_recursion_adopts_the_harness_whose_output_is_delivered",
    },
    {
        "label": "H★ is not the harness that produced the chosen output",
        "file": "steps/s07_recursion.py",
        "replace": [("return Recursion(step, selection.chosen, produced_by[selection.chosen], selection)",
                     "return Recursion(step, selection.chosen, harness, selection)")],
        "expect": "test_parallel_recursion_adopts_the_harness_whose_output_is_delivered",
    },
    {
        "label": "k = 1 still runs a selection",
        "file": "steps/s07_recursion.py",
        "replace": [("    if k == 1:\n", "    if False:\n")],
        "expect": "test_at_k_1_the_composed_harness_is_adopted_without_selection",
    },
    {
        "label": "the selector is told which of {n}, unfilled",
        "file": "steps/s07_recursion.py",
        "replace": [('.read_text(encoding="utf-8").format(n=n)', '.read_text(encoding="utf-8")')],
        "expect": "test_parallel_recursion_adopts_the_harness_whose_output_is_delivered",
    },
]
