# mini-Harness²

A from-scratch, lesson-by-lesson Python implementation of
**Harness²: Recursive Agent Harnessing for an Open World** (arXiv 2610.14224, `2610.14224v1.pdf`).

## The idea

An agent is a frozen model plus a **harness**: the files around it (system prompt, guardrails, memory, tool guidance, subagents, skills, scripts and plugins). Harness² improves the harness on each new task, without an answer key. Two editors propose changes, one about how the agent works and one about what a practitioner in the field knows. Each candidate is run on the same task, and its behaviour is compared with the original run's. A composer keeps the edits the evidence supports (Propose, Probe, Compose). Across tasks, a reflector writes what was learned to a library that later tasks' editors read. Every task still starts from the same initial harness, H₀.

## Models

- **Executor:** Claude Haiku 5.5, at low effort, runs each task inside the harness. The paper pairs a weaker executor with a strong editor; at medium effort, Haiku passed 271 of our test task's 273 checks, leaving the editor little to improve.
- **Editor:** Claude Opus 5.5 improves the harness: it proposes edits, composes them, selects outputs and reflects on what worked.

## Running

Our code runs in one Docker container, `app`. The source is mounted **read-only**; only `runs/` and a scratch volume for temporary folders are writable. Code the model writes runs in separate, short-lived containers (see Safety).

```bash
cp .env.example .env          # then set ANTHROPIC_API_KEY in .env
docker compose build          # also the image the sandboxes run
docker compose run --rm app                                          # test suite (no API calls)
docker compose run --rm app uv run --frozen python -m demos.d00_llm  # a lesson's demo
```

If your API key isn't scoped to a workspace, also set `ANTHROPIC_WORKSPACE_ID` in `.env`. On a Linux host, change `group_add` in [compose.yaml](compose.yaml) to the group id of `/var/run/docker.sock`.

From Lesson 3 on, the demos run one real task from WorkBuddy-Bench Office (`wb-bench-office-v1.0`), which is not part of this repository. Copy that task into `data/`; it is git-ignored, since it holds the task's gold answers:

```bash
mkdir -p data/wb-bench-office-v1.0/tasks
cp -R ~/Downloads/wb-bench-office-v1.0/tasks/service-channel-ticket-daily data/wb-bench-office-v1.0/tasks/
```

## Safety

From Lesson 2 on, the model writes code that we run: `run_python` calls (from the agent and its subagents) and plugin hooks. Each call runs in a fresh container (`Sandbox` in [steps/s02_executor.py](steps/s02_executor.py)) that:

- sees only that rollout's workspace (read-only for plugins): not the source (so not the grader), not other rollouts;
- has no network, and none of our environment, so no API key;
- runs as an unprivileged user with every capability dropped and no way to gain more;
- is capped at 128 processes and 512 MB of memory;
- has its output cut to the start and end as it streams in, on our side, so printing gigabytes costs our container nothing;
- is removed when the call ends, which kills anything it left running.

[tests/test_s02_executor.py](tests/test_s02_executor.py) checks each of these from inside a sandbox, and `tests/mutations/` proves each check fails when its protection is removed.

A benchmark task's own checks are downloaded code, so they run in a sandbox too, with the task's tests and gold answers mounted read-only. The workspace being graded is mounted at `/work`, not `/workspace`: their test module puts `/workspace` first on Python's import path, so an `eval_core.py` an agent wrote there would replace the real checks.

What remains:

- The `app` container holds the API key and the Docker socket, and whoever can use that socket controls Docker. That is acceptable only because no model-written code runs in `app`; keep it that way. File tools run there, but they only read and write files, refusing paths outside their folder.
- Containers share the kernel of Docker's VM, so a kernel exploit could escape one. A VM per call (gVisor, Firecracker) would be stronger; this project doesn't need it.
- Use a workspace-scoped API key with a spend limit.

If a run is killed mid-call, its sandbox may survive. `docker rm -f $(docker ps -aq --filter label=mini-harness2-sandbox)` removes every sandbox.

## Code layout

- `steps/sNN_*.py`: one lesson each. Pure library code with no globals, no CLI and no side effects on import. Dependencies (such as the `LLM` gateway) are passed in explicitly.
- `base_harness/`: H₀'s stock files, the harness every task starts from.
- `benchmarks/`: real tasks to run the method on, and the benchmark's own way of grading them. [benchmarks/workbuddy.py](benchmarks/workbuddy.py) loads a WorkBuddy-Bench task and runs its checks. Nothing in `steps/` imports from here; entry points pick a task and pass it in.
- `data/`: datasets you download (git-ignored; see Running).
- `runs/`: what demos and runs leave behind: workspaces, trajectories, grades (git-ignored).
- `demos/dNN_*.py`: the runnable entry point for each lesson. The only place that reads `config.py` and builds real clients.
- `config.py`: immutable default settings (frozen dataclasses), with no behaviour.
- `tests/`: offline tests. They run the real Anthropic SDK against a scripted HTTP transport ([tests/scripted_api.py](tests/scripted_api.py)), and each test's docstring names the bug it guards against.
- `tests/mutations/`: for each module, the bugs its tests must catch, and which test catches each one.
- `tools/mutate.py` (`python -m tools.mutate`): plants those bugs one at a time in a copy of the project and checks the right test fails.

## Do the tests actually catch bugs?

Passing tests prove little on their own. `tools/mutate.py` plants each bug listed in `tests/mutations/` into a temporary copy of the project and checks that the test named for it fails. It also runs *controls*: changes that alter nothing, which no test may fail on. The real files are never touched.

```bash
docker compose run --rm app uv run --frozen python -m tools.mutate                                  # every list, about 10 minutes
docker compose run --rm app uv run --frozen python -m tools.mutate tests/mutations/s01_harness.py   # one module
```

When you add a test, add the bug it guards against to the matching list.

## Learning path

Read the lessons in order. Each `steps/sNN_*.py` opens with the paper section it implements; its demo is `demos/dNN_*.py`.

| Lesson | Module | Paper | What it adds | Try |
|---|---|---|---|---|
| L0 | [steps/s00_llm.py](steps/s00_llm.py) | §2.1 frozen M, §3.1 roles, Fig. 6 compute | The `LLM` gateway: `llm.call(role, …)`; executor vs editor models; a per-run usage and cost meter | `python -m demos.d00_llm` (offline), then `--live` |
| L1 | [steps/s01_harness.py](steps/s01_harness.py) | §2.1, Table 5, §D.1-D.2, Prompt 1 rules | The harness as an immutable value: 8 components on an editable surface, H₀ in [base_harness/](base_harness/), `validate`, `diff`, load/write | `python -m demos.d01_harness` |
| L2 | [steps/s02_executor.py](steps/s02_executor.py) | §2.1 A(q; M, H), §2.2.1 e = (τ, y), Table 5 activation, Table 7 | The agent loop, file and `run_python` tools, `load_skill`, `run_subagent`, plugin hooks, the execution record, and the sandbox that model-written code runs in | `python -m demos.d02_executor` (live, about $0.01) |
| L3 | [steps/s03_tasks.py](steps/s03_tasks.py), [benchmarks/workbuddy.py](benchmarks/workbuddy.py) | §2.1 the task stream, §D.1 H₀, Appendix B grading | A task is a request plus files; H₀ is the stock harness plus the benchmark's reference instructions; the deliverable is whatever the agent created or changed; a real task's own checks give the score (the fraction that pass), which the method itself never sees | `python -m demos.d03_tasks` (no API calls), then `--live` (H₀ on the task, about 2 cents) |
| L4 | s04_propose | §2.2.1 Propose, Prompts 1-2 | | |
| L5 | s05_probe | §2.2.1 Probe | | |
| L6 | s06_compose | §2.2.1 Compose, Eq. 1, Prompts 3-4 | | |
| L7 | s07_recursion | §2.2.2 Eq. 2-3, Prompt 5 | | |
| L8 | s08_library | §2.3 Eq. 4, Prompt 6 | | |
| L9 | s09_pipeline, evaluate.py | the full loop, Table 1 | | |

## Deviations from the paper

Each one follows from the same question: does the rule guard a failure that can happen in *this* runtime?

- **Plugins are Python** (`plugin/<name>.py`), not TypeScript, because our executor is a Python loop.
- **No "template braces" rule.** The paper forbids `{{` / `{%` in always-on text because its runtime renders those files with Jinja. Ours doesn't template, so there is nothing to break.
- **No frontmatter `name` / `mode: subagent`.** OpenCode needs them to load agents; our runtime identifies skills and subagents by their folder. Only `description` is required, because the agent reads it to decide what to use.
- **Skill helper scripts must be `.py`**, since `run_python` is the only way our executor runs code.
- **A small custom agent instead of OpenCode/Codex.** Tools: `list_files`, `read_file`, `write_file`, `run_python` (no shell), plus `load_skill` and `run_subagent` when the harness has skills or subagents. A rollout is capped at 40 turns (the paper: 200) and each code run at 60 s; there is no separate wall-clock cap, since those two already bound it.
- **Two plugin hooks:** `after_tool` (append a note to a tool result) and `before_finish` (keep the agent working, at most twice). Subagents can't delegate again and don't run plugins.
- **One real task instead of three benchmarks.** We test with WorkBuddy-Bench Office's `service-channel-ticket-daily` (a daily ticket report from a CSV export, a JSON snapshot and a guidance document); the paper runs every test task of WorkBuddy-Bench, JobBench and LAB, three times each.
- **Deterministic checks only.** The task's score is the fraction of its own 273 checks that pass. Its LLM-judge rubrics (20% of the benchmark's full score for this task) are not run.

Filled in further as lessons land.
