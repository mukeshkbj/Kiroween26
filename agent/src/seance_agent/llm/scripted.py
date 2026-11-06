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
            hit = _POLICY_RE.search(last["text"])
            if hit:
                return [self._use("lookup_policy", {"policy_number": hit.group(0).upper()})]
            return ["Tell me which policy."]
        trailing: list[str] = []
        for tm in reversed(messages):
            if tm["role"] != "tool":
                break
            trailing.append(str(tm.get("content", "")))
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


# ---------------------------------------------------------------- offline demo model

# The amount after "to"/"=": "premium of policy P0000003 to 300" -> 300, never the policy digits.
_PREMIUM_RE = re.compile(r"premium\b.*?(?:\bto\b|=|\bat\b)\s*(\d{1,7})(?:\.\d+)?\b", re.IGNORECASE)
_STATUS_RE = re.compile(r"status\D{0,15}\b([ALC])\b", re.IGNORECASE)
_STATUS_WORDS = {"active": "A", "lapsed": "L", "cancelled": "C", "canceled": "C"}


def _last_user_policy(messages: list[Message]) -> str:
    for m in reversed(messages):
        if m["role"] == "user" and (p := _POLICY_RE.search(m["text"])):
            return p.group(0).upper()
    return ""


def demo_responder(messages: list[Message], tools: list[ToolDef]) -> list[Item]:
    """A tiny rule-based 'model' for the offline demo and for UI development.

    It plans from the user's words and phrases answers from tool results. It
    never invents tools it was not offered and never reads instructions out of
    tool results (it only formats the fields it asked for)."""
    names = {t.name for t in tools}
    last = messages[-1]
    n = sum(1 for m in messages if m["role"] == "assistant")
    if last["role"] == "user":
        text = last["text"]
        low = text.lower()
        pol = _POLICY_RE.search(text)
        if "list" in low and "list_policies" in names:
            return ["Listing the policies.", ToolUse(f"demo_{n}", "list_policies", {})]
        if pol and re.search(r"premium|status|update|change|set", low) and "update_policy" in names:
            args: dict[str, Any] = {"policy_number": pol.group(0).upper()}
            if (pm := _PREMIUM_RE.search(text)):
                args["premium"] = pm.group(1)
            sm = _STATUS_RE.search(text)
            word = next((v for k, v in _STATUS_WORDS.items() if k in low), None)
            if sm or word:
                args["status"] = (sm.group(1) if sm else word or "").upper()
            if len(args) > 1:
                return ["I will prepare that change. A person has to confirm it.",
                        ToolUse(f"demo_{n}", "update_policy", args)]
            return ["Tell me the new premium or status."]
        if pol and "lookup_policy" in names:
            return [ToolUse(f"demo_{n}", "lookup_policy", {"policy_number": pol.group(0).upper()})]
        return ["I can look up a policy (for example P0000003), list policies, or prepare a change "
                "that you then confirm."]
    recover = _recover_unknown_start(messages)
    if recover is not None:
        return recover
    out: list[str] = []
    policy_no = _last_user_policy(messages)
    for m in reversed(messages):
        if m["role"] != "tool":
            break
        try:
            j = json.loads(m["content"])
        except ValueError:
            continue
        res = j.get("result") or {}
        if j.get("trust") == "agent-notice":
            out.append(str(res.get("notice", "")))
        elif res.get("status") == "error":
            out.append("That did not work: " + str((res.get("error") or {}).get("message", "error")))
        elif j.get("tool") == "lookup_policy":
            d = res.get("data") or {}
            out.append(f"Policy {policy_no} belongs to {d.get('holder', '?')}, status {d.get('status', '?')}, "
                       f"premium {d.get('premium', '?')}, last updated {d.get('last_updated', '?')}.")
        elif j.get("tool") == "list_policies":
            rows = (res.get("data") or {}).get("rows") or []
            out.append(f"There are {len(rows)} policies on this page: "
                       + ", ".join(str(r.get("policy_number")) for r in rows if isinstance(r, dict)) + ".")
        elif j.get("tool") == "update_policy":
            out.append("Done. The change was confirmed by you and sent to the system.")
    return [" ".join(reversed(out)) or "Done."]


def _recover_unknown_start(messages: list[Message]) -> list[Item] | None:
    """A business tool said it did not start on its home screen. Go back with CLEAR (not
    commit-capable) and try that tool once more. Once per user message."""
    since_user = []
    for m in reversed(messages):
        if m["role"] == "user":
            break
        since_user.append(m)
    if any(u["name"] == "press_key" for m in since_user if m["role"] == "assistant" for u in m.get("tool_uses", [])):
        return None
    failed = None
    for m in since_user:
        if m["role"] != "tool":
            break
        try:
            j = json.loads(m["content"])
        except ValueError:
            continue
        err = (j.get("result") or {}).get("error") or {}
        if err.get("code") == "unknown_start":
            failed = j.get("tool")
    if failed is None:
        return None
    for m in since_user:
        if m["role"] == "assistant":
            for u in m.get("tool_uses", []):
                if u["name"] == failed:
                    return ["Going back to the main menu first.", ToolUse("demo_clear", "press_key", {"key": "CLEAR"}),
                            ToolUse("demo_retry", failed, dict(u["input"]))]
    return None


class DemoLlm(ScriptedLlm):
    """Offline demo provider: ``LLM_PROVIDER=scripted`` with no script file."""

    def __init__(self) -> None:
        super().__init__(responder=demo_responder, model="scripted-demo")
