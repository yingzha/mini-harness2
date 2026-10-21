"""Lesson 0: Talking to the frozen model M.

Paper anchors
-------------
* §2.1: "Let M be a model with frozen parameters." Nothing in Harness² ever
  changes M. Everything that improves is *around* the model (the harness).
* §3.1 / §D.2: two kinds of model sessions. The *executor* does the task
  inside the harness; the *editor* (also composer, selector, reflector) runs
  every improvement session at high reasoning effort.
* Fig. 6: the compute/performance trade-off counts every token spent before
  the final deliverable. `UsageMeter` is that accounting.

What this module gives the later lessons
----------------------------------------
* `LLM`: the gateway to the model for every role. It owns the SDK client, the
  settings and a usage meter. Nothing here is global: an entry point builds one
  `LLM` per run and passes it to whatever needs a model.
* `UsageMeter`: thread-safe, per-role token and dollar totals.
* `build_request`, `cost_of`, `text_of`, `workspace_headers`: pure functions,
  testable without a client.

Two API rules every later lesson relies on
------------------------------------------
1. Append `response.content` back into `messages` **unchanged**. It may hold
   thinking blocks, which must be returned as-is (preserved thinking).
2. History is append-only: never edit an earlier message. New information
   (a tool result, a plugin's nudge) always goes in a *new* message.
"""

from __future__ import annotations

import dataclasses
import os
import threading
from dataclasses import dataclass
from typing import Any, Mapping

import anthropic
from anthropic.types.beta import BetaMessage, BetaUsage

from config import LLMSettings, Price

WORKSPACE_ENV_VAR = "ANTHROPIC_WORKSPACE_ID"


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def build_request(
    settings: LLMSettings,
    role: str,
    system: str,
    messages: list,
    tools: list | None = None,
) -> dict[str, Any]:
    """The kwargs for one Messages API request made by `role`."""
    spec = settings.roles[role]  # an unknown role is a bug: fail with KeyError
    request: dict[str, Any] = {
        "model": spec.model,
        "max_tokens": settings.max_tokens_per_turn,
        "system": system,
        "messages": messages,
        # Auto-caching: caches the longest prefix of this request. In a tool loop
        # each turn re-sends the previous turns, so they are read from cache.
        "cache_control": {"type": "ephemeral"},
        "output_config": {"effort": spec.effort},
    }
    if tools:
        request["tools"] = tools
    if spec.model in settings.server_fallback_models:
        # If a safety classifier declines, the API re-runs the request on a
        # recommended fallback model instead of returning a refusal.
        request["betas"] = [settings.server_fallback_beta]
        request["fallbacks"] = "default"
    return request


def cost_of(price: Price, usage: BetaUsage) -> float:
    """Estimated USD for one response's token usage."""
    inp = usage.input_tokens or 0
    out = usage.output_tokens or 0
    cache_read = usage.cache_read_input_tokens or 0
    cache_write = usage.cache_creation_input_tokens or 0
    tier = price
    if (
        price.long_prompt is not None
        and price.long_prompt_threshold is not None
        and inp + cache_read + cache_write > price.long_prompt_threshold
    ):
        tier = price.long_prompt
    return (
        inp * tier.input
        + out * tier.output
        + cache_read * tier.cache_read
        + cache_write * tier.cache_write
    ) / 1_000_000


def text_of(response: BetaMessage) -> str:
    """Concatenate the visible text blocks (thinking blocks are skipped)."""
    return "".join(b.text for b in response.content if b.type == "text")


def workspace_headers(environ: Mapping[str, str]) -> dict[str, str]:
    """An API key that isn't scoped to a workspace must name one on every request."""
    workspace = environ.get(WORKSPACE_ENV_VAR)
    return {"anthropic-workspace-id": workspace} if workspace else {}


# ---------------------------------------------------------------------------
# Usage accounting (Fig. 6: "all tokens spent before the final deliverable")
# ---------------------------------------------------------------------------

@dataclass
class RoleUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0


class UsageMeter:
    """Per-role token/cost totals. Safe to share across threads (parallel probes)."""

    def __init__(self, prices: Mapping[str, Price]) -> None:
        self._prices = prices
        self._lock = threading.Lock()
        self._by_role: dict[str, RoleUsage] = {}

    def record(self, role: str, model: str, usage: BetaUsage) -> float:
        cost = cost_of(self._prices[model], usage)  # an unpriced model is a config bug
        with self._lock:
            r = self._by_role.setdefault(role, RoleUsage())
            r.calls += 1
            r.input_tokens += usage.input_tokens or 0
            r.output_tokens += usage.output_tokens or 0
            r.cache_read_tokens += usage.cache_read_input_tokens or 0
            r.cache_write_tokens += usage.cache_creation_input_tokens or 0
            r.cost_usd += cost
        return cost

    def snapshot(self) -> dict[str, RoleUsage]:
        """A consistent copy of the per-role totals."""
        with self._lock:
            return {role: dataclasses.replace(r) for role, r in self._by_role.items()}

    def report(self) -> str:
        snap = self.snapshot()
        rows = [f"{'role':<10} {'calls':>5} {'in':>9} {'out':>8} {'cache_rd':>9} {'cache_wr':>9} {'$':>8}"]
        for role, r in sorted(snap.items()):
            rows.append(
                f"{role:<10} {r.calls:>5} {r.input_tokens:>9} {r.output_tokens:>8} "
                f"{r.cache_read_tokens:>9} {r.cache_write_tokens:>9} {r.cost_usd:>8.4f}"
            )
        total = sum(r.cost_usd for r in snap.values())
        rows.append(f"{'total':<10} {'':>5} {'':>9} {'':>8} {'':>9} {'':>9} {total:>8.4f}")
        return "\n".join(rows)


# ---------------------------------------------------------------------------
# The gateway every later lesson receives
# ---------------------------------------------------------------------------

class LLM:
    """Sends requests for any role and meters them. Thread-safe."""

    def __init__(
        self,
        client: anthropic.Anthropic,
        settings: LLMSettings,
        meter: UsageMeter | None = None,
    ) -> None:
        self.client = client
        self.settings = settings
        self.meter = meter if meter is not None else UsageMeter(settings.prices)

    @classmethod
    def from_env(cls, settings: LLMSettings) -> LLM:
        """Real client. The SDK resolves credentials itself (ANTHROPIC_API_KEY, ...)."""
        client = anthropic.Anthropic(default_headers=workspace_headers(os.environ))
        return cls(client, settings)

    def call(self, role: str, system: str, messages: list, tools: list | None = None) -> BetaMessage:
        request = build_request(self.settings, role, system, messages, tools)
        response = self.client.beta.messages.create(**request)
        # A server-side fallback may be served by another model; price it if we
        # know it, otherwise by the model we asked for.
        model = response.model if response.model in self.settings.prices else request["model"]
        self.meter.record(role, model, response.usage)
        return response
