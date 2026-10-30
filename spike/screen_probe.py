"""
Feasibility spike for Green Screen Seance.

Question: can a program reliably (1) read a 3270 screen, (2) find its input
fields, (3) type into a field and (4) press Enter / a PF key?
If yes, an AI agent can drive it via MCP.

Prereqs:
  - TK4- running:  docker run -d --name tk4 -p 3270:3270 -p 8038:8038 skunklabz/tk4-hercules
  - x3270 suite installed (s3270 on Linux/macOS, ws3270 on Windows) and on PATH
  - pip install py3270

Usage:  python spike/screen_probe.py [host:port]
"""
import sys
import time
from py3270 import Emulator

HOST = sys.argv[1] if len(sys.argv) > 1 else "localhost:3270"


def dump(em: Emulator, title: str) -> list[str]:
    """Print the full 24x80 screen as text and return the lines."""
    em.wait_for_field()
    lines = [l.decode("ascii", "replace") if isinstance(l, bytes) else l
             for l in em.exec_command(b"Ascii()").data]
    print(f"\n===== {title} =====")
    for i, line in enumerate(lines, 1):
        print(f"{i:02d}|{line}")
    return lines


def fields(em: Emulator) -> None:
    """Show where the unprotected (input) fields are, using the 3270 buffer."""
    buf = em.exec_command(b"ReadBuffer(Ascii)").data
    inputs = 0
    for row, raw in enumerate(buf, 1):
        line = raw.decode() if isinstance(raw, bytes) else raw
        for col, cell in enumerate(line.split(), 1):
            # SF(c0=xx) marks a field start; c0 bit 0x20 = protected
            if cell.startswith("SF(") and "c0=" in cell:
                attr = int(cell.split("c0=")[1][:2], 16)
                if not attr & 0x20:
                    inputs += 1
                    print(f"  input field #{inputs} at row {row}, col {col}")
    print(f"  -> {inputs} input field(s) found")


def main() -> None:
    em = Emulator(visible=False)
    print(f"Connecting to {HOST} ...")
    em.connect(HOST)
    time.sleep(2)
    dump(em, "1. Logon screen")
    fields(em)

    # TK4- default demo user (public, documented by TK4-)
    em.send_string("HERC01")
    em.send_enter()
    time.sleep(2)
    dump(em, "2. After user id")
    fields(em)

    em.send_string("CUL8TR")
    em.send_enter()
    time.sleep(3)
    dump(em, "3. After password")

    em.terminate()
    print("\nSpike complete: read screen, found fields, typed, pressed Enter.")


if __name__ == "__main__":
    main()
