# Lessons

Read the lessons in order. Each `steps/sNN_*.py` opens with the paper sections it implements and the design choices behind it; its runnable demo is `demos/dNN_*.py`. Run demos as `docker compose run --rm app uv run --frozen python -m demos.<name>` (see [running.md](running.md)); costs are rough, from our own runs.

## L0: the model gateway

[steps/s00_llm.py](../steps/s00_llm.py) · paper: §2.1 the frozen model M, §3.1 roles, Fig. 6 compute

The `LLM` gateway every later lesson receives: `llm.call(role, …)`, with an executor model and a stronger editor model, a thread-safe usage and cost meter, and retries for transient API errors.

Try: `demos.d00_llm` (no API calls), then `--live`.

## L1: the harness

[steps/s01_harness.py](../steps/s01_harness.py) · paper: §2.1, Table 5, §D.1 to D.2, Prompt 1's rules

The harness as an immutable value: eight components on an editable surface, the stock harness in [base_harness/](../base_harness/), `validate` (the rules that discard a tree before any run), `diff`, and loading and writing.

Try: `demos.d01_harness` (no API calls).

## L2: the agent and its execution record

[steps/s02_executor.py](../steps/s02_executor.py) · paper: §2.1 A(q; M, H), §2.2.1 e = (τ, y), Table 5 activation, Table 7

The agent loop; file and `run_python` tools, `load_skill`, `run_subagent` and plugin hooks; the execution record; and the sandbox that model-written code runs in (see [safety.md](safety.md)).

Try: `demos.d02_executor` (live, about $0.01).

## L3: tasks, H₀ and grading

[steps/s03_tasks.py](../steps/s03_tasks.py), [benchmarks/workbuddy.py](../benchmarks/workbuddy.py) · paper: §2.1 the task stream, §D.1 H₀, Appendix B grading

A task is a request plus files. H₀ is the stock harness plus the benchmark's reference instructions. The deliverable is whatever the agent created or changed. A real task's own checks give the score (the fraction that pass), which the method itself never sees.

Try: `demos.d03_tasks` (no API calls), then `--live` (H₀ on the task, about 2 cents).

## L4: Propose

[steps/s04_propose.py](../steps/s04_propose.py), [prompts/](../prompts/) · paper: §2.2.1 Propose, §D.2 sessions, Prompts 1 and 2

Two editors, INV (how the agent works) and DOM (what a practitioner knows), each get the evidence as files in `context/` and edit their own copy of the harness; the files they leave are the candidate. An invalid tree goes back once with the validator's message, then falls back to the tree it started from.

Try: `demos.d04_propose` (no API calls), then `--live` (H₀ once, then both editors: about $2.50, 5 to 30 minutes).

## L5: Probe

[steps/s05_probe.py](../steps/s05_probe.py) · paper: §2.2.1 Probe

Each candidate runs once on the same task, side by side, under matched conditions: the same model, files and limits; only the harness differs. A contrast sets a probe's run beside the reference's: run stats, which harness components it actually used, and a diff of the deliverables. Facts, never a verdict.

Try: `demos.d05_probe` (live; reuses Lesson 4's candidates; a few cents).

## L6: Compose, and the contrastive step

[steps/s06_compose.py](../steps/s06_compose.py) · paper: §2.2.1 Compose, Eq. 1, Prompt 3

The composer reads the reference runs and every candidate (its tree, diff, editor's notes, probe run and contrasts) and edits a copy of the current harness into the successor H′, citing a trajectory moment for each decision. `contrastive_step` is Φ: propose, probe, compose, run H′; its record is ξ.

Try: `demos.d06_compose` (no API calls), then `--live` (one whole step: $2 to $4, 10 to 45 minutes).

## L7: recursion and selection

[steps/s07_recursion.py](../steps/s07_recursion.py) · paper: §2.2.2 Eq. 2, final selection, Prompt 5

Parallel recursion: k runs of H, then the contrastive step k wide (k editors per lane, k composers over the whole pool, each composed harness run). For k > 1, a selector picks one output blind, by shuffled id; H★ is the harness that produced it.

Try: `demos.d07_recursion` (no API calls), then `--live` (k = 2: $4 to $8, 15 to 60 minutes).

## L8: reflection and the library

[steps/s08_library.py](../steps/s08_library.py) · paper: §2.3 Eq. 4, §D.2 the library, Prompt 6

A read-only reflector reads the whole improvement record (every candidate, the rejected ones too, every composer's decisions, every run, and what was submitted) and writes what each edit did, with a verdict, and at most one transferable lesson. The library keeps H★'s full tree and an `EXPERIENCE.md` per task, with an index; later tasks' editors and composers read a copy.

Try: `demos.d08_library` (no API calls), then `--live` (k = 1 plus the reflector: $2 to $4).

## L9: the pipeline

[steps/s09_pipeline.py](../steps/s09_pipeline.py) · paper: §2.1 the stream, Fig. 3, §2.3 reuse, Table 1

The whole loop over a stream of tasks: for each task, recursion from H₀ with the library as it stands, then reflection, then the library update. Only the library carries from one task to the next. The demo then scores the stream Table 1-style, H₀'s base runs against the delivered output, for you only.

Try: `demos.d09_pipeline` (no API calls), then `--live` (two tasks at k = 1: about $6, 30 to 60 minutes). With one run per harness, the table it prints shows the mechanism, not a measured gain: the same harness run twice can differ by more than an edit's effect.
