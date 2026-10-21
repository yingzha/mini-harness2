"""Lesson 3 tests. Each docstring names the real failure the test guards against."""

import pytest

import config
from steps.s01_harness import load_harness, validate
from steps.s03_tasks import Task, initial_harness, write_task

TASK = Task("demo", "Summarise input/orders.csv into report.md.",
            {"input/orders.csv": b"id,amount\n1,5\n", "input/notes/readme.md": b"# Notes\n"})


def test_write_task_hands_over_the_request_and_files_only(tmp_path):
    """Guards: anything besides what the requester gave reaching the agent,
    files landing at other paths than the request names, and stale files from
    an older version of a task mixing into a new one."""
    files = write_task(TASK, tmp_path / "demo")
    written = {p.relative_to(tmp_path / "demo").as_posix(): p.read_bytes()
               for p in (tmp_path / "demo").rglob("*") if p.is_file()}
    assert files == tmp_path / "demo" / "files"
    assert written == {"task.md": TASK.prompt.encode(), "files/input/orders.csv": b"id,amount\n1,5\n",
                       "files/input/notes/readme.md": b"# Notes\n"}

    used = tmp_path / "used"
    used.mkdir()
    (used / "orders_from_an_older_version.csv").write_text("stale")
    with pytest.raises(FileExistsError):
        write_task(TASK, used)


def test_a_file_path_cannot_escape_the_task_folder(tmp_path):
    """Guards: a downloaded archive with a member named ../../something
    writing outside the task folder (the classic tar path traversal)."""
    with pytest.raises(ValueError):
        write_task(Task("evil", "x", {"../../../escaped.txt": b"x"}), tmp_path / "deep" / "evil")
    assert not (tmp_path / "escaped.txt").exists()   # where ../../../ from deep/evil/files/ leads


def test_initial_harness_extends_the_stock_prompt():
    """Guards: a benchmark's reference instructions replacing the stock system
    prompt instead of extending it (§D.1), or landing in a file the agent
    never sees, or dropping the rest of the harness."""
    stock, _ = load_harness(config.BASE_HARNESS_DIR)
    h0 = initial_harness(stock, "Inputs are under input/.")
    prompt = h0.files["systemprompt.md"]
    assert prompt.startswith(stock.files["systemprompt.md"].rstrip()) and prompt.endswith("Inputs are under input/.\n")
    assert {p: t for p, t in h0.files.items() if p != "systemprompt.md"} == \
        {p: t for p, t in stock.files.items() if p != "systemprompt.md"}
    assert validate(h0) == []
