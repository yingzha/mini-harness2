"""Lesson 9 tests. Each docstring names the real failure the test guards against."""

import json
import random
import shutil
from pathlib import Path

import pytest

import config
from config import RolloutLimits
from steps.s00_llm import LLM, UsageMeter
from steps.s01_harness import load_harness
from steps.s03_tasks import Task
from steps.s08_library import Reflection, update_library
from steps.s09_pipeline import resume, run_stream, save_checkpoint
from tests.routes import routed
from tests.scripted_api import ScriptedAPI

H0, _ = load_harness(config.BASE_HARNESS_DIR)
LIMITS = RolloutLimits(max_turns=3, subagent_max_turns=1, tool_timeout_s=3)
TASKS = [Task("t1", "Write report.md from input/orders.csv.", {"input/orders.csv": b"id,amount\n1,5\n"}),
         Task("t2", "Write summary.md from input/visits.csv.", {"input/visits.csv": b"day,visits\nMon,3\n"})]


def test_each_task_starts_from_h0_and_learns_only_through_the_library(sandbox, tmp_path):
    """Guards: a task starting from the previous task's adopted harness, when
    the paper restarts every task from H0 and reuses earlier components only
    through Propose; and the library not reaching the next task's editors, so
    harnessing-level recursion does nothing."""
    llm = LLM(ScriptedAPI(routed()).client(), config.LLM_SETTINGS)
    results = list(run_stream(llm, sandbox, TASKS, H0, tmp_path, k=1, prompts_dir=config.PROMPTS_DIR,
                              limits=LIMITS, max_turns=3, rng=random.Random(0)))

    assert [r.task.id for r in results] == ["t1", "t2"]
    assert all(r.recursion.step.refs[0].harness == H0 for r in results)
    first_saw = tmp_path / "t1" / "step" / "editors" / "inv1" / "context" / "library"
    later_saw = tmp_path / "t2" / "step" / "editors" / "inv1" / "context" / "library"
    assert not any(first_saw.rglob("*"))
    assert (later_saw / "entries" / "t1" / "harness" / "guardrails.md").read_text() == "Rule 1.\n"
    assert all(r.added_to_library for r in results)
    assert results[0].recursion.delivered.label == "composed1"


def test_every_call_in_a_stream_is_logged_under_its_own_session(sandbox, tmp_path):
    """Guards: a session's calls logged without its label, or under another
    session's, so a stream's spending can't be split by task and session: the
    base runs of a task share one system prompt, and every task shares the
    editors' and the reflector's."""
    log = tmp_path / "usage.jsonl"
    llm = LLM(ScriptedAPI(routed()).client(), config.LLM_SETTINGS, UsageMeter(config.LLM_SETTINGS.prices, log))
    list(run_stream(llm, sandbox, TASKS, H0, tmp_path / "run", k=1, prompts_dir=config.PROMPTS_DIR,
                    limits=LIMITS, max_turns=3, rng=random.Random(0)))

    sessions = {json.loads(line)["session"] for line in log.read_text().splitlines()}
    expected = {str(tmp_path / "run" / t / s) for t in ("t1", "t2") for s in (
        "base/base1", "step/editors/inv1", "step/editors/dom1", "step/probes/inv1", "step/probes/dom1",
        "step/composers/composed1", "step/successors/composed1", "reflector")}
    assert sessions == expected


STREAM = ["t1", "t2", "t3"]
LESSON = Reflection("| guardrails.md | added a rule | the run followed it | kept |", "When X, do Y.", ())


def finish(folder, task_id):
    """What a finished task leaves in the library, through the real update_library."""
    assert update_library(folder / "library", task_id, H0, H0, LESSON)


def test_a_resumed_stream_skips_only_the_tasks_it_finished(tmp_path):
    """Guards: a resumed stream running again the tasks it had finished, paying
    for them twice; including when the first of them left nothing in the
    library (H★ was H0 and no lesson held), so there was no library to save."""
    assert resume(tmp_path, STREAM) == 0
    save_checkpoint(tmp_path, ["t1"])
    finish(tmp_path, "t2")
    save_checkpoint(tmp_path, ["t1", "t2"])
    assert resume(tmp_path, STREAM) == 2


def test_the_library_goes_back_to_what_the_finished_tasks_left(tmp_path):
    """Guards: the task that was running when the stream stopped having added
    its entry already, so that on the rerun its editors read its own lesson,
    and update_library then fails on the second entry, losing the task again.
    The same holds when no task had finished yet."""
    finish(tmp_path, "t1")
    assert resume(tmp_path, STREAM) == 0 and not (tmp_path / "library").exists()
    finish(tmp_path, "t1")
    save_checkpoint(tmp_path, ["t1"])
    finish(tmp_path, "t2")                       # t2 added its entry, then the stream stopped
    assert resume(tmp_path, STREAM) == 1
    assert [p.name for p in (tmp_path / "library" / "entries").iterdir()] == ["t1"]
    assert len((tmp_path / "library" / "index.md").read_text().splitlines()) == 1
    finish(tmp_path, "t2")                       # its rerun adds the entry again, with no clash


def test_the_interrupted_task_reruns_in_a_clean_folder(tmp_path):
    """Guards: a half-finished attempt's sessions and runs left where the rerun
    writes its own, so the two mix; a later interruption's folder landing on an
    earlier one's, also after one was cleared away; and the finished tasks'
    folders being moved too."""
    save_checkpoint(tmp_path, ["t1"])
    (tmp_path / "t1").mkdir()
    (tmp_path / "t1" / "kept.md").write_text("done")
    (tmp_path / "t2" / "step").mkdir(parents=True)
    assert resume(tmp_path, STREAM) == 1
    (tmp_path / "t2" / "step").mkdir(parents=True)
    assert resume(tmp_path, STREAM) == 1
    assert not (tmp_path / "t2").exists()
    assert sorted(p.name for p in tmp_path.glob("t2.*")) == ["t2.interrupted1", "t2.interrupted2"]
    shutil.rmtree(tmp_path / "t2.interrupted1")   # cleared away to save space
    (tmp_path / "t2" / "step").mkdir(parents=True)
    assert resume(tmp_path, STREAM) == 1
    assert sorted(p.name for p in tmp_path.glob("t2.*")) == ["t2.interrupted2", "t2.interrupted3"]
    assert (tmp_path / "t1" / "kept.md").read_text() == "done"


def test_a_checkpoint_cut_off_mid_write_is_not_trusted(tmp_path):
    """Guards: a stream stopped while saving a checkpoint, leaving one that
    looks whole but holds only part of the library, and a resume trusting it;
    and that leftover then making the rerun's own save of it fail."""
    save_checkpoint(tmp_path, ["t1"])
    partial = tmp_path / "checkpoints" / "2.partial"
    (partial / "library").mkdir(parents=True)
    (partial / "finished.json").write_text(json.dumps(["t1", "t2"]))
    assert resume(tmp_path, STREAM) == 1
    finish(tmp_path, "t2")
    save_checkpoint(tmp_path, ["t1", "t2"])
    assert resume(tmp_path, STREAM) == 2


def test_a_checkpoint_save_cut_off_leaves_the_last_whole_one(tmp_path, monkeypatch):
    """Guards: a checkpoint written in place, so a stream stopped while copying
    the library (a full disk, a kill) leaves one that looks whole with half a
    library in it, and the resume trusts it."""
    finish(tmp_path, "t1")
    save_checkpoint(tmp_path, ["t1"])
    finish(tmp_path, "t2")

    def cut_off(src, dst, **_):
        Path(dst, "entries").mkdir(parents=True)   # part of the library is copied, then the save stops
        raise OSError("No space left on device")

    monkeypatch.setattr(shutil, "copytree", cut_off)
    with pytest.raises(OSError):
        save_checkpoint(tmp_path, ["t1", "t2"])
    monkeypatch.undo()
    assert resume(tmp_path, STREAM) == 1


def test_another_streams_folder_is_refused(tmp_path):
    """Guards: resuming a stream in another stream's run folder, so that its
    tasks read a library built from tasks that aren't in it."""
    finish(tmp_path, "other")
    save_checkpoint(tmp_path, ["other"])
    with pytest.raises(ValueError, match="another stream"):
        resume(tmp_path, STREAM)
