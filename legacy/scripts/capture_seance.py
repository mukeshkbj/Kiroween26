"""Capture the five Seance Insurance stand-in screens as a gss.capture/1 file.

Agent A only. Drives the running stand-in (python -m seance_standin on
STANDIN_PORT) through the REAL bridge + ScreenParser, so screen_ids, field
layouts and labels are genuine. Writes legacy/captures/seance-insurance/capture.json
(contracts section 2.3). No secrets are involved (insurance data only); the
message/output spans are declared volatile so the capture reproduces its own
screen_ids (contract 10.4).

Usage (from the repo root, with the stand-in and TK4- both up):
    mcp-server/.venv/Scripts/python legacy/scripts/capture_seance.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "legacy" / "standin"))

from seance_bridge import Bridge, Key  # noqa: E402
from seance_mcp.screens import screen_out  # noqa: E402
from seance_standin.screens import VOLATILE_REGIONS  # noqa: E402


def press(bridge: Bridge, key: Key) -> None:
    """Press a key through the bridge (PF/PA form fixed in bridge/ on 2026-11-06)."""
    bridge.press(key)

APP_ID = "seance-insurance"
PORT = int(os.environ.get("STANDIN_PORT", "3271"))
OUT = ROOT / "legacy" / "captures" / APP_ID / "capture.json"


def so_dict(bridge: Bridge) -> dict:
    return screen_out(bridge.read_screen()).model_dump()


def volatile_pairs() -> list[list[int]]:
    return [[r, c, n] for (r, c, n) in VOLATILE_REGIONS]


def main() -> None:
    bridge = Bridge("localhost", PORT, volatile_regions=VOLATILE_REGIONS)
    bridge.connect()
    screens: list[dict] = []
    seen: set[str] = set()

    def record(name: str) -> None:
        if name in seen:
            return
        seen.add(name)
        screens.append({"name": name, "screen": so_dict(bridge), "volatile": volatile_pairs()})

    # menu
    record("menu")
    # menu -> enquiry (option 1), look up a seed policy, back
    bridge.fill_field((7, 15), "1")
    press(bridge, Key.ENTER)
    record("enquiry")
    bridge.fill_field((3, 13), "P0000003")
    press(bridge, Key.ENTER)
    record("enquiry_result")
    press(bridge, Key.PF3)
    # menu -> list (option 2)
    bridge.fill_field((7, 15), "2")
    press(bridge, Key.ENTER)
    record("list")
    press(bridge, Key.PF3)
    # menu -> update (option 3) -> confirm (no commit)
    bridge.fill_field((7, 15), "3")
    press(bridge, Key.ENTER)
    record("update")
    bridge.fill_field((3, 13), "P0000003")
    bridge.fill_field((5, 22), "L")
    press(bridge, Key.ENTER)
    record("confirm")
    press(bridge, Key.PF3)   # cancel, do not commit during capture
    bridge.disconnect()

    capture = {
        "schema": "gss.capture/1",
        "app_id": APP_ID,
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": ("Seance Insurance stand-in (legacy/standin). Presentation is a "
                 "Python TN3270 stand-in; business logic is the real COBOL "
                 "SEANCSVC on TK4-. See legacy/README.md."),
        "screens": screens,
        "transitions": [
            {"from": "menu", "key": "ENTER", "fills": [{"field": "OPTION", "value": "1"}], "to": "enquiry"},
            {"from": "menu", "key": "ENTER", "fills": [{"field": "OPTION", "value": "2"}], "to": "list"},
            {"from": "menu", "key": "ENTER", "fills": [{"field": "OPTION", "value": "3"}], "to": "update"},
            {"from": "menu", "key": "CLEAR", "fills": [], "to": "menu"},
            {"from": "enquiry", "key": "ENTER", "fills": [{"field": "POLNO", "value": "P0000003"}], "to": "enquiry_result"},
            {"from": "enquiry", "key": "PF3", "fills": [], "to": "menu"},
            {"from": "list", "key": "PF3", "fills": [], "to": "menu"},
            {"from": "update", "key": "ENTER", "fills": [{"field": "POLNO", "value": "P0000003"}], "to": "confirm"},
            {"from": "update", "key": "PF3", "fills": [], "to": "menu"},
            {"from": "confirm", "key": "PF3", "fills": [], "to": "menu"},
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(capture, indent=2), encoding="utf-8")
    print(f"wrote {OUT} ({len(screens)} screens)")


if __name__ == "__main__":
    main()
