# Design

## Code layout

- `steps/sNN_*.py`: one lesson each, the method itself. Pure library code: no globals, no CLI, no side effects on import. Dependencies (the `LLM` gateway, the sandbox, a random source, folders) are passed in explicitly.
- `base_harness/`: the stock harness every task starts from, before a benchmark's reference instructions turn it into H₀.
- `prompts/`: the improver's prompts (Appendix H), adapted to this runtime: [editor.md](../prompts/editor.md) with a dimension section ([editor_inv.md](../prompts/editor_inv.md), [editor_dom.md](../prompts/editor_dom.md)), [composer.md](../prompts/composer.md), [harness_rules.md](../prompts/harness_rules.md) (the sections those two share), [selector.md](../prompts/selector.md) and [reflector.md](../prompts/reflector.md).
- `benchmarks/`: real tasks to run the method on, and the benchmark's own way of grading them. [workbuddy.py](../benchmarks/workbuddy.py) loads a WorkBuddy-Bench task and runs its checks. Nothing in `steps/` imports from here.
- `demos/dNN_*.py`: the runnable entry point for each lesson, and the only place that reads `config.py` and builds real clients.
- `config.py`: immutable default settings (frozen dataclasses), with no behaviour.
- `tests/`, `tests/mutations/`, `tools/mutate.py`: see [testing.md](testing.md).
- `data/`: datasets you download; `runs/`: what live runs leave behind. Both are git-ignored.

## Rules the code follows

- **Explicit dependencies.** Every function gets what it uses as arguments; nothing reaches for a global or reads `config.py` on its own.
- **Values, not objects with state.** A harness, a task, an execution record, a step record: all frozen. Most functions are pure; the few that touch disk say so.
- **One way to do each thing.** Later lessons reuse earlier ones instead of copying them: the composer is the editors' session on more evidence, parallel recursion is the contrastive step made k wide, and the selector's retry is the editors' `SendBackOnce`.
- **The method never sees a score.** Grading lives in `benchmarks/`, and every session's evidence is built from values that can't hold a grade (see [safety.md](safety.md)).
- **Every test guards a named failure, proven by mutation** (see [testing.md](testing.md)).

## Where the paper's symbols live

| Paper | Code |
|---|---|
| M, the frozen model | the `LLM` gateway, by role ([s00](../steps/s00_llm.py)) |
| H, a harness | `Harness`, a mapping from path to text ([s01](../steps/s01_harness.py)) |
| H₀ | `initial_harness(stock, reference)` ([s03](../steps/s03_tasks.py)) |
| A(q; M, H), one rollout | `execute` ([s02](../steps/s02_executor.py)) |
| e = (τ, y) | `ExecutionRecord`: `.steps` is τ, `.deliverable` is y |
| an INV or DOM candidate | `Candidate`, from `propose` ([s04](../steps/s04_propose.py)) |
| a probe and its contrast | `probe`, `contrast` ([s05](../steps/s05_probe.py)) |
| Φ, the contrastive step (Eq. 1) | `contrastive_step` ([s06](../steps/s06_compose.py)) |
| ξ, the step record | `StepRecord` |
| H′, the successor | `StepRecord.composed[j].harness` |
| Eq. 2, parallel recursion | `parallel_recursion` ([s07](../steps/s07_recursion.py)) |
| H★, the adopted harness | `Recursion.adopted` |
| D_t, the improvement record | `Recursion` (with the step record and the selection) |
| R_t, the improvement harness | the prompts in `prompts/` plus the stream's library folder |
| Update (Eq. 4) | `reflect`, then `update_library` ([s08](../steps/s08_library.py)) |
| the stream q₁ … q_N | `run_stream` ([s09](../steps/s09_pipeline.py)) |
