"""Anthropic provider (REQ-009, REQ-010, REQ-011).

Conversion to and from the SDK is in pure functions so recorded payloads can be
tested without a network. Errors are mapped to ``LlmError`` using only the
exception *class* and HTTP status, never ``str(exc)``: SDK messages can echo
request details, and no key may reach a log, an event or an error message.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from ..config import Settings
from .base import LlmError, LlmEvent, Message, Stop, TextDelta, ToolDef, ToolUse, Usage

log = logging.getLogger("seance_agent.llm.anthropic")


def to_anthropic_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Neutral messages -> Anthropic. Consecutive tool results become one user
    message of ``tool_result`` blocks, directly after the assistant's ``tool_use``."""
    out: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    def flush() -> None:
        if results:
            out.append({"role": "user", "content": list(results)})
            results.clear()

    for m in messages:
        role = m["role"]
        if role == "tool":
            results.append({"type": "tool_result", "tool_use_id": m["tool_use_id"], "content": m["content"]})
            continue
        flush()
        if role == "user":
            out.append({"role": "user", "content": m["text"]})
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.get("text"):
                blocks.append({"type": "text", "text": m["text"]})
            for u in m.get("tool_uses", []):
                blocks.append({"type": "tool_use", "id": u["id"], "name": u["name"], "input": u["input"]})
            if blocks:
                out.append({"role": "assistant", "content": blocks})
    flush()
    return out


def to_anthropic_tools(tools: list[ToolDef]) -> list[dict[str, Any]]:
    return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]


def map_error(exc: Exception) -> LlmError:
    """Class and status only. Never the exception text."""
    import anthropic

    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return LlmError("llm_unavailable", "The language model rejected the configured credentials.")
    if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return LlmError("llm_unavailable", "The language model could not be reached.")
    status = getattr(exc, "status_code", None)
    return LlmError("llm_error", f"The language model request failed{f' (HTTP {status})' if status else ''}.")


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings: Settings, *, client: Any | None = None):
        self.model = settings.llm_model
        self._max_tokens = settings.llm_max_tokens
        if client is not None:
            self._client = client
        else:
            import anthropic

            key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
            self._client = anthropic.AsyncAnthropic(api_key=key, timeout=settings.llm_timeout_s)

    def __repr__(self) -> str:  # no client, no key
        return f"AnthropicProvider(model={self.model!r})"

    async def stream(self, messages: list[Message], tools: list[ToolDef], system: str) -> AsyncIterator[LlmEvent]:
        try:
            async with self._client.messages.stream(
                model=self.model, max_tokens=self._max_tokens, system=system,
                messages=to_anthropic_messages(messages), tools=to_anthropic_tools(tools),
            ) as stream:
                async for event in stream:
                    if getattr(event, "type", None) == "text":
                        yield TextDelta(event.text)
                final = await stream.get_final_message()
        except LlmError:
            raise
        except Exception as exc:  # noqa: BLE001 - mapped without echoing its text
            log.warning("anthropic call failed: %s", type(exc).__name__)
            raise map_error(exc) from None
        for block in final.content:
            if getattr(block, "type", None) == "tool_use":
                yield ToolUse(block.id, block.name, dict(block.input))
        yield Usage(final.usage.input_tokens, final.usage.output_tokens)
        yield Stop(str(final.stop_reason))
