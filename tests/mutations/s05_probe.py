"""Bugs to plant in steps/s05_probe.py, each with the test that must catch it.

Run with: python -m tools.mutate tests/mutations/s05_probe.py
"""

MUTATIONS = [
    {
        "label": "candidates credited with each other's runs",
        "file": "steps/s05_probe.py",
        "replace": [("pool.map(run, harnesses, harnesses.values())",
                     "pool.map(run, harnesses, reversed(list(harnesses.values())))")],
        "expect": "test_probes_run_the_same_task_under_the_same_conditions",
    },
    {
        "label": "skills the probe loaded go unreported",
        "file": "steps/s05_probe.py",
        "replace": [("used = [f\"skill {c.input.get('name')}\" for c in calls if c.name == \"load_skill\"]",
                     "used = []")],
        "expect": "test_a_contrast_shows_what_changed_and_what_was_used",
    },
    {
        "label": "the agent's own scripts pass for harness scripts",
        "file": "steps/s05_probe.py",
        "replace": [("for s in scripts if SCRIPT_FILE.fullmatch(s) or SKILL_SCRIPT.fullmatch(s)]", "for s in scripts]")],
        "expect": "test_a_contrast_shows_what_changed_and_what_was_used",
    },
    {
        "label": "a run that produced nothing doesn't stand out",
        "file": "steps/s05_probe.py",
        "replace": [('or "NOTHING"', 'or ""')],
        "expect": "test_a_contrast_shows_what_changed_and_what_was_used",
    },
    {
        "label": "the deliverable diff is left out",
        "file": "steps/s05_probe.py",
        "replace": [("changes = diff_files(ref.deliverable, other.deliverable)", 'changes = ""')],
        "expect": "test_a_contrast_shows_what_changed_and_what_was_used",
    },
    {
        "label": "a script run as ./scripts/x.py goes unreported",
        "file": "steps/s05_probe.py",
        "replace": [("scripts = [str(PurePosixPath(s)) for c in calls", "scripts = [s for c in calls")],
        "expect": "test_a_contrast_shows_what_changed_and_what_was_used",
    },
    {
        "label": "a plugin that kept the agent working goes unreported",
        "file": "steps/s05_probe.py",
        "replace": [('used += ["plugin nudge"] * sum(', 'used += [] * sum(')],
        "expect": "test_a_contrast_shows_what_changed_and_what_was_used",
    },
    {
        "label": "any nudge passes for a plugin's",
        "file": "steps/s05_probe.py",
        "replace": [('bool(s.nudge and s.nudge.startswith("[plugin "))', "bool(s.nudge)")],
        "expect": "test_a_contrast_shows_what_changed_and_what_was_used",
    },
]
