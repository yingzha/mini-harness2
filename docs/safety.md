# Safety

## Model-written code runs in a sandbox

From Lesson 2 on, the model writes code that we run: `run_python` calls (from the agent and its subagents) and plugin hooks. Each call runs in a fresh container (`Sandbox` in [steps/s02_executor.py](../steps/s02_executor.py)) that:

- sees only that rollout's workspace (read-only for plugins): not the source (so not the grader), not other rollouts;
- has no network, and none of our environment, so no API key;
- runs as an unprivileged user with every capability dropped and no way to gain more;
- is capped at 128 processes and 512 MB of memory;
- has its output cut to the start and end as it streams in, on our side, so printing gigabytes costs our container nothing;
- is removed when the call ends, which kills anything it left running.

[tests/test_s02_executor.py](../tests/test_s02_executor.py) checks each of these from inside a sandbox, and `tests/mutations/` proves each check fails when its protection is removed (see [testing.md](testing.md)).

## Grading runs in a sandbox too

A benchmark task's own checks are downloaded code, so they run in a sandbox, with the task's tests and gold answers mounted read-only. The workspace being graded is mounted at `/work`, not `/workspace`: their test module puts `/workspace` first on Python's import path, so an `eval_core.py` an agent wrote there would replace the real checks.

## No grade reaches the method

The method never sees a score. Every improvement session (editor, composer, selector, reflector) gets its evidence as a folder built only from a task, harnesses and execution records, none of which can hold a grade; grading lives in `benchmarks/`, which nothing in `steps/` imports. Those sessions can read their folder and write only a harness copy (or nothing); none of them runs code.

## What remains

- The `app` container holds the API key and the Docker socket, and whoever can use that socket controls Docker. That is acceptable only because no model-written code runs in `app`; keep it that way. File tools run there, but they only read and write files, refusing paths outside their folder.
- Containers share the kernel of Docker's VM, so a kernel exploit could escape one. A VM per call (gVisor, Firecracker) would be stronger; this project doesn't need it.
- Use a workspace-scoped API key with a spend limit.
