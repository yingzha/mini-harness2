"""Default settings for mini-Harness².

This module is data only: immutable values, no behaviour, no I/O. Lessons never
read it directly. Entry points (each lesson's `__main__`, the pipeline, the
tests) pick values from here and pass them in explicitly.

Credentials are not configured here. The Anthropic SDK resolves them from the
environment (`ANTHROPIC_API_KEY`); under Docker, compose injects that from .env.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class RoleSpec:
    """Which model plays a role, and how hard it thinks."""
    model: str
    effort: str  # low | medium | high | xhigh | max


@dataclass(frozen=True)
class Price:
    """USD per 1M tokens. Estimates for the usage meter, not billing truth."""
    input: float
    output: float
    cache_read: float
    cache_write: float
    # Some models bill long prompts at a higher tier.
    long_prompt_threshold: int | None = None
    long_prompt: Price | None = None


@dataclass(frozen=True)
class LLMSettings:
    roles: Mapping[str, RoleSpec]
    prices: Mapping[str, Price]
    server_fallback_models: frozenset[str]  # models that accept fallbacks="default"
    server_fallback_beta: str
    max_tokens_per_turn: int


@dataclass(frozen=True)
class RolloutLimits:
    max_turns: int            # model turns per rollout (§D.1: "#Steps")
    subagent_max_turns: int   # turns a delegated subagent may take
    tool_timeout_s: float     # per run_python call or plugin hook


# ---------------------------------------------------------------------------
# Models and roles (paper §3.1 / §D.2)
#
# The paper runs a frozen *executor* (Gemini 3.5 Flash / GLM-5) inside the
# harness, and a stronger *editor* (Claude Opus 4.8, high reasoning effort)
# for every improvement session: editors, composer, selector, reflector.
# We mirror that split with a cheap executor and a strong editor.
# ---------------------------------------------------------------------------
_EXECUTOR = RoleSpec(model="claude-haiku-5-5", effort="medium")
_EDITOR = RoleSpec(model="claude-opus-5-5", effort="high")

LLM_SETTINGS = LLMSettings(
    roles=MappingProxyType({
        "executor": _EXECUTOR,   # A(q; M, H): runs the task inside the harness
        "editor": _EDITOR,       # Propose: INV / DOM harness editors
        "composer": _EDITOR,     # Compose: merges candidate edits
        "selector": _EDITOR,     # Final selection over anonymised deliverables
        "reflector": _EDITOR,    # Harnessing-level recursion: writes library lessons
    }),
    prices=MappingProxyType({
        "claude-opus-5-5": Price(4.00, 20.00, 0.20, 5.00),
        "claude-haiku-5-5": Price(
            0.10, 0.50, 0.01, 0.125,
            long_prompt_threshold=100_000,
            long_prompt=Price(0.50, 2.50, 0.05, 0.625),
        ),
    }),
    # Haiku 5.5 has no server-side refusal fallback, so it never gets the parameter.
    server_fallback_models=frozenset({"claude-opus-5-5"}),
    server_fallback_beta="server-side-fallback-2026-07-01",
    # Non-streaming per-turn cap; keeps each request under the SDK's HTTP timeout.
    max_tokens_per_turn=16000,
)

# ---------------------------------------------------------------------------
# Rollout limits (§D.1 caps each rollout at 200 model turns; we go smaller)
# ---------------------------------------------------------------------------
ROLLOUT_LIMITS = RolloutLimits(max_turns=40, subagent_max_turns=20, tool_timeout_s=60)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
BASE_HARNESS_DIR = ROOT / "base_harness"
RUNS_DIR = ROOT / "runs"
