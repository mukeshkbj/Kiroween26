"""Session: a thin subprocess wrapper around s3270.

s3270 runs in peer-script mode: it reads commands from stdin and writes responses
to stdout. Every command completes with a two-line message -- a status line, then
``ok`` or ``error``. Data-returning commands (ReadBuffer, Query) write their data
first, then the status line, then ``ok``/``error``.

The status line has 12 blank-separated fields; we use field 0 (keyboard: U/L/E)
and fields 8-9 (cursor row/col, 1-based in x3270).

NOTE: this layer needs a real s3270 binary + a reachable 3270 host, so it is only
exercised by the integration test (skipped when TK4- is down). The exact status
field offsets and cursor base are confirmed against real TK4- then.
"""
from __future__ import annotations

import os
import subprocess
import time

from .errors import KeyboardTimeoutError, SessionError
from .readbuffer import parse_readbuffer_ascii


def _resolve_s3270_path(explicit: str | None) -> str:
    """Find the s3270 binary.

    Order: an explicit arg, the S3270_PATH env var, a repo-local .tools/s3270.exe
    (used on Windows where s3270 isn't on PATH), then 's3270' on PATH.
    """
    if explicit:
        return explicit
    env = os.environ.get("S3270_PATH")
    if env and os.path.isfile(env):
        return env
    # repo root is three dirs above this file (bridge/src/seance_bridge/session.py)
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    candidate = os.path.join(repo_root, ".tools", "s3270.exe")
    if os.path.isfile(candidate):
        return candidate
    return "s3270"


class Session:
    def __init__(self, s3270_path: str | None = None):
        self._path = _resolve_s3270_path(s3270_path)
        self._proc: subprocess.Popen[str] | None = None

    # -- lifecycle -------------------------------------------------------

    def connect(self, host: str, port: int = 3270) -> None:
        try:
            self._proc = subprocess.Popen(
                [self._path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise SessionError(f"s3270 not found at {self._path!r}") from exc

        _, _, ok = self._exec(f"Connect({host}:{port})")
        if not ok:
            raise SessionError(f"Connect({host}:{port}) failed")

    def disconnect(self) -> None:
        if self._proc is None:
            return
        try:
            self._exec("Disconnect")
        except SessionError:
            pass
        try:
            self._exec("Quit")
        except SessionError:
            pass
        try:
            self._proc.terminate()
        finally:
            self._proc = None

    # -- low-level protocol ---------------------------------------------

    def _exec(self, command: str) -> tuple[list[str], str, bool]:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise SessionError("session not connected")
        proc.stdin.write(command + "\n")
        proc.stdin.flush()
        lines: list[str] = []
        while True:
            line = proc.stdout.readline()
            if not line:
                raise SessionError("s3270 closed unexpectedly")
            line = line.rstrip("\n")
            if line == "ok":
                status = lines[-1] if lines else ""
                return lines[:-1], status, True
            if line == "error":
                status = lines[-1] if lines else ""
                return lines[:-1], status, False
            lines.append(line)

    @staticmethod
    def _parse_status(status: str) -> tuple[str, int, int]:
        """Return (keyboard_state, cursor_row_0based, cursor_col_0based)."""
        fields = status.split()
        kb = fields[0] if fields else "L"
        crow = ccol = 0
        # x3270 status: fields 8 and 9 are cursor row/col (1-based); confirm at
        # integration time. Fail soft to (0,0) if the shape differs.
        if len(fields) >= 10:
            try:
                crow = max(0, int(fields[8]) - 1)
                ccol = max(0, int(fields[9]) - 1)
            except ValueError:
                pass
        return kb, crow, ccol

    # -- operations ------------------------------------------------------

    def wait_unlock(self, timeout_s: float) -> None:
        """Poll until the keyboard unlocks, or raise KeyboardTimeoutError.

        Never resends a key: an ambiguous acknowledgement is a safe failure.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            _, status, _ = self._exec("Query")
            kb, _, _ = self._parse_status(status)
            if kb == "U":
                return
            time.sleep(0.05)
        raise KeyboardTimeoutError("keyboard still locked after key press; not resending")

    def read_buffer(self):
        """Read the screen and return a decoded Buffer (cursor from status)."""
        data, status, ok = self._exec("ReadBuffer(Ascii)")
        if not ok:
            raise SessionError(f"ReadBuffer failed: {status}")
        _, crow, ccol = self._parse_status(status)
        return parse_readbuffer_ascii("\n".join(data), cursor_row=crow, cursor_col=ccol)

    def send_string(self, text: str) -> None:
        # Escape characters that are special in the x3270 action grammar. A full
        # escape is confirmed at integration time; this covers the common case.
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        _, _, ok = self._exec(f"String({safe})")
        if not ok:
            raise SessionError(f"String({safe!r}) failed")

    def cursor_move(self, row: int, col: int) -> None:
        # x3270 cursor is 1-based; confirm at integration time.
        _, _, ok = self._exec(f"CursorMove({row + 1},{col + 1})")
        if not ok:
            raise SessionError(f"CursorMove({row},{col}) failed")

    def press_key(self, key: str, timeout_s: float = 5.0) -> None:
        _, _, ok = self._exec(key)
        if not ok:
            raise SessionError(f"{key} failed")
        self.wait_unlock(timeout_s)
