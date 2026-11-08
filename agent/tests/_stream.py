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
    if open_turn is not None:
        raise ContractError(f"turn {open_turn} never finished")
