# Deviations from the paper

Each one follows from the same question: does the paper's rule guard a failure that can happen in *this* runtime, at this scale?

## The executor and its harness

- **A small custom agent instead of OpenCode or Codex.** Tools: `list_files`, `read_file`, `write_file`, `run_python` (no shell), plus `load_skill` and `run_subagent` when the harness has skills or subagents. A rollout is capped at 40 turns (the paper: 200) and each code run at 60 s; there is no separate wall-clock cap, since those two already bound it.
- **Plugins are Python** (`plugin/<name>.py`), not TypeScript, because our executor is a Python loop. They have two hooks: `after_tool` (append a note to a tool result) and `before_finish` (keep the agent working, at most twice). Subagents can't delegate again and don't run plugins.
- **No "template braces" rule.** The paper forbids `{{` and `{%` in always-on text because its runtime renders those files with Jinja. Ours doesn't template, so there is nothing to break.
- **No frontmatter `name` or `mode: subagent`.** OpenCode needs them to load agents; our runtime finds skills and subagents by their folder. Only `description` is required, because the agent reads it to decide what to use.
- **Skill helper scripts must be `.py`**, since `run_python` is the only way our executor runs code.

## Tasks and evaluation

- **Real tasks, but few.** Lessons 3 to 8 use one WorkBuddy-Bench Office task, `service-channel-ticket-daily` (a daily ticket report from a CSV export, a JSON snapshot and a guidance document). Lesson 9's stream adds a sibling, `market-daily-brief-a-share-recap` (a daily market recap from a frozen filing room of CSV, JSON and Markdown); both are text in, Markdown out. The paper runs every test task of WorkBuddy-Bench, JobBench and LAB, three times each. Tasks with spreadsheet or document files are out of reach here: the agent's Python has only the standard library, and deliverables are handled as text.
- **Deterministic checks only.** A task's score is the fraction of its own deterministic checks that pass (273 for the ticket task, 24 for the market recap). The tasks' LLM-judge rubrics are not run.
- **Evaluation lives in the Lesson 9 demo**, not in a separate script, and needs no extra runs: each task's base runs are H₀'s runs. There are no ablations (such as running without the library) and no repeated streams.

## The improver

- **The prompts are adapted to this runtime**, rule for rule: Python plugins with our two hooks, scripts run with `run_python`, the two validation rules that apply here, and no benchmark-specific block (H₀'s reference instructions are already in the harness the editor reads). Plugin shapes our hooks can't do (trimming or capping a tool's output) are left out. The composer's prompt adds one sentence, which our contrast makes checkable: a component the rollout never used cannot have caused what it did.
- **Editors and the composer have a `copy_file` tool.** The paper's sessions run in a coding agent with a shell; ours have only file tools, and retyping a 15 KB script to merge it would cost tokens and risk typos.
- **Improvement sessions are capped at 60 turns** (the paper sets no cap); a session that hits the cap falls back to its starting tree, like an invalid one.
- **No folder guard for grades.** The paper refuses any session folder holding a verdict, rubric or score. Here every session's folder is built only from a task, harnesses and execution records, none of which can hold one.

## Recursion, selection and the library

- **Parallel recursion only.** The paper's main tables use the single step and parallel recursion; sequential recursion (Eq. 3, Prompt 4) appears in one scaling figure. It is not built here: it would chain k one-wide steps, each also given every earlier round's evidence.
- **The selection pool is H's own runs plus each composed harness's run.** The paper says the selector sees "anonymized deliverables", some from the unmodified harness, without listing the pool. If the selector's reply names no valid id after one retry, the first run of H is taken and the fallback recorded.
- **One library per stream run, in its run folder.** The paper keeps one library per benchmark domain and starts it empty for each stream. A task that adopted H₀ itself and supported no lesson adds no entry.
