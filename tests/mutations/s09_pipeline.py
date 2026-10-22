"""Bugs to plant in steps/s09_pipeline.py, each with the test that must catch it.

Run with: python -m tools.mutate tests/mutations/s09_pipeline.py
"""

MUTATIONS = [
    {
        "label": "each task starts from the previous task's adopted harness",
        "file": "steps/s09_pipeline.py",
        "replace": [("        yield TaskResult(task, recursion, reflection, added)\n",
                     "        yield TaskResult(task, recursion, reflection, added)\n        h0 = recursion.adopted\n")],
        "expect": "test_each_task_starts_from_h0_and_learns_only_through_the_library",
    },
    {
        "label": "each task gets a library of its own",
        "file": "steps/s09_pipeline.py",
        "replace": [("k=k, library=library,", 'k=k, library=folder / task.id / "own-library",')],
        "expect": "test_each_task_starts_from_h0_and_learns_only_through_the_library",
    },
    {
        "label": "the delivered run is not the chosen one",
        "file": "steps/s07_recursion.py",
        "replace": [("for r in [*self.step.refs, *self.step.successors.values()]}[self.chosen]",
                     "for r in [*self.step.refs, *self.step.successors.values()]}[self.step.refs[0].label]")],
        "expect": "test_each_task_starts_from_h0_and_learns_only_through_the_library",
    },
]
