"""The offline demos must keep running. Each docstring names the failure guarded against."""

import subprocess
import sys

import pytest

import config


@pytest.mark.parametrize(("demo", "marker"), [
    ("d00_llm", "fallbacks='default'"),
    ("d01_harness", "After the fix: validate -> []"),
    ("d04_propose", "Run with --live"),
], ids=["d00_llm", "d01_harness", "d04_propose"])
def test_offline_demo_runs(demo, marker):
    """Guards: a change in steps/ breaking a lesson's demo, which is what you
    run to learn that lesson, without any library test noticing. The marker
    checks the demo got to its end. d02 makes live API calls and d03 needs the dataset, so they aren't run here;
    d04 runs up to where its live part starts."""
    done = subprocess.run([sys.executable, "-m", f"demos.{demo}"], cwd=config.ROOT,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    assert marker in done.stdout
