"""One real-model conversation against fake-insurance, through the real websocket path.

    cd agent
    .venv\\Scripts\\python.exe scripts\\real_conversation.py

Lookup, list, then a premium update that is approved the way the UI does it: a
``confirm_decision`` from the controller connection. The "person" here approves only after
checking the modal's content, which comes from the gate and the review screen, not from the
model: the confirmation must name ENTER on the confirm screen, and that screen must show
P0000003 with a new premium of 300.

Credentials: environment or ``agent/.env`` (gitignored). The key is never printed, logged or
written; the recorded stream is checked for key-like strings before it is saved to
``docs/handoff/d/streams/real-model-conversation.jsonl``. Cost: three turns, at most four
model calls each.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from tests._stream import check_stream, check_summaries, check_user_facing_text  # noqa: E402
from tests.test_api import connect_fake, make_client, open_ws  # noqa: E402

from seance_agent.__main__ import load_dotenv  # noqa: E402
from seance_agent.config import Settings  # noqa: E402
from seance_agent.llm.factory import build_llm  # noqa: E402

OUT = HERE.parent / "docs" / "handoff" / "d" / "streams" / "real-model-conversation.jsonl"
KEYLIKE = re.compile(r"sk-ant|sk-[A-Za-z0-9_\-]{20,}|AKIA[0-9A-Z]{12,}")
TURNS = ["Look up policy P0000003.", "List the policies.", "Set the premium of policy P0000003 to 300."]


def main() -> int:
    load_dotenv()
    settings = Settings.from_env(os.environ)
    llm, available = build_llm(settings)
    if llm is None or not available or settings.llm_provider.value == "scripted":
        print("no real LLM configured; nothing run")
        return 2
    print(f"provider={llm.name} model={llm.model}")  # never the key
    decisions: list[str] = []
    with make_client(llm=(llm, True), allow_commit=True, max_steps=4) as c, open_ws(c) as s:
        connect_fake(s)
        app = c.hub.live.rt.service.port  # the FakeApp
        for i, text in enumerate(TURNS):
            s.send(id=f"u{i}", type="user_message", text=text)
            while True:
                ev = s.recv()
                if ev["type"] == "turn_finished":
                    break
                if ev["type"] == "confirmation_required":
                    req = ev["data"]
                    review = next((e["data"]["screen"] for e in reversed(s.seen)
                                   if e["type"] == "screen" and e["data"]["screen"]["screen_id"] == req["screen_id"]), None)
                    rows = "\n".join(review["rows"]) if review else ""
                    ok = (req["key"] == "Enter" and "CONFIRM UPDATE" in rows and "P0000003" in rows
                          and re.search(r"\b300(\.00)?\b", rows) is not None)
                    decision = "approve" if ok else "deny"
                    decisions.append(decision)
                    s.send(id=f"d{i}", type="confirm_decision", action_id=req["action_id"], decision=decision)
        events = s.seen
        premium = app.policies["P0000003"]["premium"]
        mutations = len(app.mutations)

    text = "\n".join(json.dumps({"dir": "server", "delay_ms": 120, "event": e}, ensure_ascii=False) for e in events)
    key = os.environ.get("ANTHROPIC_API_KEY") or ""
    if KEYLIKE.search(text) or (key and key in text):
        print("key-like text found in the stream: NOT written")
        return 1
    check_stream(events)
    check_summaries(events)
    check_user_facing_text(events)
    OUT.write_text(text + "\n", encoding="utf-8")
    usage = [e["data"]["usage"] for e in events if e["type"] == "turn_finished" and e["data"]["usage"]]
    print(f"events={len(events)} decisions={decisions} premium={premium} mutations={mutations}")
    print("tokens in/out per turn: " + ", ".join(f"{u['input_tokens']}/{u['output_tokens']}" for u in usage))
    print(f"wrote {OUT.name}")
    return 0 if decisions == ["approve"] and premium == "300.00" and mutations == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
