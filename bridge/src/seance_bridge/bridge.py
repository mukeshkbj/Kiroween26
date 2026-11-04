"""Bridge: the public facade combining Session + ScreenParser.

Exposes the API the requirements specify: connect, read_screen, fill_field,
press, disconnect. fill_field validates field constraints before typing;
press flags commit-capable keys via the returned action metadata.
"""
from __future__ import annotations

import re
import time
from collections.abc import Sequence

from .errors import FieldValidationError
from .keys import COMMIT_CAPABLE, Key
from .models import BUFFER_SIZE, COLS, Field, ScreenModel
from .parser import ScreenParser, diff_positions
from .session import Session

_MAX_REPAINT_RETRIES = 3
_NUMERIC_RE = re.compile(r"^[+-]?\d+(\.\d+)?$")


class PressResult:
    """Result of press(): the new screen plus whether it may commit data."""

    def __init__(self, screen: ScreenModel, may_commit: bool):
        self.screen = screen
        self.may_commit = may_commit


class Bridge:
    def __init__(
        self,
        host: str,
        port: int = 3270,
        wait_timeout_ms: int = 5000,
        session: Session | None = None,
        volatile_regions: Sequence[tuple[int, int, int]] = (),
        volatile_gap_s: float = 0.15,
    ):
        """``volatile_regions``: known (row, col, length) spans to always exclude
        from screen_id, for stamps that are fixed at paint time (so two reads
        agree) but differ between repaints, e.g. the TK4- welcome Date/Time."""
        self._host = host
        self._port = port
        self._timeout_s = wait_timeout_ms / 1000.0
        self._volatile_gap_s = volatile_gap_s
        self._static_volatile = frozenset(
            r * COLS + c + i
            for r, c, n in volatile_regions
            for i in range(n)
            if 0 <= r * COLS + c + i < BUFFER_SIZE
        )
        self._parser = ScreenParser()
        self._session = session or Session()

    # -- lifecycle -------------------------------------------------------

    def connect(self) -> None:
        self._session.connect(self._host, self._port)

    def disconnect(self) -> None:
        self._session.disconnect()

    @property
    def session(self) -> Session:
        return self._session

    # -- operations ------------------------------------------------------

    def read_screen(self) -> ScreenModel:
        """Read the screen twice; positions that changed are volatile.

        Volatile positions (a live clock, say) stay visible in ``rows`` but are
        excluded from ``screen_id``. If the field layout differs between the two
        reads the screen was mid-repaint, so we read again (bounded).
        """
        first = self._session.read_buffer()
        for _ in range(_MAX_REPAINT_RETRIES):
            time.sleep(self._volatile_gap_s)
            second = self._session.read_buffer()
            if second.field_starts == first.field_starts:
                break
            first = second
        else:
            second = self._session.read_buffer()
        volatile = diff_positions(first, second) | self._static_volatile
        return self._parser.parse(second, volatile)

    def fill_field(self, field_ref: int | tuple[int, int], value: str) -> ScreenModel:
        screen = self.read_screen()
        field = self._resolve_field(screen, field_ref)

        if field.protected:
            raise FieldValidationError(f"field {field.index} is protected")
        if len(value) > field.length:
            raise FieldValidationError(
                f"value too long: {len(value)} > field length {field.length}"
            )
        if field.numeric and not _NUMERIC_RE.match(value):
            # Never echo the value: the field may be hidden (a PIN), and error
            # messages end up in tool results and the audit log.
            raise FieldValidationError(f"field {field.index} is numeric; value is not a number")

        self._session.cursor_move(field.row, field.col)
        self._session.send_string(value)
        return self.read_screen()

    def press(self, key: Key) -> PressResult:
        self._session.press_key(key.value, self._timeout_s)
        screen = self.read_screen()
        return PressResult(screen=screen, may_commit=key in COMMIT_CAPABLE)

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _resolve_field(screen: ScreenModel, field_ref: int | tuple[int, int]) -> Field:
        if isinstance(field_ref, int):
            for f in screen.fields:
                if f.index == field_ref:
                    return f
            raise FieldValidationError(f"no field with index {field_ref}")
        row, col = field_ref
        f = ScreenParser.field_at(screen, row, col)
        if f is None:
            raise FieldValidationError(f"no field covers ({row},{col})")
        return f
