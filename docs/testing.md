# Testing

## The tests

`tests/` runs offline, with no API key, but it needs Docker: some tests start real sandbox containers.

```bash
docker compose run --rm app                                                   # every test
docker compose run --rm app uv run --frozen pytest tests/test_s01_harness.py  # one file
```

- **The real SDK, a scripted server.** Tests use the real Anthropic SDK client pointed at a scripted HTTP transport ([tests/scripted_api.py](../tests/scripted_api.py)). Our requests are serialised by the SDK and the canned replies are parsed into real SDK types, so a misspelt parameter or a response shape we handle wrongly fails here, not on the first live run.
- **Answers by who is asking.** Sessions that run side by side don't call in a fixed order, so whole-pipeline tests answer each request by the session that sent it, recognised by its system prompt ([tests/routes.py](../tests/routes.py)).
- **The real sandbox.** Tests that run model-written code use real sandbox containers, exactly as rollouts do.
- **One named failure per test.** Each test's docstring names the real failure it guards against.

## Do the tests actually catch bugs?

Passing tests prove little on their own. [tools/mutate.py](../tools/mutate.py) plants each bug listed in `tests/mutations/` into a temporary copy of the project and checks that the test named for it fails. It also runs *controls*: changes that alter nothing, which no test may fail on. The real files are never touched.

```bash
docker compose run --rm app uv run --frozen python -m tools.mutate                                  # every list
docker compose run --rm app uv run --frozen python -m tools.mutate tests/mutations/s01_harness.py   # one module
```

When you add a test, add the bug it guards against to the matching list in `tests/mutations/`.
