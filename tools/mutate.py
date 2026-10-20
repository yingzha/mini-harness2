"""Mutation testing: prove that each test catches the bug it says it guards against.

Every bug listed in tests/mutations/*.py is planted, one at a time, in a fresh
copy of the project; the test suite runs in that copy, and the bug's expected
test must fail. A *control* (expect=None) is a change that keeps behaviour the
same, so no test may fail for it. The real project is never modified.

    python tools/mutate.py                                   # every bug list
    python tools/mutate.py tests/mutations/s01_harness.py    # one list

Exits non-zero if any bug goes uncaught, a control breaks a test, a bug no
longer applies to the current code, or the unmodified copy fails its tests.
"""

import os
import runpy
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_NOT_COPIED = shutil.ignore_patterns(".git", ".venv", ".env", "runs", "library", "tasks",
                                     "__pycache__", ".pytest_cache", "*.pdf")


def failing_tests(mutation: dict | None) -> set[str] | str:
    """Plant `mutation` (None: no change) in a copy and return the failing tests,
    or a message if the bug's text no longer occurs exactly once."""
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "project"
        shutil.copytree(ROOT, project, ignore=_NOT_COPIED)
        if mutation is not None:
            target = project / mutation["file"]
            source = target.read_text()
            for old, new in mutation["replace"]:
                if source.count(old) != 1:
                    return f"no longer applies: {old[:60]!r} occurs {source.count(old)} times in {mutation['file']}"
                source = source.replace(old, new)
            target.write_text(source)
        out = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=project,
                             capture_output=True, text=True).stdout
    return {line.split("::")[-1].split(" ")[0] for line in out.splitlines() if line.startswith(("FAILED", "ERROR"))}


def verdict(mutation: dict, failed: set[str] | str) -> tuple[bool, str]:
    label, expect = mutation["label"], mutation["expect"]
    if isinstance(failed, str):
        return False, f"  SETUP   {label}: {failed}"
    if expect is None:
        ok = not failed
        return ok, f"  {'ok' if ok else 'BROKE':<7} control: {label}" + ("" if ok else f" (failed: {', '.join(sorted(failed))})")
    ok = expect in failed
    detail = f"by {expect}" if ok else f"expected {expect}, failing: {', '.join(sorted(failed)) or 'none'}"
    return ok, f"  {'caught' if ok else 'MISSED':<7} {label}  ({detail})"


specs = [Path(p) for p in sys.argv[1:]] or sorted((ROOT / "tests" / "mutations").glob("*.py"))
baseline = failing_tests(None)
if baseline:
    sys.exit(f"The unmodified project fails its tests ({baseline}); mutation results would mean nothing.")

all_ok = True
with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
    for spec in specs:
        mutations = runpy.run_path(str(spec))["MUTATIONS"]
        shown = spec.resolve().relative_to(ROOT) if spec.resolve().is_relative_to(ROOT) else spec
        print(f"{shown}  ({len(mutations)} bug{'' if len(mutations) == 1 else 's'})")
        for mutation, failed in zip(mutations, pool.map(failing_tests, mutations)):
            ok, line = verdict(mutation, failed)
            all_ok &= ok
            print(line)
print("\nAll planted bugs were caught by their expected tests." if all_ok else "\nSome checks FAILED (see above).")
sys.exit(0 if all_ok else 1)
