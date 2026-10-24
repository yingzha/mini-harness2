"""Real tasks from WorkBuddy-Bench Office (paper, Appendix B), one at a time, for smoke tests.

The dataset isn't part of this repository: copy the task you use into
data/wb-bench-office-v1.0/tasks/ (git-ignored; see docs/running.md). Each task is a Harbor folder:

    instruction.md                  the request
    environment/workspace.tar.gz    the files the agent starts with
    tests/grading/                  the task's own deterministic checks (code we downloaded)
    tests/gold/                     the answers those checks compare against
    tests/verifier.toml             how the benchmark runs them
    tests/judge.yaml                LLM-judge rubrics (not used here)

* `load_task` turns a folder into a Task: the request and the starting files.
  tests/ is never part of it, so it can't reach a workspace or an editor.
* `grade` runs the task's own checks on a finished workspace, in a sandbox,
  since they are code we downloaded. The LLM-judge rubrics are not run, so the
  score is the deterministic part alone (the benchmark's test_pass_rate, which
  carries 70 to 85% of its full score).
"""

from __future__ import annotations

import json
import re
import tarfile
import tempfile
import tomllib
from pathlib import Path
from types import MappingProxyType

from steps.s02_executor import WORKDIR, Sandbox
from steps.s03_tasks import Check, Grade, Task

# Added to the stock harness to make this benchmark's H0 (§D.1; steps/s03_tasks.initial_harness)
REFERENCE = ("Your current directory is the task's workspace. The request names the materials to use "
             "(usually under input/); treat them as read-only. Save each deliverable exactly where the "
             "request says.")

# Runs in the sandbox, with the image's venv Python: their test module imports pytest.
_CHECK_RUNNER = """
import json, os, runpy
with os.fdopen(os.dup(1), "w") as result:
    os.dup2(2, 1)   # what their code prints goes to stderr, not into the result
    checks = runpy.run_path("/tests/grading/test_verify.py")["_CHECKS"]
    json.dump([[str(c.get("name")), c.get("passed") is True, str(c.get("detail", ""))] for c in checks], result)
"""


def load_task(folder: Path) -> Task:
    """A Harbor task folder as a Task: instruction.md and the workspace archive."""
    with tarfile.open(folder / "environment" / "workspace.tar.gz") as archive:
        files = {m.name.removeprefix("./"): archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}
    return Task(folder.name, (folder / "instruction.md").read_text(encoding="utf-8"), MappingProxyType(files))


def _moved(path: str) -> str:
    """A path their code is given under /workspace, where the sandbox mounts the workspace instead."""
    return WORKDIR + path[len("/workspace"):] if path == "/workspace" or path.startswith("/workspace/") else path


def grade(sandbox: Sandbox, folder: Path, workspace: Path, *, final_reply: str = "", timeout_s: float = 300) -> Grade:
    """Run the task's own deterministic checks on a finished workspace. `final_reply`
    is the agent's last message: some tasks check it, and the benchmark's runner
    saves it as /workspace/final_answer.md."""
    tests = folder / "tests"
    verify = (tests / "grading" / "test_verify.py").read_text(encoding="utf-8")
    # Their test module puts /workspace first on sys.path, so a file the agent wrote
    # there under the name of one of their modules (eval_core.py) would replace
    # their checks. The workspace goes to WORKDIR instead, every path their
    # variables give under /workspace is moved there, and /workspace holds only
    # final_answer.md, which can't be imported. Their module may also name the
    # deliverable itself, as a default for WB_BENCH_OUTPUT_PATH or as
    # DEFAULT_OUTPUT_PATH: a file, or the bare /workspace when the whole workspace
    # is the deliverable. Checks that need the benchmark runner's trajectory log
    # can't pass here: we don't write one.
    env = {name: _moved(str(value))
           for name, value in tomllib.loads((tests / "verifier.toml").read_text(encoding="utf-8")).get("env", {}).items()}
    env.update(WB_BENCH_CASE_DIR=WORKDIR, WB_BENCH_VERIFIER_LOGS="/tmp/verifier")
    default = re.search(r"""(?:"WB_BENCH_OUTPUT_PATH",\s*|DEFAULT_OUTPUT_PATH\s*=\s*)["']/workspace(/[^"']*)?["']""",
                        verify)
    if default:
        env["WB_BENCH_OUTPUT_PATH"] = WORKDIR + (default.group(1) or "")
    if "WB_BENCH_OUTPUT_PATH" not in env and "WB_BENCH_OUTPUT_PATH" in verify:
        # Their own default would point at /workspace, so every check would fail
        # quietly: the task would look impossible rather than broken.
        raise RuntimeError(f"{folder.name}: can't tell where its checks look for the deliverable: its test "
                           "module names it in a form grade() doesn't know")
    with tempfile.TemporaryDirectory() as reply:
        (Path(reply) / "final_answer.md").write_text(final_reply, encoding="utf-8")
        done = sandbox.run(["/opt/venv/bin/python", "-I", "-c", _CHECK_RUNNER], workspace, writable=False,
                           timeout_s=timeout_s, readonly={"/tests": tests, "/workspace": Path(reply)}, env=env,
                           max_output=2_000_000)
    if done.returncode != 0:
        raise RuntimeError(f"{folder.name}: its checks did not run: {done.stderr[-800:]}")
    return Grade(tuple(Check(name, passed, detail) for name, passed, detail in json.loads(done.stdout)))
