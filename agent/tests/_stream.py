"""Stream ordering guarantees of docs/contracts.md 4.2 and 4.3.

Copied, as the examples README instructs, from ``seance_mcp.contracts.check``.
The agent's emitted streams (events.py envelopes) must satisfy these rules
(REQ-026); the property test in ``test_events_properties.py`` runs this over
generated sequences, and the conformance test runs it over the committed
transcripts.
"""
from __future__ import annotations

from typing import Any


class ContractError(AssertionError):
    pass


def check_stream(events: list[dict[str, Any]]) -> None:
    last_seq = 0
    open_turn: str | None = None
    calls: dict[str, int] = {}
    pending: dict[str, int] = {}
    finished_turns: set[str] = set()
    call_screens: dict[str, list[str]] = {}
    for e in events:
        if e["seq"] != last_seq + 1:
            raise ContractError(f"seq gap or repeat: {last_seq} -> {e['seq']}")
        last_seq = e["seq"]
        t, d, turn = e["type"], e["data"], e.get("turn_id")
        if t == "turn_started":
            if open_turn is not None:
                raise ContractError(f"turn {turn} started inside {open_turn}")
            open_turn = turn
        elif t == "turn_finished":
            if open_turn != turn or turn in finished_turns:
                raise ContractError(f"turn_finished for {turn} without matching turn_started")
            finished_turns.add(turn)
            open_turn = None
            unresolved = [c for c, n in calls.items() if n == 0]
            if unresolved:
                raise ContractError(f"turn ended with tool calls lacking a result: {unresolved}")
            if any(n == 0 for n in pending.values()):
                raise ContractError("turn ended with an unresolved confirmation")
        elif t == "tool_call":
            calls[d["tool_call_id"]] = 0
        elif t == "tool_result":
            if d["tool_call_id"] not in calls or calls[d["tool_call_id"]] != 0:
                raise ContractError(f"tool_result without exactly one tool_call: {d['tool_call_id']}")
            calls[d["tool_call_id"]] = 1
        elif t == "confirmation_required":
            pending[d["action_id"]] = 0
        elif t == "confirmation_resolved":
            if pending.get(d["action_id"]) != 0:
                raise ContractError(f"confirmation_resolved without a single confirmation_required: {d['action_id']}")
            pending[d["action_id"]] = 1
        if t in ("tool_call", "tool_result", "thinking", "assistant_delta", "assistant_message") and turn is None:
            raise ContractError(f"{t} outside a turn")
        _check_call_screens(e, calls, call_screens)
    if open_turn is not None:
        raise ContractError(f"turn {open_turn} never finished")


def _check_call_screens(e: dict[str, Any], calls: dict[str, int], call_screens: dict[str, list[str]]) -> None:
    """Contracts 4.3 screen/focus rules (findings D-3; stricter than the integrator's copy for now):

    * a call's ``screen``/``field_focus`` events arrive between its ``tool_call`` and its ``tool_result``;
    * its first ``screen`` event is ``phase: before``, and there is exactly one ``before``;
    * ``field_focus.screen_id`` names a real screen (never empty).
    """
    t, d = e["type"], e["data"]
    if t not in ("screen", "field_focus"):
        return
    cid = d.get("tool_call_id")
    if cid is None:
        if t == "screen" and d["phase"] != "snapshot":
            raise ContractError(f"seq {e['seq']}: screen{{{d['phase']}}} without a tool_call_id")
        return
    if calls.get(cid) != 0:
        raise ContractError(f"seq {e['seq']}: {t} for {cid} outside its tool_call..tool_result")
    if t == "field_focus":
        if not d["screen_id"]:
            raise ContractError(f"seq {e['seq']}: field_focus for {cid} has an empty screen_id")
        return
    phases = call_screens.setdefault(cid, [])
    if not phases and d["phase"] != "before":
        raise ContractError(f"seq {e['seq']}: first screen of {cid} is {d['phase']!r}, not 'before'")
    if phases and d["phase"] == "before":
        raise ContractError(f"seq {e['seq']}: second screen{{before}} for {cid}")
    if d["phase"] == "snapshot":
        raise ContractError(f"seq {e['seq']}: snapshot inside tool call {cid}")
    phases.append(d["phase"])


def check_summaries(events: list[dict[str, Any]]) -> None:
    """Finding D-2: a failed tool is never summarised as 'ok'."""
    for e in events:
        if e["type"] == "tool_result" and e["data"]["status"] == "error":
            s = e["data"]["summary"].lower()
            if s.endswith(" ok") or s == "ok" or " ok." in s:
                raise ContractError(f"seq {e['seq']}: failed {e['data']['tool_call_id']} summarised as {s!r}")


MODEL_ONLY = ("do not retry", "propose it again", "do not argue", "this is final")


def check_user_facing_text(events: list[dict[str, Any]]) -> None:
    """Finding D-5: instructions meant for the model never reach the person's screen."""
    for e in events:
        t, d = e["type"], e["data"]
        texts: list[str] = []
        if t == "tool_result":
            texts.append(d["summary"])
            err = (d.get("result") or {}).get("error") if isinstance(d.get("result"), dict) else None
            if isinstance(err, dict):
                texts.append(str(err.get("message", "")))
        elif t in ("assistant_message", "assistant_delta"):
            texts.append(d["text"])
        elif t == "error":
            texts.append(d["message"])
        for text in texts:
            low = text.lower()
            for phrase in MODEL_ONLY:
                if phrase in low:
                    raise ContractError(f"seq {e['seq']}: {t} shows model-only text {phrase!r}: {text[:120]!r}")
