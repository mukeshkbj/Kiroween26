"""REQ-032: one end-to-end run through the agent against the LIVE legacy system.

Marked ``integration`` and skipped unless ``GSS_LIVE_OK=1`` and ``TN3270_HOST`` are
set, so it is a no-op in every checkout except Agent A's (contracts 2.1). Agent D
never runs it. It uses the ``scripted`` provider and is READ-ONLY: it reads the
screen and, if a business tool exists, looks a policy up. It proposes nothing,
presses no commit-capable key itself, and would stop at the modal if anything did.

Run (Agent A, from a checkout allowed to touch ``gss-legacy``)::

    $env:GSS_LIVE_OK = "1"; $env:GSS_E2E_APP = "tk4-builtins"
    python -m pytest -m integration tests/test_live_e2e.py -q

Three runs in a row, each a fresh connection, because the demo path must work
three times in a row (judging.md).
"""
from __future__ import annotations

import os

import pytest

from seance_agent.llm.base import ToolUse
from seance_agent.llm.scripted import ScriptedLlm

from ._stream import check_stream
from .test_api import connect_fake, make_client, open_ws  # noqa: F401  (connect_fake used for the fake variant)

pytestmark = pytest.mark.integration

APP = os.environ.get("GSS_E2E_APP", "tk4-builtins")

if os.environ.get("GSS_LIVE_OK") != "1" or not os.environ.get("TN3270_HOST"):
    pytest.skip("live run: needs GSS_LIVE_OK=1 and TN3270_HOST (Agent A only)", allow_module_level=True)


@pytest.mark.parametrize("run", [1, 2, 3])
def test_read_only_turn_against_the_live_system(run: int) -> None:
    llm = ScriptedLlm([[ToolUse("tu1", "read_screen", {})], ["I read the screen."]])
    with make_client(llm=(llm, True), env=os.environ, allow_commit=False) as c, open_ws(c) as s:
        s.until("session_state")
        s.send(id="c1", type="connect_system", app_id=APP)
        s.until("session_state", lambda e: e["data"]["state"] == "connected")
        s.until("screen", lambda e: e["data"]["phase"] == "snapshot")
        s.send(id="u1", type="user_message", text="What is on the screen?")
        s.until("turn_finished")
        check_stream(s.seen)
        assert any(e["type"] == "screen" and e["data"]["phase"] == "after" for e in s.seen)
        assert not [e for e in s.seen if e["type"] == "confirmation_required"]
        assert "hidden" not in " ".join(
            str(f["value"]) for e in s.seen if e["type"] == "screen"
            for f in e["data"]["screen"]["fields"] if f["hidden"] and f["value"] is not None)
