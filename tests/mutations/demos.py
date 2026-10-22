"""Bugs to plant in the offline demos, each with the test that must catch it.

Run with: python -m tools.mutate tests/mutations/demos.py
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
    {
        "label": "d04 reads a prompt file that was renamed",
        "file": "demos/d04_propose.py",
        "replace": [
            ('dom = (config.PROMPTS_DIR / "editor_dom.md").read_text()',
             'dom = (config.PROMPTS_DIR / "editor_domain.md").read_text()'),
        ],
        "expect": "test_offline_demo_runs[d04_propose]",
    },
    {
        "label": "d06 imports a function that was renamed",
        "file": "demos/d06_compose.py",
        "replace": [
            ("from steps.s06_compose import composer_prompt, contrastive_step",
             "from steps.s06_compose import composer_prompts, contrastive_step"),
        ],
        "expect": "test_offline_demo_runs[d06_compose]",
    },
    {
        "label": "d07 fills the selector prompt with a wrong argument",
        "file": "demos/d07_recursion.py",
        "replace": [("print(selector_prompt(config.PROMPTS_DIR, 4))", "print(selector_prompt(config.PROMPTS_DIR))")],
        "expect": "test_offline_demo_runs[d07_recursion]",
    },
    {
        "label": "d08 imports a function that was renamed",
        "file": "demos/d08_library.py",
        "replace": [("from steps.s08_library import reflect, reflector_prompt, update_library",
                     "from steps.s08_library import reflect, reflector_prompts, update_library")],
        "expect": "test_offline_demo_runs[d08_library]",
    },
]
