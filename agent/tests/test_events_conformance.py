"""REQ-030: the agent's event models match docs/contracts.md section 4 exactly.

Three checks, all over the committed examples (the integrator generated them by
driving the real service), so this test fails the moment events.py drifts from
the contract:

1. Every ``events/*.json`` server event parses through ``server_event_adapter``
   and re-serialises to the same JSON (field-for-field, byte-stable under sorted
   keys). Every ``events/client-*.json`` does the same through the client adapter.
2. Each parsed server event also validates against the generated JSON Schema.
3. Every transcript in ``transcripts/*.jsonl`` replays through our models, and the
   server events satisfy the copied ``check_stream`` ordering rules.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from seance_agent.events import client_message_adapter, server_event_adapter

from ._stream import check_stream


def _canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _server_events(examples_dir: Path) -> list[Path]:
    return sorted(p for p in (examples_dir / "events").glob("*.json") if not p.name.startswith("client-"))


def _client_messages(examples_dir: Path) -> list[Path]:
    return sorted((examples_dir / "events").glob("client-*.json"))


def _load_schema(schemas_dir: Path, name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((schemas_dir / f"{name}.schema.json").read_text(encoding="utf-8")))


def test_every_server_event_example_exists(examples_dir: Path) -> None:
    # Guard against the fixtures silently moving away: all 16 event types present.
    names = {p.stem for p in _server_events(examples_dir)}
    expected = {
        "session_state", "ack", "turn_started", "thinking", "assistant_delta",
        "assistant_message", "tool_call", "screen", "field_focus", "tool_result",
        "confirmation_required", "confirmation_resolved", "audit_entry",
        "turn_finished", "error", "pong",
    }
    assert expected <= names, f"missing server event examples: {expected - names}"


def test_server_events_round_trip_and_validate(examples_dir: Path, schemas_dir: Path) -> None:
    validator = _load_schema(schemas_dir, "server-event")
    for path in _server_events(examples_dir):
        raw = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(raw)  # the committed example matches the schema
        model = server_event_adapter.validate_python(raw)
        dumped = server_event_adapter.dump_python(model, mode="json")
        assert _canonical(dumped) == _canonical(raw), f"{path.name} did not round-trip through events.py"


def test_client_messages_round_trip_and_validate(examples_dir: Path, schemas_dir: Path) -> None:
    validator = _load_schema(schemas_dir, "client-message")
    for path in _client_messages(examples_dir):
        raw = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(raw)
        model = client_message_adapter.validate_python(raw)
        dumped = client_message_adapter.dump_python(model, mode="json")
        assert _canonical(dumped) == _canonical(raw), f"{path.name} did not round-trip through events.py"


def test_transcripts_replay_through_models(examples_dir: Path) -> None:
    transcripts = sorted((examples_dir / "transcripts").glob("*.jsonl"))
    assert transcripts, "no transcripts found to replay"
    for path in transcripts:
        server_events: list[dict] = []
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj["dir"] == "server":
                model = server_event_adapter.validate_python(obj["event"])
                dumped = server_event_adapter.dump_python(model, mode="json")
                assert _canonical(dumped) == _canonical(obj["event"]), f"{path.name}:{n} drift on {obj['event']['type']}"
                server_events.append(obj["event"])
            else:
                client_message_adapter.validate_python(obj["msg"])
        check_stream(server_events)
