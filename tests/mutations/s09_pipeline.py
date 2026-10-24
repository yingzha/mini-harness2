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
    {
        "label": "a resumed stream starts over",
        "file": "steps/s09_pipeline.py",
        "replace": [("    return len(finished)\n", "    return 0\n")],
        "expect": "test_a_resumed_stream_skips_only_the_tasks_it_finished",
    },
    {
        "label": "a task that left no library cannot be checkpointed",
        "file": "steps/s09_pipeline.py",
        "replace": [('    if (folder / "library").is_dir():\n'
                     '        shutil.copytree(folder / "library", partial / "library")\n'
                     '    else:\n'
                     '        (partial / "library").mkdir(parents=True)\n',
                     '    shutil.copytree(folder / "library", partial / "library")\n')],
        "expect": "test_a_resumed_stream_skips_only_the_tasks_it_finished",
    },
    {
        "label": "the library kept as the interrupted task left it",
        "file": "steps/s09_pipeline.py",
        "replace": [('    shutil.rmtree(folder / "library", ignore_errors=True)\n'
                     '    if last:\n'
                     '        shutil.copytree(last / "library", folder / "library")\n', "")],
        "expect": "test_the_library_goes_back_to_what_the_finished_tasks_left",
    },
    {
        "label": "the interrupted task's folder left where its rerun writes",
        "file": "steps/s09_pipeline.py",
        "replace": [('            (folder / task_id).rename(folder / f"{task_id}.interrupted{max(taken, default=0) + 1}")\n',
                     "            pass\n")],
        "expect": "test_the_interrupted_task_reruns_in_a_clean_folder",
    },
    {
        "label": "the interrupted suffix counted, not the highest taken",
        "file": "steps/s09_pipeline.py",
        "replace": [("max(taken, default=0) + 1", "len(taken) + 1")],
        "expect": "test_the_interrupted_task_reruns_in_a_clean_folder",
    },
    {
        "label": "finished tasks' folders moved aside too",
        "file": "steps/s09_pipeline.py",
        "replace": [("    for task_id in task_ids[len(finished):]:\n", "    for task_id in task_ids:\n")],
        "expect": "test_the_interrupted_task_reruns_in_a_clean_folder",
    },
    {
        "label": "a checkpoint cut off mid-write trusted",
        "file": "steps/s09_pipeline.py",
        "replace": [('if p.name.isdigit()]', 'if p.name.split(".")[0].isdigit()]'),
                    ("key=lambda p: int(p.name)", 'key=lambda p: int(p.name.split(".")[0])')],
        "expect": "test_a_checkpoint_cut_off_mid_write_is_not_trusted",
    },
    {
        "label": "a leftover partial checkpoint not cleared before saving",
        "file": "steps/s09_pipeline.py",
        "replace": [("    shutil.rmtree(partial, ignore_errors=True)\n", "")],
        "expect": "test_a_checkpoint_cut_off_mid_write_is_not_trusted",
    },
    {
        "label": "another stream's run folder accepted",
        "file": "steps/s09_pipeline.py",
        "replace": [("    if list(task_ids[:len(finished)]) != finished:\n", "    if False:\n")],
        "expect": "test_another_streams_folder_is_refused",
    },
]
