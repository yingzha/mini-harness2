# Running

## Setup

You need Docker and an Anthropic API key. Our code runs in one container, `app`; the source is mounted read-only, and only `runs/` and a scratch volume for temporary folders are writable. Code the model writes runs in separate, short-lived containers (see [safety.md](safety.md)).

```bash
cp .env.example .env          # then set ANTHROPIC_API_KEY in .env
docker compose build          # also the image the sandboxes run
docker compose run --rm app   # the test suite (no API calls)
```

If your API key isn't scoped to a workspace, also set `ANTHROPIC_WORKSPACE_ID` in `.env`. On a Linux host, change `group_add` in [compose.yaml](../compose.yaml) to the group id of `/var/run/docker.sock` (`stat -c %g /var/run/docker.sock` prints it), so our code can start sandbox containers.

## The tasks

From Lesson 3 on, the demos run real tasks from WorkBuddy-Bench Office (`wb-bench-office-v1.0`; the benchmark is described in [arXiv 2607.20911](https://arxiv.org/abs/2607.20911)). It is not part of this repository. Lessons 3 to 8 use one of its 50 tasks. Lesson 9 runs a stream: by default the lesson's two tasks, or with `--stream text-office` the 14 tasks this runtime can attempt and grade ([deviations.md](deviations.md#tasks-and-evaluation) says why only those). [config.py](../config.py) names each stream's tasks, in the order they run. Copy the dataset's tasks into `data/`; the commands below assume it is in `~/Downloads`. `data/` is git-ignored because it holds the tasks' gold answers; only `benchmarks/workbuddy.py` reads those, to grade.

```bash
mkdir -p data/wb-bench-office-v1.0
cp -R ~/Downloads/wb-bench-office-v1.0/tasks data/wb-bench-office-v1.0/
```

## Demos

```bash
docker compose run --rm app uv run --frozen python -m demos.d04_propose                               # a lesson's demo, offline part
docker compose run --rm app uv run --frozen python -m demos.d09_pipeline --live                       # the whole pipeline
docker compose run --rm app uv run --frozen python -m demos.d09_pipeline --live --stream text-office  # over 14 tasks
```

Most demos print what their stage is told without calling the API, and run for real with `--live`. The exceptions: Lesson 1's demo never calls the API, and Lessons 2 and 5 always do. Lessons 7 to 9 also take `--k N` to set the recursion width k, and Lesson 9 takes `--stream NAME` to pick one of the streams in config.py. [lessons.md](lessons.md) lists each demo with a rough cost; the usage meter printed at the end of a live run has the actual figure.

Live runs from Lesson 4 on can take half an hour or more, and most of them print nothing until a stage ends. On a Mac, put `caffeinate -is` in front of the command, or the machine may sleep and drop the API connection mid-run. The client already retries transient API errors (`max_retries` in [config.py](../config.py)).

## Resuming a stream

The 14-task stream takes hours. If a Lesson 9 run is cut short, carry on with it:

```bash
docker compose run --rm app uv run --frozen python -m demos.d09_pipeline --resume runs/demo_l9_<time>
```

It carries on with the tasks and k the run began with (`run.json`), skipping the ones that finished. It puts the library back as they left it, since the task that was running may already have added its entry, and reruns that task, keeping its half-finished folder as `<task>.interrupted<n>`. A finished task whose grading failed is graded again from its kept runs. It refuses to start while the container that began the run is still running it.

## Where results go

Every live demo from Lesson 2 on keeps everything under `runs/demo_lN_<time>/`: each session's `context/` folder (exactly what that model saw, and for editors and composers the harness as they left it), each run's workspace and trajectory, diffs and notes, a `grade.md` with the failed checks, and `usage.jsonl`, one line per model call: when it was made, the session that made it (its folder, so spending splits by task and session), its role, how many messages the request held, its input, cache-read, cache-write, output and thinking tokens, and its estimated cost. `grade.md` holds expected values: it is for you, and nothing in the pipeline ever reads it. Each demo's docstring lists the layout of its own folder.

## Cleanup

If a run is killed mid-call, its sandbox container may survive. This removes every sandbox:

```bash
docker rm -f $(docker ps -aq --filter label=mini-harness2-sandbox)
```
