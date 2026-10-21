"""Bugs to plant in steps/s03_tasks.py, each with the test that must catch it.

Run with: python -m tools.mutate tests/mutations/s03_tasks.py
A control (expect=None) changes nothing observable, so no test may fail for it.
"""

MUTATIONS = [
    {
        "label": "task files may escape the folder",
        "file": "steps/s03_tasks.py",
        "replace": [
            ("target = resolve_inside(files, path)",
             "target = files / path"),
        ],
        "expect": "test_a_file_path_cannot_escape_the_task_folder",
    },
    {
        "label": "task written into a used folder",
        "file": "steps/s03_tasks.py",
        "replace": [
            ("if folder.exists() and any(folder.iterdir()):",
             "if False:"),
        ],
        "expect": "test_write_task_hands_over_the_request_and_files_only",
    },
    {
        "label": "reference replaces the stock prompt",
        "file": "steps/s03_tasks.py",
        "replace": [
            ("f\"{prompt}\\n\\n{reference.strip()}\\n\"",
             "f\"{reference.strip()}\\n\""),
        ],
        "expect": "test_initial_harness_extends_the_stock_prompt",
    },
]
