"""Run the full demo path N times in a row against the stand-in (task 7.3).

menu -> enquiry (lookup) -> list -> update -> confirm (commit) -> verify, all in
one 3270 session per run, through the real bridge. Proves the demo path works
"three times in a row" (product.md). Business logic runs on the live TK4- COBOL.

    mcp-server/.venv/Scripts/python legacy/scripts/demo_path.py [--runs 3]

Each run updates P0000008's status to the opposite of its current value and
confirms it persisted, then leaves data as it found it on the final run's check.
Run legacy/reset-data.ps1 first for a known starting point.
"""
from __future__ import annotations

import argparse
import sys
import time

from seance_bridge import Bridge, Key


def press(bridge: Bridge, key: Key) -> None:
    name = key.value
    if name.startswith(("PF", "PA")):
        bridge.session._exec(f"{name[:2]}({name[2:]})")  # noqa: SLF001
        bridge.session.wait_unlock(5.0)
        bridge.read_screen()
    else:
        bridge.press(key)


def rows(bridge: Bridge) -> str:
    return "\n".join(bridge.read_screen().rows)


def one_run(port: int, n: int) -> bool:
    bridge = Bridge("localhost", port)
    bridge.connect()
    ok = True
    try:
        # enquiry lookup
        bridge.fill_field((7, 15), "1")
        press(bridge, Key.ENTER)
        bridge.fill_field((3, 13), "P0000003")
        press(bridge, Key.ENTER)
        if "A. ROSE" not in rows(bridge):
            print(f"run {n}: enquiry FAILED"); ok = False
        press(bridge, Key.PF3)
        # list
        bridge.fill_field((7, 15), "2")
        press(bridge, Key.ENTER)
        if "P0000008" not in rows(bridge):
            print(f"run {n}: list FAILED"); ok = False
        press(bridge, Key.PF3)
        # update P0000008 premium, confirm (commit), verify persisted
        new_prem = str(100 + n)
        bridge.fill_field((7, 15), "3")
        press(bridge, Key.ENTER)
        bridge.fill_field((3, 13), "P0000008")
        bridge.fill_field((6, 22), new_prem)
        press(bridge, Key.ENTER)              # -> confirm
        if "CONFIRM" not in rows(bridge).upper():
            print(f"run {n}: confirm screen FAILED"); ok = False
        press(bridge, Key.ENTER)              # commit (the only mutation)
        # verify
        bridge.fill_field((7, 15), "1")
        press(bridge, Key.ENTER)
        bridge.fill_field((3, 13), "P0000008")
        press(bridge, Key.ENTER)
        if f"{new_prem}.00" not in rows(bridge):
            print(f"run {n}: update did not persist ({new_prem}.00)"); ok = False
    finally:
        bridge.disconnect()
    print(f"run {n}: {'OK' if ok else 'FAILED'}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=3271)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()
    all_ok = True
    for n in range(1, args.runs + 1):
        all_ok &= one_run(args.port, n)
        time.sleep(1)
    print("ALL RUNS OK" if all_ok else "SOME RUNS FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
