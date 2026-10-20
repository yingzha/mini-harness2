# mini-Harness²

A from-scratch, lesson-by-lesson Python implementation of
**Harness²: Recursive Agent Harnessing for an Open World** (arXiv 2610.14224, `2610.14224v1.pdf`).

**Executor:** Claude Haiku 5.5 runs each task inside the harness.
**Editor:** Claude Opus 5.5 improves the harness: it proposes edits, composes them, selects outputs and reflects on what worked.

## Running

Everything runs in one Docker container. The source is mounted **read-only**; only `tasks/`, `runs/` and `library/` are writable.

```bash
cp .env.example .env          # then set ANTHROPIC_API_KEY in .env
docker compose build
docker compose run --rm app                                          # offline test suite
docker compose run --rm app uv run --frozen python -m demos.d00_llm  # a lesson's demo
```

If your API key isn't scoped to a workspace, also set `ANTHROPIC_WORKSPACE_ID` in `.env`.

## Safety

From Lesson 2 on, the model writes code that we run. It runs inside the container with the workspace as its working directory, a timeout, and an environment without the API key; file tools refuse paths outside their folder; `.env` is hidden inside the container. That closes the easy paths, not all of them: model code shares the container with the executor, so it could still read the key from `/proc/<pid>/environ`, read the project source, or use the network. A fresh container per rollout (as in the paper) would close those. Use a workspace-scoped key with a spend limit.

## Code layout

- `steps/sNN_*.py`: one lesson each. Pure library code with no globals, no CLI and no side effects on import. Dependencies (such as the `LLM` gateway) are passed in explicitly.
- `demos/dNN_*.py`: the runnable entry point for each lesson. The only place that reads `config.py` and builds real clients.
- `config.py`: immutable default settings (frozen dataclasses), with no behaviour.
- `tests/`: offline tests. They run the real Anthropic SDK against a scripted HTTP transport ([tests/scripted_api.py](tests/scripted_api.py)), and each test's docstring names the bug it guards against.

## Learning path

Read the lessons in order. Each `steps/sNN_*.py` opens with the paper section it implements; its demo is `demos/dNN_*.py`.

| Lesson | Module | Paper | What it adds | Try |
|---|---|---|---|---|
| L0 | [steps/s00_llm.py](steps/s00_llm.py) | §2.1 frozen M, §3.1 roles, Fig. 6 compute | The `LLM` gateway: `llm.call(role, …)`; executor vs editor models; a per-run usage and cost meter | `python -m demos.d00_llm` (offline), then `--live` |
| L1 | [steps/s01_harness.py](steps/s01_harness.py) | §2.1, Table 5, §D.1-D.2, Prompt 1 rules | The harness as an immutable value: 8 components on an editable surface, H₀ in [base_harness/](base_harness/), `validate`, `diff`, load/write | `python -m demos.d01_harness` |
| L2 | [steps/s02_executor.py](steps/s02_executor.py) | §2.1 A(q; M, H), §2.2.1 e = (τ, y), Table 5 activation, Table 7 | The agent loop, file and `run_python` tools, `load_skill`, `run_subagent`, plugin hooks, the execution record | `python -m demos.d02_executor` (live, about $0.01) |
| L3 | s03_tasks | open-world task stream | | |
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

Filled in further as lessons land.
