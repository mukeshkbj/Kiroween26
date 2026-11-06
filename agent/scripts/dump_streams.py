"""Record the agent's REAL event streams as transcripts (for Agent C's conformance run).

    cd agent
    .venv\\Scripts\\python.exe scripts\\dump_streams.py

Each file in ``docs/handoff/d/streams/`` is a contracts-format transcript
(``{"dir":"server","delay_ms":N,"event":{...}}`` per line) produced by driving the
actual hub over a websocket against FakeApp and B's pack with the demo model. Unlike
``docs/contracts/examples/transcripts`` (recorded by the integrator's stand-in) these
come from the agent's own code path, so they are what the UI will really receive.
Every stream is checked with ``check_stream`` and the server-event models before it
is written.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from tests._stream import check_stream  # noqa: E402
from tests.test_api import connect_fake, make_client, open_ws  # noqa: E402

from seance_agent.events import server_event_adapter  # noqa: E402

OUT = HERE.parent / "docs" / "handoff" / "d" / "streams"
UPDATE = "Set the premium of policy P0000003 to 300"


def write(name: str, events: list[dict]) -> None:
    for e in events:
        server_event_adapter.validate_python(e)
    check_stream(events)
    OUT.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"dir": "server", "delay_ms": 120, "event": e}, ensure_ascii=False) for e in events]
    (OUT / f"{name}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"ok: {name} ({len(events)} events)")


def scenario(name: str, text: str, decision: str | None, **settings) -> None:
    with make_client(**settings) as c, open_ws(c) as s:
        connect_fake(s)
        s.send(id="u1", type="user_message", text=text)
        if decision is not None:
            req = s.until("confirmation_required")["data"]
            s.send(id="d1", type="confirm_decision", action_id=req["action_id"], decision=decision)
        s.until("turn_finished")
        write(name, s.seen)


def main() -> int:
    scenario("lookup", "Look up policy P0000003", None)
    scenario("list", "List the policies", None)
    scenario("commit-approve", UPDATE, "approve")
    scenario("commit-deny", UPDATE, "deny")
    scenario("commit-expire", UPDATE, None, pending_ttl_s=0.3)
    scenario("read-only", UPDATE, "approve", allow_commit=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
