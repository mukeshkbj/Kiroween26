"""LlmProvider: the one interface every model backend implements (REQ-010).

A provider streams ``LlmEvent``s for one model call: text deltas, complete
tool-use blocks, usage and a stop reason. Messages use a small provider-neutral
shape; each adapter converts it to its SDK's format.

Message shapes (plain dicts, so scripted tests stay trivial):

* ``{"role": "user", "text": str}``
* ``{"role": "assistant", "text": str, "tool_uses": [{"id","name","input"}]}``
* ``{"role": "tool", "tool_use_id": str, "content": str}`` - ``content`` is always
  the untrusted-wrapped JSON string built by ``prompts.wrap_tool_result``.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Message = dict[str, Any]


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class TextDelta:
    text: str
    kind: Literal["text_delta"] = "text_delta"


@dataclass(frozen=True)
class ToolUse:
    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)
    kind: Literal["tool_use"] = "tool_use"


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    kind: Literal["usage"] = "usage"


@dataclass(frozen=True)
class Stop:
    reason: str  # "end_turn" | "tool_use" | "max_tokens" | ...
    kind: Literal["stop"] = "stop"


LlmEvent = TextDelta | ToolUse | Usage | Stop


class LlmError(Exception):
    """Provider failure. ``code`` is ``llm_unavailable`` or ``llm_error``.
    The message never contains a credential."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class LlmProvider(Protocol):
    name: str
    model: str

    def stream(self, messages: list[Message], tools: list[ToolDef], system: str) -> AsyncIterator[LlmEvent]: ...
