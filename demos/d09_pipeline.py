"""Demo for Lesson 9 (steps/s09_pipeline.py): Harness² over a stream of real
tasks, then a Table 1-style evaluation, for you only.

    python -m demos.d09_pipeline                                # the lesson's stream of two tasks (no API calls)
    python -m demos.d09_pipeline --live                         # k = 1: about $3 and 15 to 30 minutes per task
    python -m demos.d09_pipeline --live --k 2                   # with selection, roughly twice that
    python -m demos.d09_pipeline --stream text-office           # 14 tasks; with --live, likely $40 to $70 and 4 to 10 hours
    python -m demos.d09_pipeline --resume runs/demo_l9_<time>   # carry on with a live run that was cut short

Streams are named in config.WORKBUDDY_STREAMS, and their tasks must be in data/
(see docs/running.md). The costs per task were measured on the lesson's two
tasks; the other 12 of text-office's have never been run through the whole
pipeline. The evaluation needs no extra runs: each task's base runs are H0's
runs, so H0's score is theirs, and Harness²'s is the delivered output's. A live
run is kept under runs/demo_l9_<time>/:

  run.json        the stream (its task folders, in order) and k: what --resume carries on with
  owner           the container running it, so a resume can't start while it still is
  library/        the library as it grew; checkpoints/<n>/ holds it as each finished task left it
  <task>/         each task's recursion and reflection; <task>.interrupted<n>/ an attempt cut short
  rows.json       each finished task's runs to grade and, once graded, its scores: for you only
  report.md       the evaluation, rewritten as each task ends
  usage.jsonl     every model call's tokens and cost, by session
"""

import json
import random
import socket
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean

import config
from benchmarks import workbuddy
from steps.s00_llm import LLM
from steps.s01_harness import load_harness
from steps.s02_executor import Sandbox
from steps.s03_tasks import initial_harness
from steps.s09_pipeline import resume, run_stream, save_checkpoint


def option(flag: str) -> str | None:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else None


def shown(path: Path) -> Path:
    return path.relative_to(config.ROOT) if path.is_relative_to(config.ROOT) else path


resuming = option("--resume")
if resuming:
    if option("--stream") or option("--k"):
        raise SystemExit("--resume carries on with the stream and k the run began with; leave out --stream and --k.")
    run_dir = Path(resuming).resolve()
    if not (run_dir / "run.json").is_file():
        raise SystemExit(f"{resuming} is not a Lesson 9 run folder: it has no run.json.")
    began = json.loads((run_dir / "run.json").read_text())
    name, k, stream = began["stream"], began["k"], [config.ROOT / f for f in began["tasks"]]
else:
    name, k = option("--stream") or "lesson", int(option("--k") or 1)
    if name not in config.WORKBUDDY_STREAMS:
        raise SystemExit(f"No stream named {name!r}. config.WORKBUDDY_STREAMS has: {', '.join(config.WORKBUDDY_STREAMS)}.")
    stream = list(config.WORKBUDDY_STREAMS[name])
    run_dir = config.RUNS_DIR / time.strftime("demo_l9_%Y%m%d-%H%M%S")

missing = [shown(f) for f in stream if not f.is_dir()]
if missing:
    raise SystemExit(f"Not found: {', '.join(map(str, missing))}. Copy the stream's tasks there first (see docs/running.md).")
tasks = [workbuddy.load_task(f) for f in stream]
ids = [t.id for t in tasks]
folders = dict(zip(ids, stream))
print(f"The {name!r} stream, in order. Each task starts from H0; only the library carries over:")
print("".join(f"  {i}. {t.id}: {t.prompt.strip().splitlines()[0][:100]}\n" for i, t in enumerate(tasks, 1)))
if not resuming and "--live" not in sys.argv[1:]:
    print("Run with --live to run Harness² over it.")
    raise SystemExit

owner = run_dir / "owner"
if resuming and owner.is_file():
    other = owner.read_text().strip()
    running = subprocess.run(["docker", "ps", "--quiet", "--no-trunc"], capture_output=True, text=True).stdout.split()
    if other != socket.gethostname() and any(c.startswith(other) for c in running):
        raise SystemExit(f"Container {other} is still running this stream. Stop it first (docker stop {other}).")

stock, _ = load_harness(config.BASE_HARNESS_DIR)
h0 = initial_harness(stock, workbuddy.REFERENCE)
llm = LLM.from_env(config.LLM_SETTINGS, usage_log=run_dir / "usage.jsonl")
sandbox = Sandbox.from_docker(config.SANDBOX)
rows_file = run_dir / "rows.json"


def save_rows() -> None:
    partial = rows_file.with_name("rows.partial")
    partial.write_text(json.dumps(rows, indent=1))
    partial.replace(rows_file)


def graded(task_id: str, row: dict) -> dict:
    """The row with its scores. A grading error is recorded, not raised: the task
    is done and paid for, and its runs are kept to grade again on --resume."""
    try:
        base = mean(workbuddy.grade(sandbox, folders[task_id], Path(w), final_reply=reply).score
                    for w, reply in row["refs"])
        w, reply = row["delivered_run"]
        return row | {"h0": base, "harness2": workbuddy.grade(sandbox, folders[task_id], Path(w),
                                                              final_reply=reply).score, "error": None}
    except Exception as e:   # grading is evaluation: it must never cost the stream a task it finished
        return row | {"h0": None, "harness2": None, "error": f"{type(e).__name__}: {e}"[:400]}


if resuming:
    done = resume(run_dir, ids)
    rows = json.loads(rows_file.read_text()) if rows_file.is_file() else {}
    rows = {i: rows[i] for i in ids[:done] if i in rows}   # a row saved just before the stream stopped is a rerun's
    print(f"Resuming {shown(run_dir)}: {done} of {len(tasks)} tasks were done, and the library is back as they left it.")
    for task_id in [i for i, r in rows.items() if r["h0"] is None]:
        rows[task_id] = graded(task_id, rows[task_id])
        print(f"  graded again: {task_id}: " + (rows[task_id]["error"] or "done"))
    save_rows()
else:
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({"stream": name, "k": k, "tasks": [str(shown(f)) for f in stream]}))
    done, rows = 0, {}
owner.write_text(socket.gethostname())


def spent() -> float:
    return sum(r.cost_usd for r in llm.meter.snapshot().values())


def report() -> str:
    """The table so far, with Table 1's macro-average over the graded tasks; also written to report.md."""
    finished = [rows[i] | {"task": i} for i in ids if i in rows]
    ok = [r for r in finished if r["error"] is None]
    table = ["| Task | H0 | Harness² | Delivered | Library entry | $ |", "|---|---|---|---|---|---|"]
    table += [f"| {r['task']} | " + (f"{r['h0']:.3f} | {r['harness2']:.3f}" if r["error"] is None else "n/a | n/a")
              + f" | {r['delivered']} | {'yes' if r['entry'] else 'no'} | {r['cost']:.2f} |" for r in finished]
    if ok:
        table.append(f"| Mean of {len(ok)} graded | {mean(r['h0'] for r in ok):.3f} | "
                     f"{mean(r['harness2'] for r in ok):.3f} | | | {sum(r['cost'] for r in finished):.2f} |")
    text = "\n".join(table) + "".join(f"\n\nNot graded, {r['task']}: {r['error']}" for r in finished if r["error"])
    (run_dir / "report.md").write_text(
        f"# Harness² on the {name!r} stream: {len(finished)} of {len(tasks)} WorkBuddy-Bench Office tasks, k = {k}\n\n"
        f"{text}\n\nScores are the fraction of each task's deterministic checks that pass. H0 is the mean over the "
        "task's base runs. One stream, one run per harness: differences of a few checks can be chance. "
        "$ is each task's finished attempt; an attempt cut short is not counted.\n")
    return text


before = spent()
print(f"Running at k = {k}; each task reports when it is done.", flush=True)
for result in run_stream(llm, sandbox, tasks[done:], h0, run_dir, k=k, prompts_dir=config.PROMPTS_DIR,
                         limits=config.ROLLOUT_LIMITS, max_turns=config.IMPROVER_MAX_TURNS, rng=random.Random()):
    task_id, recursion = result.task.id, result.recursion
    cost, before = spent() - before, spent()
    rows[task_id] = {"refs": [[str(r.workspace), r.final_text] for r in recursion.step.refs],
                     "delivered_run": [str(recursion.delivered.workspace), recursion.delivered.final_text],
                     "delivered": recursion.chosen, "entry": result.added_to_library, "cost": cost,
                     "h0": None, "harness2": None, "error": None}
    save_rows()
    save_checkpoint(run_dir, ids[:ids.index(task_id) + 1])   # the task is done: nothing after this may undo it
    rows[task_id] = graded(task_id, rows[task_id])
    save_rows()
    report()
    row = rows[task_id]
    print(f"\n{task_id} ({len(rows)} of {len(tasks)}): delivered {recursion.chosen}'s output; " +
          ("left a library entry." if result.added_to_library else "left nothing in the library.")
          + f"\n  lesson: {result.reflection.experience.splitlines()[0] if result.reflection.experience else 'NO_ENTRY'}"
          + (f"\n  for you only: H0 {row['h0']:.3f}, Harness² {row['harness2']:.3f} (fraction of checks); ${cost:.2f}"
             if row["error"] is None else f"\n  grading failed, kept to grade again on --resume: {row['error']}"),
          flush=True)

print(f"\n{report()}\n\nEverything is under {shown(run_dir)}/")
print("Usage meter, this session:\n" + llm.meter.report())
