"""Lesson 0 tests. Each docstring names the real failure the test guards against."""

from dataclasses import replace
from types import MappingProxyType

import pytest
from anthropic.types.beta import BetaUsage

import config
from config import Price
from steps.s00_llm import LLM, cost_of, workspace_headers
from tests.scripted_api import ScriptedAPI, reply, text

SETTINGS = config.LLM_SETTINGS
EXECUTOR = SETTINGS.roles["executor"].model
EDITOR = SETTINGS.roles["editor"].model
USER = [{"role": "user", "content": "x"}]


def test_requests_are_valid_for_the_real_sdk():
    """Guards: a misspelt or renamed request parameter, a header on the wrong
    model, or a reply we parse wrongly. Without this they only fail live.
    Also: Haiku has no server-side fallback, so it must never be sent one."""
    api = ScriptedAPI([reply(text("a"), model=EXECUTOR), reply(text("b"), model=EDITOR)])
    llm = LLM(api.client(), SETTINGS)
    tool = {"name": "read_file", "description": "Read a file.",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}}

    executor_reply = llm.call("executor", "sys", USER)
    llm.call("editor", "sys", USER, tools=[tool])

    executor, editor = api.requests
    assert executor.body["model"] == EXECUTOR
    assert executor.body["output_config"] == {"effort": SETTINGS.roles["executor"].effort}
    assert executor.body["cache_control"] == {"type": "ephemeral"}
    assert "fallbacks" not in executor.body and "anthropic-beta" not in executor.headers

    assert editor.body["model"] == EDITOR
    assert editor.body["fallbacks"] == "default"
    assert SETTINGS.server_fallback_beta in editor.headers["anthropic-beta"]
    assert editor.body["tools"][0]["name"] == "read_file"

    assert executor_reply.content[0].text == "a"


def test_meter_costs_follow_reported_usage():
    """Guards: cost accounting drifting from the API's usage numbers (the
    Fig. 6 compute comparison relies on it): totals that keep only the last
    call instead of adding up every call, and the real API omitting cache
    fields entirely, which arrive as None rather than 0."""
    settings = replace(SETTINGS, prices=MappingProxyType({
        EXECUTOR: Price(input=1, output=2, cache_read=0.1, cache_write=1.25),
        EDITOR: Price(input=10, output=20, cache_read=1, cache_write=12.5),
    }))
    api = ScriptedAPI([
        reply(text("a"), model=EXECUTOR, input_tokens=1000, output_tokens=500),  # no cache fields
        reply(text("a"), model=EXECUTOR, input_tokens=2000, output_tokens=0),
        reply(text("b"), model=EDITOR, input_tokens=100, output_tokens=10, cache_read=1000, cache_write=200),
    ])
    llm = LLM(api.client(), settings)
    llm.call("executor", "sys", USER)
    llm.call("executor", "sys", USER)
    llm.call("editor", "sys", USER)

    usage = llm.meter.snapshot()
    assert usage["executor"].calls == 2
    assert usage["executor"].input_tokens == 3000
    assert usage["executor"].cost_usd == pytest.approx((1000 * 1 + 500 * 2 + 2000 * 1) / 1e6)
    assert usage["editor"].cost_usd == pytest.approx((100 * 10 + 10 * 20 + 1000 * 1 + 200 * 12.5) / 1e6)
    assert usage["editor"].cache_read_tokens == 1000


def test_fallback_served_by_an_unpriced_model_does_not_crash_the_run():
    """Guards: a refusal fallback answered by a model missing from the price
    table (e.g. claude-opus-4-8) raising KeyError in the middle of a pipeline.
    It is priced as the model we asked for."""
    api = ScriptedAPI([reply(text("ok"), model="claude-opus-4-8", input_tokens=0, output_tokens=1_000_000)])
    llm = LLM(api.client(), SETTINGS)
    llm.call("editor", "sys", USER)
    assert llm.meter.snapshot()["editor"].cost_usd == pytest.approx(SETTINGS.prices[EDITOR].output)


def test_long_prompt_tier_starts_strictly_above_threshold_and_counts_cached_tokens():
    """Guards: an off-by-one at the tier boundary, and forgetting that cached
    tokens are part of the prompt's length."""
    price = Price(input=1, output=0, cache_read=1, cache_write=1,
                  long_prompt_threshold=100, long_prompt=Price(input=10, output=0, cache_read=10, cache_write=10))
    assert cost_of(price, BetaUsage(input_tokens=100, output_tokens=0)) == pytest.approx(100 * 1 / 1e6)
    assert cost_of(price, BetaUsage(input_tokens=101, output_tokens=0)) == pytest.approx(101 * 10 / 1e6)
    assert cost_of(price, BetaUsage(input_tokens=1, output_tokens=0, cache_read_input_tokens=100)) == \
        pytest.approx((1 + 100) * 10 / 1e6)


def test_blank_workspace_id_sends_no_header():
    """Guards: .env.example ships `ANTHROPIC_WORKSPACE_ID=` blank. An empty
    anthropic-workspace-id header would make every request fail with a 400."""
    for environ, expected in [({"ANTHROPIC_WORKSPACE_ID": ""}, None),
                              ({"ANTHROPIC_WORKSPACE_ID": "wrkspc_1"}, "wrkspc_1")]:
        api = ScriptedAPI([reply(text("ok"), model=EXECUTOR)])
        LLM(api.client(default_headers=workspace_headers(environ)), SETTINGS).call("executor", "sys", USER)
        assert api.requests[0].headers.get("anthropic-workspace-id") == expected


def test_the_real_client_retries_as_configured(monkeypatch):
    """Guards: one transient API error (a dropped connection, an overload)
    ending an hour-long run, because the client gave up after the SDK's
    default two retries instead of the configured number."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")   # never sent: no request is made
    settings = replace(config.LLM_SETTINGS, max_retries=7)
    assert LLM.from_env(settings).client.max_retries == 7
