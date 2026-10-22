"""Tests for loading and grading a WorkBuddy-Bench task. Each docstring names the
real failure the test guards against. They use a small stand-in task folder laid
out like the real ones, so they run without the dataset."""

import io
import json
import tarfile
from pathlib import Path

import pytest

from benchmarks.workbuddy import grade, load_task
from steps.s03_tasks import write_task

GOLD = {"tickets": 17, "busiest_desk": "East desk", **{f"field_{i}": f"value {i}" for i in range(80)}}

# Their glue, cut down: it reads WB_BENCH_* variables and puts /workspace first on sys.path.
TEST_VERIFY = '''
import os, sys
from pathlib import Path
import pytest
GRADING_DIR = Path(__file__).resolve().parent
GOLD_PATH = Path(os.environ.get("WB_BENCH_GOLD_PATH", "/tests/gold/gold_answer.json"))
OUTPUT_PATH = os.environ.get("WB_BENCH_OUTPUT_PATH", "/workspace/report.md")
sys.path.insert(0, str(GRADING_DIR))
sys.path.insert(0, "/workspace")
try:
    open("/tests/gold/tampered", "w").write("x")
except OSError:
    pass
import eval_core
_CHECKS = eval_core.evaluate(OUTPUT_PATH, GOLD_PATH)["checks"]
'''
EVAL_CORE = '''
import json
from pathlib import Path
def evaluate(output_path, gold_path):
    gold = json.loads(Path(gold_path).read_text())
    output = Path(output_path) / "report.md" if Path(output_path).is_dir() else Path(output_path)
    text = output.read_text() if output.exists() else ""
    print("evaluating", output_path)
    return {"checks": [{"name": f"mentions_{k}", "passed": str(v) in text, "detail": f"expected {v!r} " * 20}
                       for k, v in gold.items()]}
'''


@pytest.fixture
def task_folder(tmp_path) -> Path:
    folder = tmp_path / "ticket-daily"
    (folder / "environment").mkdir(parents=True)
    (folder / "instruction.md").write_text("Write report.md from input/tickets.csv.", encoding="utf-8")
    with tarfile.open(folder / "environment" / "workspace.tar.gz", "w:gz") as archive:
        data = b"id,desk\n1,East desk\n"
        member = tarfile.TarInfo("input/tickets.csv")
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    (folder / "tests" / "grading").mkdir(parents=True)
    (folder / "tests" / "gold").mkdir()
    (folder / "tests" / "grading" / "test_verify.py").write_text(TEST_VERIFY)
    (folder / "tests" / "grading" / "eval_core.py").write_text(EVAL_CORE)
    (folder / "tests" / "gold" / "gold_answer.json").write_text(json.dumps(GOLD))
    (folder / "tests" / "verifier.toml").write_text('[env]\nWB_BENCH_GOLD_PATH = "/tests/gold/gold_answer.json"\n')
    return folder


def workspace_with(task_folder: Path, tmp_path: Path, files: dict[str, str]) -> Path:
    workspace = write_task(load_task(task_folder), tmp_path / "rollout")
    for path, text in files.items():
        (workspace / path).write_text(text)
    return workspace


def test_a_task_is_its_request_and_starting_files_only(task_folder):
    """Guards: the task's checks or gold answers reaching the agent's workspace
    (loading the whole folder instead of the workspace archive)."""
    task = load_task(task_folder)
    assert task.prompt == "Write report.md from input/tickets.csv."
    assert dict(task.files) == {"input/tickets.csv": b"id,desk\n1,East desk\n"}


def test_its_own_checks_grade_the_workspace(sandbox, task_folder, tmp_path):
    """Guards: the checks not finding the gold answers or the deliverable (so
    every rollout scores zero and the score says nothing), and a long list of
    checks cut off mid-way, which crashes grading of exactly the long reports."""
    report = "\n".join(str(v) for v in GOLD.values())
    full = grade(sandbox, task_folder, workspace_with(task_folder, tmp_path / "a", {"report.md": report}))
    partial = grade(sandbox, task_folder, workspace_with(task_folder, tmp_path / "b", {"report.md": "17 tickets"}))
    assert len(full.checks) == len(GOLD) and full.score == 1.0
    assert [c.name for c in partial.checks if c.passed] == ["mentions_tickets"]


@pytest.mark.parametrize(("env", "output_line"), [
    ('WB_BENCH_OUTPUT_PATH = "/workspace"\n',
     'OUTPUT_PATH = os.environ.get("WB_BENCH_OUTPUT_PATH", "/workspace")'),
    ("",
     "DEFAULT_OUTPUT_PATH = '/workspace/report.md'\n"
     'OUTPUT_PATH = os.environ.get("WB_BENCH_OUTPUT_PATH", DEFAULT_OUTPUT_PATH)'),
], ids=["whole-workspace", "module-constant"])
def test_checks_find_the_deliverable_however_the_task_names_it(sandbox, task_folder, tmp_path, env, output_line):
    """Guards: a task that names its deliverable as the bare /workspace (the
    whole workspace is the output) or through a DEFAULT_OUTPUT_PATH constant,
    left pointing at /workspace, where the sandbox mounts nothing: every check
    fails on every rollout, and the task looks impossible rather than broken."""
    (task_folder / "tests" / "grading" / "test_verify.py").write_text(TEST_VERIFY.replace(
        'OUTPUT_PATH = os.environ.get("WB_BENCH_OUTPUT_PATH", "/workspace/report.md")', output_line))
    (task_folder / "tests" / "verifier.toml").write_text(
        '[env]\nWB_BENCH_GOLD_PATH = "/tests/gold/gold_answer.json"\n' + env)
    report = "\n".join(str(v) for v in GOLD.values())
    assert grade(sandbox, task_folder, workspace_with(task_folder, tmp_path, {"report.md": report})).score == 1.0


def test_an_agent_cannot_grade_itself(sandbox, task_folder, tmp_path):
    """Guards: their test module putting /workspace first on sys.path, so an
    eval_core.py the agent wrote into its workspace replaces the real checks
    and passes everything; and the checks (code we downloaded) changing the
    gold answers on our disk."""
    forged = 'def evaluate(*args):\n    return {"checks": [{"name": "forged", "passed": True}]}\n'
    g = grade(sandbox, task_folder, workspace_with(task_folder, tmp_path, {"eval_core.py": forged, "report.md": ""}))
    assert "forged" not in {c.name for c in g.checks} and g.score == 0.0
    assert not (task_folder / "tests" / "gold" / "tampered").exists()
