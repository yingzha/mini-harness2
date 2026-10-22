# mini-Harness²

A from-scratch, lesson-by-lesson Python implementation of
**Harness²: Recursive Agent Harnessing for an Open World** ([arXiv 2610.14224](https://arxiv.org/abs/2610.14224)). The authors' own code is at [github.com/google-research/harness2](https://github.com/google-research/harness2).

## The idea

An agent is a frozen model plus a **harness**: the files around it (system prompt, guardrails, memory, tool guidance, subagents, skills, scripts and plugins). Harness² improves the harness on each new task without an answer key: it never sees a score, only what the agent did.

For each task in a stream:

1. **Run.** The agent attempts the task with the initial harness, H₀.
2. **Propose.** Two editors read that run, and each edits its own copy of the harness: INV changes how the agent works, DOM adds what a practitioner in the field would know.
3. **Probe.** Each candidate harness attempts the same task, and its run is set beside the first one.
4. **Compose.** A composer keeps the edits the evidence supports. The result, the successor harness H′, attempts the task too.
5. **Select.** The harness whose output is delivered is H★. By default (k = 1) that is H′. With k > 1, the steps before this one run k times in parallel, and a selector picks one output blind: it sees the outputs, not the harnesses that made them.
6. **Reflect.** A reflector writes what was learned to a library, which the editors and composers of later tasks read.

Only the library carries over from one task to the next: every task starts again from H₀.

```
for each task:

  H₀ ─► Run ─► Propose ─► Probe ─► Compose ─► H′ ─► Select ─► H★
                  ▲                                           │
                  │                                           ▼
               library ◄────────────────────────────────── Reflect
```

Two models play the roles, as in the paper's weak-executor, strong-editor setup:

- **Executor:** Claude Haiku 5.5, at low effort, runs each task inside the harness. A weaker executor leaves the improver something to fix; [docs/deviations.md](docs/deviations.md) says why low effort.
- **Improver:** Claude Opus 5.5, at high effort, proposes edits, composes them, selects outputs and reflects on what worked.

## Quick start

You need Docker and an Anthropic API key. On a Linux host, see [Setup](docs/running.md#setup) first.

```bash
cp .env.example .env          # then set ANTHROPIC_API_KEY in .env
docker compose build          # one image, for our code and for the sandboxes it starts
docker compose run --rm app   # the test suite (no API calls)
docker compose run --rm app uv run --frozen python -m demos.d01_harness   # Lesson 1's demo (no API calls)
```

The demos from Lesson 3 on need real tasks from WorkBuddy-Bench Office copied into `data/`, and the live ones cost money: see [docs/running.md](docs/running.md).

## Lessons

Each lesson is one module in `steps/`, built on the ones before it, so read them in order. Each module opens with the paper sections it implements, and its runnable demo is the `demos/dNN_*.py` with the same number. [docs/lessons.md](docs/lessons.md) has the details and what each demo costs.

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

Start with these two:

- [docs/lessons.md](docs/lessons.md): each lesson in more detail, with its demo and what it costs.
- [docs/running.md](docs/running.md): setup, getting the tasks, running the demos, where results go, cleanup.

Then, as you need them:

- [docs/design.md](docs/design.md): code layout, the rules the code follows, and where each of the paper's symbols lives.
- [docs/safety.md](docs/safety.md): the sandbox model-written code runs in, and why no grade reaches the method.
- [docs/testing.md](docs/testing.md): offline tests against a scripted API, and mutation testing.
- [docs/deviations.md](docs/deviations.md): where and why this differs from the paper.

## License

[MIT](LICENSE).
