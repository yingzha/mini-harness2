"""An offline Anthropic API for tests.

Tests use the *real* SDK client, pointed at a scripted HTTP transport instead of
the network. Our requests are serialised by the real SDK and the canned replies
are parsed into real SDK types, so a misspelt parameter or a response shape we
handle wrongly fails here instead of on the first live run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import anthropic
import httpx2


@dataclass(frozen=True)
class SentRequest:
    headers: dict[str, str]
    body: dict[str, Any]


class ScriptedAPI:
    """Answers each POST /v1/messages with the next queued reply, or with
    `replies(body)` when given a function (for sessions that run side by side,
    whose order is not fixed), and records the request."""

    def __init__(self, replies: list[dict] | Callable[[dict], dict]) -> None:
        self._replies = replies if callable(replies) else list(replies)
        self.requests: list[SentRequest] = []

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.requests.append(SentRequest(dict(request.headers), body))
        if callable(self._replies):
            return httpx2.Response(200, json=self._replies(body))
        if not self._replies:
            raise AssertionError("ScriptedAPI ran out of replies")
        return httpx2.Response(200, json=self._replies.pop(0))

    def client(self, default_headers: Mapping[str, str] | None = None) -> anthropic.Anthropic:
        return anthropic.Anthropic(
            api_key="test-key",          # explicit, so a real key in the environment is never used
            base_url="http://scripted",
            max_retries=0,
            default_headers=default_headers,
            http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(self._handle)),
        )


def reply(
    *content: dict,
    model: str,
    stop_reason: str = "end_turn",
    input_tokens: int = 10,
    output_tokens: int = 5,
    cache_read: int | None = None,
    cache_write: int | None = None,
    thinking: int | None = None,
) -> dict:
    """A Messages API response body, as the server would send it."""
    usage: dict[str, Any] = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    if cache_read is not None:
        usage["cache_read_input_tokens"] = cache_read
    if cache_write is not None:
        usage["cache_creation_input_tokens"] = cache_write
    if thinking is not None:
        usage["output_tokens_details"] = {"thinking_tokens": thinking}
    return {
        "id": "msg_scripted", "type": "message", "role": "assistant", "model": model,
        "content": list(content), "stop_reason": stop_reason, "stop_sequence": None, "usage": usage,
    }


def text(t: str) -> dict:
    return {"type": "text", "text": t}


def tool_use(id: str, name: str, input: dict) -> dict:
    return {"type": "tool_use", "id": id, "name": name, "input": input}


def thinking(signature: str, thinking: str = "") -> dict:
    """A thinking block. Its text is empty by default, as the API returns it unless asked otherwise."""
    return {"type": "thinking", "thinking": thinking, "signature": signature}
