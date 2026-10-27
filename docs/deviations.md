# Deviations from the paper

Each one follows from the same question: does the paper's rule guard a failure that can happen in *this* runtime, at this scale?

## The executor and its harness

- **The executor is Claude Haiku 5.5 at low effort**, standing in for the paper's weaker executors (Gemini 3.5 Flash, GLM-5). On the ticket task, one run at medium effort passed 271 of 273 checks, which leaves the improver almost nothing to work on; one run at low effort passed 254. These are single runs on one task: the same harness run twice on it has differed by 15 checks.
- **A small custom agent instead of OpenCode or Codex.** Tools: `list_files`, `read_file`, `write_file`, `run_python` (no shell), plus `load_skill` and `run_subagent` when the harness has skills or subagents. A rollout is capped at 40 turns (the paper: 200) and each code run at 60 s; there is no separate wall-clock cap, since those two already bound it.
- **Plugins are Python** (`plugin/<name>.py`), not TypeScript, because our executor is a Python loop. They have two hooks: `after_tool` (append a note to a tool result) and `before_finish` (keep the agent working, at most twice). Subagents can't delegate again and don't run plugins.
- **No "template braces" rule.** The paper forbids `{{` and `{%` in always-on text because its runtime renders those files with Jinja. Ours doesn't template, so there is nothing to break.
- **No frontmatter `name` or `mode: subagent`.** OpenCode needs them to load agents; our runtime finds skills and subagents by their folder. Only `description` is required, because the agent reads it to decide what to use.
- **Skill helper scripts must be `.py`**, since `run_python` is the only way our executor runs code.
- **The harness's scripts sit in the workspace while the agent runs**, at their own paths, so text that names `scripts/check.py` is right. When the rollout ends they are taken out again, with the folders only they needed, because the finished workspace is what gets graded and some Office tasks fail any stray script (two of the 14 did, on the first `text-office` stream). A script the agent changed stays, as part of what it produced.

## Tasks and evaluation

- **Real tasks, but few.** Lessons 3 to 8 use one WorkBuddy-Bench Office task, `service-channel-ticket-daily` (a daily ticket report from a CSV export, a JSON snapshot and a guidance document). Lesson 9's stream adds a sibling, `market-daily-brief-a-share-recap` (a daily market recap from a frozen filing room of CSV, JSON and Markdown); both are text in, Markdown out. A larger stream, `text-office`, runs the 14 of the 50 Office tasks this runtime can attempt and grade: their files are text in and text out, and their checks need only the standard library. The other 36 need spreadsheet, document or slide files, which are out of reach here: the agent's Python has only the standard library, and deliverables are handled as text. One of the 14, `monitoring-weekly-draft-followup`, has 4 checks (of 100) that read the trajectory log the benchmark's own runner writes; this runtime writes none, so they fail for every harness alike. Checks on the agent's final reply do run: grading gets it where the benchmark's runner saves it. The two lesson tasks were watched while the prompts were adapted to this runtime, so the other 12 are the only unseen ones. The paper runs every test task of WorkBuddy-Bench, JobBench and LAB, three times each.
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
