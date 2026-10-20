"""Demo for Lesson 1 (steps/s01_harness.py).

    python -m demos.d01_harness

Loads the stock harness H0, shows its components, then plays the part of an
editor: makes an edit that breaks two rules, reads the validator's feedback,
fixes it, and prints the resulting diff. Nothing is written to disk.
"""

import config
from steps.s01_harness import Harness, component_of, diff, load_harness, validate

h0, left_out = load_harness(config.BASE_HARNESS_DIR)

print("H0, the stock harness (Table 5):")
for path, text in sorted(h0.files.items()):
    c = component_of(path)
    label = f"{c.id} {c.name:<13} {c.activation}" if c else "placeholder (for editors only)"
    print(f"  {path:<38} {len(text):>4} B   {label}")
if left_out:
    print(f"  left out (off the editable surface): {left_out}")

print("\nWhat reaches the model on every call (C1-C4):")
print("  " + h0.always_on_text().replace("\n", "\n  "))
print(f"\nvalidate(H0) -> {validate(h0)}")

# An editor adds a skill whose helper script it forgot to ship, and forgets the trigger line.
skill = (
    "---\n"
    "description: Reconcile records across two files that share an ID.\n"
    "---\n"
    "1. Normalise IDs (strip spaces, upper-case, drop dashes) before joining.\n"
    "2. Run skills/reconcile/scripts/normalise_ids.py on each file.\n"
    "3. List records with no counterpart; never drop them silently.\n"
)
draft = Harness({**h0.files, "skills/reconcile/SKILL.md": skill})
print("\nAn editor's first draft adds skills/reconcile/SKILL.md. The validator says:")
for error in validate(draft):
    print(f"  - {error}")

fixed = Harness({
    **draft.files,
    "skills/reconcile/scripts/normalise_ids.py": (
        "import sys\n"
        "for line in open(sys.argv[1]):\n"
        "    print(line.strip().upper().replace('-', ''))\n"
    ),
    "guardrails.md": "When records from two files must be matched, load the `reconcile` skill.\n",
})
print(f"\nAfter the fix: validate -> {validate(fixed)}")
print("\nThe edit, as the composer and reflector will see it (diff H0 -> fixed):\n")
print(diff(h0, fixed))
