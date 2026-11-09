"""Validate contract examples: schema checks plus the stream rules of contracts section 4.3.

``python -m seance_mcp.contracts.check`` validates everything under
``docs/contracts/examples/`` against ``docs/contracts/schemas/`` and the stream
rules. Agents D and C reuse ``check_stream`` (copy it) on their own output.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from ..paths import REPO_ROOT
from .models import client_message_adapter, server_event_adapter, transcript_line_adapter

CONTRACTS = REPO_ROOT / "docs" / "contracts"
EXAMPLES = CONTRACTS / "examples"
SCHEMAS = CONTRACTS / "schemas"

# example file (relative to examples/) -> schema name
_REST = {
    "rest/health.json": "rest-health", "rest/session.json": "rest-session", "rest/apps.json": "rest-apps",
    "rest/audit.json": "rest-audit", "spirit-map/spirit-map-view.json": "spirit-map-view",
    "toolpack/tools.json": "toolpack", "toolpack/tool-approvals.json": "tool-approvals",
    "toolpack/key-policy.golden.json": "key-policy", "capture/capture.json": "capture",
}


class ContractError(AssertionError):
    pass


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def check_stream(events: list[dict[str, Any]]) -> None:
    """Ordering guarantees of docs/contracts.md 4.2 and 4.3 for one session's events."""
    last_seq = 0
    open_turn: str | None = None
    calls: dict[str, int] = {}      # tool_call_id -> results so far
    pending: dict[str, int] = {}    # action_id -> resolutions so far
    finished_turns: set[str] = set()
    message_turn: dict[str, str | None] = {}  # message_id -> the turn it belongs to
    for e in events:
        if e["seq"] != last_seq + 1:
            raise ContractError(f"seq gap or repeat: {last_seq} -> {e['seq']}")
        last_seq = e["seq"]
        t, d, turn = e["type"], e["data"], e.get("turn_id")
        if t == "turn_started":
            if open_turn is not None:
                raise ContractError(f"turn {turn} started inside {open_turn}")
            if turn in finished_turns:
                raise ContractError(f"turn_id {turn} reused within the session (contracts 4.2)")
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
            if d["tool_call_id"] in calls:
                raise ContractError(f"tool_call_id {d['tool_call_id']} reused within the session (contracts 4.2)")
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
        if t in ("assistant_delta", "assistant_message"):
            # Many deltas share one message_id within one turn; the same id in a later turn is reuse.
            owner = message_turn.setdefault(d["message_id"], turn)
            if owner != turn:
                raise ContractError(f"message_id {d['message_id']} reused in turn {turn} (first in {owner}; contracts 4.2)")
        if t in ("tool_call", "tool_result", "thinking", "assistant_delta", "assistant_message") and turn is None:
            raise ContractError(f"{t} outside a turn")
    if open_turn is not None:
        raise ContractError(f"turn {open_turn} never finished")


def _no_hidden_values(obj: Any, where: str) -> None:
    """A screen field flagged hidden must carry value null."""
    if isinstance(obj, dict):
        if obj.get("hidden") is True and "value" in obj and obj["value"] is not None:
            raise ContractError(f"{where}: hidden field with a value")
        for k, v in obj.items():
            _no_hidden_values(v, f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _no_hidden_values(v, f"{where}[{i}]")


def validate_transcript(path: Path) -> list[dict[str, Any]]:
    server_events: list[dict[str, Any]] = []
    sv = _validator("server-event")
    cv = _validator("client-message")
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        obj = json.loads(line)
        transcript_line_adapter.validate_python(obj)
        if obj["dir"] == "server":
            server_event_adapter.validate_python(obj["event"])
            sv.validate(obj["event"])
            server_events.append(obj["event"])
        else:
            client_message_adapter.validate_python(obj["msg"])
            cv.validate(obj["msg"])
        _no_hidden_values(obj, f"{path.name}:{n}")
    check_stream(server_events)
    return server_events


def validate_all(examples: Path = EXAMPLES) -> list[str]:
    """Return a list of 'ok: ...' lines; raise on the first problem."""
    from .models import SCHEMAS as ADAPTERS

    done: list[str] = []
    for name in ADAPTERS:
        sf = SCHEMAS / f"{name}.schema.json"
        if not sf.exists():
            raise ContractError(f"missing schema file {sf}")
        Draft202012Validator.check_schema(json.loads(sf.read_text(encoding="utf-8")))
    sv, cv = _validator("server-event"), _validator("client-message")
    for f in sorted((examples / "events").glob("*.json")):
        obj = json.loads(f.read_text(encoding="utf-8"))
        name = "client-message" if f.name.startswith("client-") else "server-event"
        (cv if name == "client-message" else sv).validate(obj)
        (client_message_adapter if name == "client-message" else server_event_adapter).validate_python(obj)
        _no_hidden_values(obj, f.name)
        done.append(f"ok: events/{f.name}")
    for f in sorted((examples / "transcripts").glob("*.jsonl")):
        validate_transcript(f)
        done.append(f"ok: transcripts/{f.name}")
    for rel, name in _REST.items():
        f = examples / rel
        obj = json.loads(f.read_text(encoding="utf-8"))
        _validator(name).validate(obj)
        from .models import SCHEMAS as A

        A[name].validate_python(obj)
        _no_hidden_values(obj, rel)
        done.append(f"ok: {rel}")
    return done


def main() -> int:
    try:
        for line in validate_all():
            print(line)
    except (ContractError, Exception) as exc:  # noqa: BLE001
        print(f"FAIL: {type(exc).__name__}: {str(exc)[:600]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
