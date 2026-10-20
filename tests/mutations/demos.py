"""Bugs to plant in the offline demos, each with the test that must catch it.

Run with: python tools/mutate.py tests/mutations/demos.py
They model a refactor elsewhere that a demo depends on but no library test covers.
"""

MUTATIONS = [
    {
        "label": "d00 iterates a mapping as if it were pairs",
        "file": "demos/d00_llm.py",
        "replace": [
            ("for role, spec in settings.roles.items():",
             "for role, spec in settings.roles:"),
        ],
        "expect": "test_offline_demo_runs[d00_llm]",
    },
    {
        "label": "d01 imports a function that was renamed",
        "file": "demos/d01_harness.py",
        "replace": [
            ("from steps.s01_harness import Harness, component_of, diff, load_harness, validate",
             "from steps.s01_harness import Harness, component_for, diff, load_harness, validate"),
        ],
        "expect": "test_offline_demo_runs[d01_harness]",
    },
    {
        "label": "d01 stops before its last step",
        "file": "demos/d01_harness.py",
        "replace": [
            ('print(f"\\nAfter the fix: validate -> {validate(fixed)}")',
             'raise SystemExit(0)'),
        ],
        "expect": "test_offline_demo_runs[d01_harness]",
    },
]
