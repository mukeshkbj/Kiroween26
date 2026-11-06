"""Demo readiness check for the Seance Insurance stand-in (legacy-environment 7.1).

Connects to the stand-in's TN3270 port through the real bridge, waits until a
stable screen with the keyboard unlocked shows the Main Menu, then proves the
live path by looking up a seed policy (which runs the COBOL SEANCSVC on TK4-)
and checking the returned holder. Prints a clear OK/FAIL line and exits 0/1.

    python legacy/healthcheck.py [--port 3271] [--timeout 360]
"""
from __future__ import annotations

import argparse
import sys
import time

from seance_bridge import Bridge, Key


def _rows_text(bridge: Bridge) -> str:
    return "\n".join(bridge.read_screen().rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=3271)
    ap.add_argument("--timeout", type=int, default=360)
    ap.add_argument("--policy", default="P0000001")
    ap.add_argument("--expect-holder", default="J. MARLOWE")
    args = ap.parse_args()

    deadline = time.monotonic() + args.timeout
    bridge = Bridge("localhost", args.port)
    # 1) connect and see the menu
    while True:
        try:
            bridge.connect()
            text = _rows_text(bridge)
            if "MAIN MENU" in text:
                break
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        else:
            last = "menu not shown"
        if time.monotonic() > deadline:
            print(f"FAIL: stand-in not ready on port {args.port}: {last}")
            return 1
        time.sleep(3)

    # 2) prove the live COBOL path: menu -> enquiry -> lookup a seed policy
    try:
        bridge.fill_field((7, 15), "1")
        bridge.press(Key.ENTER)
        bridge.fill_field((3, 13), args.policy)
        bridge.press(Key.ENTER)
        text = _rows_text(bridge)
    finally:
        bridge.disconnect()

    if args.expect_holder in text:
        print(f"OK: menu reachable, keyboard unlocked, and {args.policy} -> "
              f"{args.expect_holder!r} from COBOL on TK4-.")
        return 0
    print(f"FAIL: lookup of {args.policy} did not return {args.expect_holder!r}. "
          f"Is HERC01.SEANCE.POLICY seeded (run legacy/reset-data.ps1)?")
    return 1


if __name__ == "__main__":
    sys.exit(main())
