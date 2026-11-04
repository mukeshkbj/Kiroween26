"""End-to-end against the live TK4- container (task 6.1), through the real bridge.

The only "commit" is ENTER on the welcome screen with a non-existent user id
(TK4- answers IKJ56420I ... NOT AUTHORIZED TO USE TSO). It never logs on to TSO.
A test elicitation callback stands in for the human.
"""
import os

import pytest

from seance_mcp.port import RealBridgePort

from harness import Session, human, make_rig

HARMLESS = "XYZZY"


@pytest.mark.integration
def test_live_read_pending_confirm_flow():
    host = os.environ["TN3270_HOST"]
    port = int(os.environ.get("TN3270_PORT", "3270"))
    rig = make_rig(port=RealBridgePort(wait_timeout_ms=8000))
    s = Session(rig, elicitation_callback=human(rig))
    try:
        s.ok("connect", host=host, port=port)
        screen = s.ok("read_screen")
        if not any("Logon ===>" in r for r in screen["rows"]):
            s.ok("press_key", key="CLEAR")  # banner still up: CLEAR is non-committing
            screen = s.ok("read_screen")
        assert "Logon ===>" in screen["rows"][22]

        fields = s.ok("list_fields")["result"]
        r, c = screen["cursor"]
        at_cursor = [f for f in fields if not f["protected"] and f["row"] == r
                     and f["col"] <= c < f["col"] + f["length"]]
        assert at_cursor, f"no unprotected field at cursor {screen['cursor']}"
        logon = at_cursor[0]
        assert logon["label"].endswith("===>")

        # A non-commit key runs immediately.
        assert s.ok("press_key", key="CLEAR")["status"] == "executed"
        assert "Logon ===>" in s.ok("read_screen")["rows"][22]

        # Type, then ENTER: pending; nothing sent; screen unchanged.
        s.ok("fill_field", field_ref=logon["index"], value=HARMLESS)
        before = s.ok("read_screen")
        pend = s.ok("press_key", key="ENTER")
        assert pend["status"] == "pending"
        assert {f["value"] for f in pend["action"]["field_snapshot"]} >= {HARMLESS}
        after_propose = s.ok("read_screen")
        assert after_propose["screen_id"] == before["screen_id"]
        assert HARMLESS in after_propose["rows"][22]
        assert rig.outcomes("press_key")[-1] == "proposed"

        # The (test) human confirms: ENTER is sent exactly once.
        result = s.ok("confirm_action", action_id=pend["action"]["action_id"])
        # TK4- passes the welcome-screen input straight to TSO logon as a user id;
        # XYZZY does not exist, so it is rejected and nothing can log on.
        text = "\n".join(result["rows"])
        assert f"USERID {HARMLESS} NOT AUTHORIZED TO USE TSO" in text
        assert len(rig.asked) == 1 and "Send Enter" in rig.asked[0]
        assert "[unknown_action]" in s.err("confirm_action", action_id=pend["action"]["action_id"])
        assert rig.service.audit.verify() is None
    finally:
        anyio_disconnect(rig)


def anyio_disconnect(rig):
    import anyio

    anyio.run(rig.service.disconnect)
