# mini-Harness²

A from-scratch, lesson-by-lesson Python implementation of
**Harness²: Recursive Agent Harnessing for an Open World** (arXiv 2610.14224, `2610.14224v1.pdf`).

## The idea

An agent is a frozen model plus a **harness**: the files around it (system prompt, guardrails, memory, tool guidance, subagents, skills, scripts and plugins). Harness² improves the harness on each new task, without an answer key. Two editors propose changes, one about how the agent works and one about what a practitioner in the field knows. Each candidate is run on the same task, and its behaviour is compared with the original run's. A composer keeps the edits the evidence supports (Propose, Probe, Compose). Across tasks, a reflector writes what was learned to a library that later tasks' editors read. Every task still starts from the same initial harness, H₀.

```
for each task in the stream:
  H₀ ──► run it ──► Propose (INV, DOM) ──► Probe (run each) ──► Compose ──► H′ ──► run it
                        ▲ reads                    k > 1: pick one output blind ──► H★, delivered
                        │                                                             │
                     library ◄─────── Reflect on everything, add an entry ◄────────────┘
```

Two models play the roles, as in the paper's weak-executor, strong-editor setup:

- **Executor:** Claude Haiku 5.5, at low effort, runs each task inside the harness. A weaker executor leaves the improver something to fix; [docs/deviations.md](docs/deviations.md) says why low effort.
- **Improver:** Claude Opus 5.5 proposes edits, composes them, selects outputs and reflects on what worked.

## Quick start

```bash
cp .env.example .env          # then set ANTHROPIC_API_KEY in .env
docker compose build          # also the image the sandboxes run
docker compose run --rm app   # the test suite (no API calls)
docker compose run --rm app uv run --frozen python -m demos.d01_harness   # a lesson's demo
```

The demos from Lesson 3 on need real tasks from WorkBuddy-Bench Office copied into `data/`, and the live ones cost money: see [docs/running.md](docs/running.md).

## Lessons

Read them in order. Each `steps/sNN_*.py` opens with the paper sections it implements; its demo is `demos/dNN_*.py`. [docs/lessons.md](docs/lessons.md) has the details and what each demo costs.

| Lesson | Module | Adds |
|---|---|---|
| L0 | [s00_llm](steps/s00_llm.py) | The model gateway, by role, with a usage and cost meter |
| L1 | [s01_harness](steps/s01_harness.py) | The harness as a value: eight components, validation, diffs |
| L2 | [s02_executor](steps/s02_executor.py) | The agent loop, its tools and plugins, the execution record, the sandbox |
| L3 | [s03_tasks](steps/s03_tasks.py) | Tasks, H₀, and a real task's own checks (which the method never sees) |
| L4 | [s04_propose](steps/s04_propose.py) | Propose: INV and DOM editors, each editing its own copy of the harness |
| L5 | [s05_probe](steps/s05_probe.py) | Probe: each candidate run once, and its run contrasted with the reference |
| L6 | [s06_compose](steps/s06_compose.py) | Compose, and the whole contrastive step Φ |
| L7 | [s07_recursion](steps/s07_recursion.py) | Parallel recursion, and the blind selection of H★ |
| L8 | [s08_library](steps/s08_library.py) | Reflection, and the library later tasks read |
| L9 | [s09_pipeline](steps/s09_pipeline.py) | The whole loop over a stream of tasks, and its evaluation |

## Docs

- [docs/lessons.md](docs/lessons.md): each lesson in more detail, with its demo.
- [docs/running.md](docs/running.md): setup, the tasks, costs, long runs, where results go, cleanup.
- [docs/design.md](docs/design.md): code layout, the rules the code follows, and where each of the paper's symbols lives.
- [docs/safety.md](docs/safety.md): the sandbox model-written code runs in, and why no grade reaches the method.
- [docs/testing.md](docs/testing.md): offline tests against a scripted API, and mutation testing.
- [docs/deviations.md](docs/deviations.md): where and why this differs from the paper.
