"""Session: a thin subprocess wrapper around s3270.

s3270 runs in peer-script mode: it reads commands from stdin and writes responses
to stdout. Every command completes with a status line, then ``ok`` or ``error``.
Data-returning commands (ReadBuffer, Ascii, Wait errors) emit their data lines
first, each prefixed with ``data: ``; the status line is never prefixed.

The status line has 12 blank-separated fields; we use field 0 (keyboard: U/L/E)
and fields 8-9 (cursor row/col, **0-origin**, same base as MoveCursor).
"""
from __future__ import annotations

import math
import re
import os
import subprocess
import time

from .errors import KeyboardTimeoutError, SessionError
from .models import Buffer
from .readbuffer import parse_readbuffer_ascii

_DATA_PREFIX = "data: "


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
    # repo root is four dirs above this file (bridge/src/seance_bridge/session.py)
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    candidate = os.path.join(repo_root, ".tools", "s3270.exe")
    if os.path.isfile(candidate):
        return candidate
    return "s3270"


def quote_string_arg(text: str) -> str:
    """Return ``text`` as a double-quoted s3270 argument.

    Backslash and double quote are escaped. Control characters are rejected:
    a raw newline would end the command line (command injection into the s3270
    script channel) and ``\\n`` style escapes would press keys.
    """
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in text):
        raise SessionError("control characters are not allowed in typed text")
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


class Session:
    def __init__(self, s3270_path: str | None = None):
        self._path = _resolve_s3270_path(s3270_path)
        self._proc: subprocess.Popen[str] | None = None

    # -- lifecycle -------------------------------------------------------

    def connect(self, host: str, port: int = 3270, settle_timeout_s: float = 20.0) -> None:
        """Connect and wait for a stable first screen.

        TK4- paints the Hercules banner first and moves on to the VTAM welcome
        screen a moment later, so we (1) wait for an input field, then (2) wait
        until the screen stops changing. A host whose first screen has no input
        field (banner only) is legitimate, so an InputField timeout is not fatal.
        """
        try:
            self._proc = subprocess.Popen(
                [self._path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                encoding="latin-1",
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise SessionError(f"s3270 not found at {self._path!r}") from exc

        _, _, ok = self._exec(f"Connect({host}:{port})")
        if not ok:
            raise SessionError(f"Connect({host}:{port}) failed")
        self._exec(f"Wait({math.ceil(settle_timeout_s)},InputField)")
        self.wait_stable(settle_timeout_s)

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
        """Run one command. Returns (data lines without prefix, status, ok)."""
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise SessionError("session not connected")
        if "\n" in command or "\r" in command:
            raise SessionError("command must be a single line")
        try:
            proc.stdin.write(command + "\n")
            proc.stdin.flush()
        except OSError as exc:
            raise SessionError("s3270 pipe closed") from exc
        data: list[str] = []
        status = ""
        while True:
            line = proc.stdout.readline()
            if not line:
                raise SessionError("s3270 closed unexpectedly")
            line = line.rstrip("\r\n")
            if line == "ok":
                return data, status, True
            if line == "error":
                return data, status, False
            if line.startswith(_DATA_PREFIX):
                data.append(line[len(_DATA_PREFIX):])
            else:
                status = line  # the (unprefixed) status line precedes ok/error

    @staticmethod
    def _parse_status(status: str) -> tuple[str, int, int]:
        """Return (keyboard_state, cursor_row, cursor_col), cursor 0-origin."""
        fields = status.split()
        kb = fields[0] if fields else "L"
        crow = ccol = 0
        if len(fields) >= 10:
            try:
                crow = max(0, int(fields[8]))
                ccol = max(0, int(fields[9]))
            except ValueError:
                pass
        return kb, crow, ccol

    # -- operations ------------------------------------------------------

    def wait_unlock(self, timeout_s: float) -> None:
        """Block in s3270 ``Wait(Unlock)``; raise KeyboardTimeoutError on expiry.

        Never resends a key: an ambiguous acknowledgement is a safe failure.
        """
        _, _, ok = self._exec(f"Wait({max(1, math.ceil(timeout_s))},Unlock)")
        if not ok:
            raise KeyboardTimeoutError("keyboard still locked after key press; not resending")

    def _raw_buffer(self) -> tuple[list[str], str]:
        data, status, ok = self._exec("ReadBuffer(Ascii)")
        if not ok:
            raise SessionError(f"ReadBuffer failed: {status}")
        return data, status

    def wait_stable(self, timeout_s: float, interval_s: float = 0.4, quiet_reads: int = 3) -> None:
        """Wait until the raw screen is identical for ``quiet_reads`` reads in a row."""
        deadline = time.monotonic() + timeout_s
        last: list[str] | None = None
        same = 0
        while time.monotonic() < deadline:
            data, _ = self._raw_buffer()
            same = same + 1 if data == last else 1
            if same >= quiet_reads:
                return
            last = data
            time.sleep(interval_s)
        # Never settled (e.g. a screen that animates). Not fatal: callers that
        # care mask volatile regions instead.

    def read_buffer(self) -> Buffer:
        """Read the screen and return a decoded Buffer (cursor from status)."""
        data, status = self._raw_buffer()
        _, crow, ccol = self._parse_status(status)
        return parse_readbuffer_ascii(data, cursor_row=crow, cursor_col=ccol)

    def ascii_rows(self, rows: int = 24, cols: int = 80) -> list[str]:
        """Rows as s3270 itself renders them via ``Ascii()`` (reference for tests)."""
        data, status, ok = self._exec("Ascii()")
        if not ok:
            raise SessionError(f"Ascii failed: {status}")
        padded = [line.ljust(cols)[:cols] for line in data[:rows]]
        return padded + [" " * cols] * (rows - len(padded))

    def send_string(self, text: str) -> None:
        arg = quote_string_arg(text)
        _, _, ok = self._exec(f"String({arg})")
        if not ok:
            raise SessionError("String() failed")

    def cursor_move(self, row: int, col: int) -> None:
        """Move the cursor; ``MoveCursor(row,col)`` is 0-origin."""
        _, _, ok = self._exec(f"MoveCursor({row},{col})")
        if not ok:
            raise SessionError(f"MoveCursor({row},{col}) failed")

    def press_key(self, key: str, timeout_s: float = 5.0) -> None:
        _, _, ok = self._exec(s3270_key_action(key))
        if not ok:
            raise SessionError(f"{key} failed")
        self.wait_unlock(timeout_s)


_KEY_RE = re.compile(r"(PF|PA)([1-9]\d?)")


def s3270_key_action(key: str) -> str:
    """The s3270 action for an attention key name (the bridge's ``Key`` values).

    s3270 wants ``PF(3)`` and ``PA(1)``, not the bare ``PF3``; ``Enter`` and ``Clear``
    are already valid action names. This is an **allowlist**: anything else is
    refused rather than forwarded, because the string becomes an s3270 command and
    a key name must never be a way to inject one (found by Agent A, 2026-11-05).
    """
    if key in ("Enter", "Clear"):
        return key
    m = _KEY_RE.fullmatch(key)
    if m:
        kind, n = m.group(1), int(m.group(2))
        if (kind == "PF" and 1 <= n <= 24) or (kind == "PA" and 1 <= n <= 3):
            return f"{kind}({n})"
    raise SessionError(f"unsupported key {key!r}")
