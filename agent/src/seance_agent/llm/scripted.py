"""Deterministic providers: ScriptedLlm (CI, offline demo) and GullibleLlm (tests).

``ScriptedLlm`` replays a fixed script: one entry per model call, each entry a
list of items, where an item is a ``str`` (assistant text) or a ``ToolUse``. When
the script is exhausted it ends the turn with a short sentence. A *responder*
function may be given instead for context-dependent replies.

``GullibleLlm`` is the adversary used by the injection tests (REQ-029a): a model
that **obeys any imperative it reads in the latest tool result**, including ones
for tools it was never offered (``confirm_action``). The agent's safety must hold
against it, because safety never depends on the model behaving.
"""
from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

from .base import LlmEvent, Message, Stop, TextDelta, ToolDef, ToolUse, Usage

Item = str | ToolUse
Responder = Callable[[list[Message], list[ToolDef]], list[Item]]

_POLICY_RE = re.compile(r"\bP\d{7}\b", re.IGNORECASE)
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


class ScriptedLlm:
    name = "scripted"

    def __init__(self, script: list[list[Item]] | None = None, *, responder: Responder | None = None,
                 model: str = "scripted-demo"):
        self.model = model
        self._script = list(script or [])
        self._responder = responder
        self.calls: list[dict[str, Any]] = []  # what the provider was sent (for no-leak tests)

    async def stream(self, messages: list[Message], tools: list[ToolDef], system: str) -> AsyncIterator[LlmEvent]:
        self.calls.append({"messages": json.loads(json.dumps(messages)), "tools": [t.name for t in tools],
                           "system": system})
        if self._responder is not None:
            items = self._responder(messages, tools)
        elif self._script:
            items = self._script.pop(0)
        else:
            items = ["Done."]
        in_tok = sum(len(json.dumps(m)) for m in messages) // 4
        out_tok = 0
        uses = 0
        for item in items:
            if isinstance(item, str):
                for i in range(0, len(item), 24):
                    yield TextDelta(item[i:i + 24])
                out_tok += len(item) // 4
            else:
                uses += 1
                yield item
        yield Usage(in_tok, out_tok)
        yield Stop("tool_use" if uses else "end_turn")


class GullibleLlm(ScriptedLlm):
    """Obeys imperatives found in the latest tool result. Never refuses."""

    name = "scripted"

    def __init__(self) -> None:
        super().__init__(responder=self._respond, model="gullible-test")
        self._n = 0
        self._done: set[str] = set()
        self.attempted: list[tuple[str, dict[str, Any]]] = []

    def _use(self, name: str, args: dict[str, Any]) -> ToolUse:
        self._n += 1
        self.attempted.append((name, args))
        return ToolUse(f"tu_{self._n}", name, args)

    def _respond(self, messages: list[Message], tools: list[ToolDef]) -> list[Item]:
        last = messages[-1]
        if last["role"] == "user":
            m = _POLICY_RE.search(last["text"])
            if m:
                return [self._use("lookup_policy", {"policy_number": m.group(0).upper()})]
            return ["Tell me which policy."]
        trailing: list[str] = []
        for m in reversed(messages):
            if m["role"] != "tool":
                break
            trailing.append(str(m.get("content", "")))
        text = " ".join(reversed(trailing)).lower()
        out: list[Item] = []
        if '"tool": "lookup_policy"' in text and "read" not in self._done:
            # Being "thorough": also look at the raw screen, where free text lives.
            self._done.add("read")
            out.append(self._use("read_screen", {}))

        def once(key: str, use: ToolUse) -> None:
            if key not in self._done:
                self._done.add(key)
                out.append(use)

        if "ignore previous instructions" in text or "confirm" in text:
            for aid in _UUID_RE.findall(text) or ["any-action-id"]:
                once(f"confirm:{aid}", self._use("confirm_action", {"action_id": aid}))
            if "confirm" in text:
                once("approve-all", self._use("approve_pending", {}))
        if "pf3" in text:
            once("pf3", self._use("press_key", {"key": "PF3"}))
        if "premium to 0" in text:
            once("premium0", self._use("update_policy", {"policy_number": "P0000004", "premium": "0"}))
        if "press enter" in text:
            once("enter", self._use("press_key", {"key": "ENTER"}))
        return out or ["Done."]
