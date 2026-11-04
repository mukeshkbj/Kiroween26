"""Tiny s3270 driver for setup work on the live gss-legacy container (Agent A only).

Usage: python s3270_drive.py STEP [STEP ...]
Each STEP is one of:
  snap            print the current screen (Ascii)
  enter | clear   press that key
  pf:N | pa:N     press PF/PA key N
  str:TEXT        type TEXT at the cursor
  pass            type MVS_PASSWORD from legacy/.env (never printed)
  wait:SECONDS    sleep
  eof             erase to end of field (use before typing over a prefilled field)
  @field:TEXT     not supported (keep it simple)
After every key a snapshot is printed, except the line holding a password.
Keys are never re-sent automatically.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
S3270_EXE = ROOT / ".tools" / "s3270.exe"


def env_value(key: str) -> str:
    for line in (ROOT / "legacy" / ".env").read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"{key} not set in legacy/.env")


class S3270:
    def __init__(self, host: str, port: int) -> None:
        self.p = subprocess.Popen(
            [str(S3270_EXE), "-model", "3279-2"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            cwd=str(S3270_EXE.parent),
        )
        self.cmd(f"Connect({host}:{port})")

    def cmd(self, c: str) -> list[str]:
        assert self.p.stdin and self.p.stdout
        self.p.stdin.write(c + "\n")
        self.p.stdin.flush()
        out: list[str] = []
        while True:
            line = self.p.stdout.readline().rstrip("\n")
            if line in ("ok", "error") or not line and self.p.poll() is not None:
                if line == "error":
                    out.append("ERROR")
                return out
            out.append(line)

    def snap(self) -> str:
        lines = self.cmd("Ascii")
        return "\n".join(l[6:] if l.startswith("data: ") else l for l in lines)


def main() -> None:
    s = S3270("localhost", int(os.environ.get("TN3270_PORT", "3270")))
    time.sleep(2)
    for step in sys.argv[1:]:
        if step == "snap":
            print(s.snap())
            continue
        if step == "pass":
            s.cmd(f"String({env_value('MVS_PASSWORD')})")
            print("[typed password]")
            continue
        if step == "eof":
            s.cmd("EraseEOF")
            continue
        if step == "eof":  # erase to end of field before typing over a prefilled value
            s.cmd("EraseEOF")
            continue
        if step.startswith("wait:"):
            time.sleep(float(step[5:]))
            continue
        if step.startswith("str:"):
            s.cmd('String("' + step[4:].replace('"', '\\"') + '")')
            continue
        if step.startswith(("pf:", "pa:")):
            s.cmd(f"{step[:2].upper()}({step[3:]})")
        else:
            s.cmd({"enter": "Enter", "clear": "Clear"}[step])
        s.cmd("Wait(10,InputField)")
        time.sleep(1)
        if os.environ.get("VERBOSE"):
            print(f"--- after {step} ---")
            print(s.snap())
    s.cmd("Disconnect")
    s.p.terminate()


if __name__ == "__main__":
    main()
