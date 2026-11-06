"""Capture the TK4- built-in screens (app_id tk4-builtins) for Agent B.

Agent A only, against the LIVE TK4- on port 3270. Two screens:
  welcome        the VTAM/TK4- logon welcome (has a live Date/Time -> volatile)
  logon_rejected the error after a bogus logon with the harmless test id XYZZY
                 (IKJ56420I-style). We NEVER complete a real logon (START-HERE).

Writes legacy/captures/tk4-builtins/capture.json (gss.capture/1). No secrets:
XYZZY is a non-existent user; no password is ever typed.

Usage (TK4- up, from repo root):
    mcp-server/.venv/Scripts/python legacy/scripts/capture_builtins.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from seance_bridge import Bridge, Key  # noqa: E402
from seance_mcp.screens import screen_out  # noqa: E402

APP_ID = "tk4-builtins"
PORT = int(os.environ.get("TN3270_PORT", "3270"))
OUT = ROOT / "legacy" / "captures" / APP_ID / "capture.json"

# The TK4- welcome screen stamps a live Date (0-origin row 0) and Time; mask the
# whole top-right corner where "Date hh.mm.yy / Time hh:mm:ss" can appear so the
# screen_id is stable. Found by observing two reads of the real screen.
from seance_mcp.config import TK4_CLOCK_REGIONS as WELCOME_VOLATILE  # noqa: E402  clock + terminal id


from seance_bridge import COLS  # noqa: E402


def _volatile_spans(bridge: Bridge) -> list[list[int]]:
    """Read twice and report the (row,col,len) spans the bridge marks volatile,
    merged into contiguous runs, so the capture can reproduce its screen_id."""
    m = bridge.read_screen()
    positions = sorted(m.volatile)
    spans: list[list[int]] = []
    for p in positions:
        r, c = divmod(p, COLS)
        if spans and spans[-1][0] == r and spans[-1][1] + spans[-1][2] == c:
            spans[-1][2] += 1
        else:
            spans.append([r, c, 1])
    return spans


def capture_screen(bridge: Bridge, name: str) -> dict:
    so = screen_out(bridge.read_screen()).model_dump()
    return {"name": name, "screen": so, "volatile": [list(v) for v in so["volatile"]]}


def main() -> None:
    bridge = Bridge("localhost", PORT, volatile_regions=WELCOME_VOLATILE)
    bridge.connect()
    # TK4- shows the Hercules device banner first and replaces it with the VTAM
    # welcome ("Terminal CUU0C0 ... Date") a moment later. Wait for the welcome.
    # After a fresh IPL with no terminal attached, VTAM painted the welcome into
    # the void and does not repaint on connect: the banner stays until a key.
    # CLEAR is read-only (it is the capture's own self-transition), so press it
    # once if the welcome has not appeared after 10 s.
    for i in range(40):
        if bridge.read_screen().rows[0].lstrip().startswith("Terminal"):
            break
        if i == 10:
            bridge.press(Key.CLEAR)
        time.sleep(1)
    else:
        raise SystemExit("VTAM welcome screen never appeared")
    screens = [capture_screen(bridge, "welcome")]

    # TK4- logon flow: ENTER past the banner to the logon prompt, type the
    # harmless non-existent test id XYZZY, ENTER -> rejection. No password typed,
    # no logon completed (START-HERE).
    bridge.press(Key.ENTER)
    time.sleep(1)
    try:
        bridge.session.send_string("XYZZY")
    except Exception:
        pass
    bridge.press(Key.ENTER)
    time.sleep(1)
    screens.append(capture_screen(bridge, "logon_rejected"))
    bridge.disconnect()

    capture = {
        "schema": "gss.capture/1",
        "app_id": APP_ID,
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": ("Real TK4- (MVS 3.8j) built-in screens, captured live by Agent "
                 "A. welcome has a live clock (declared volatile). logon_rejected "
                 "is the error for the non-existent test id XYZZY; no logon is "
                 "ever completed and no password is typed."),
        "screens": screens,
        "transitions": [
            {"from": "welcome", "key": "ENTER",
             "fills": [{"field": "", "value": "XYZZY"}], "to": "logon_rejected"},
            {"from": "welcome", "key": "CLEAR", "fills": [], "to": "welcome"},
            {"from": "logon_rejected", "key": "CLEAR", "fills": [], "to": "welcome"},
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(capture, indent=2), encoding="utf-8")
    print(f"wrote {OUT} ({len(screens)} screens)")


if __name__ == "__main__":
    main()
