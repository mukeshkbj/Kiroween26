"""ScreenModel -> tool output: sanitised, typed, hidden values never present.

This is the single point where bridge screen data becomes MCP output, so
control-character stripping and the hidden-value rule live here and only here.
Screen text is untrusted data; it is only ever placed in data fields.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from seance_bridge import Field, ScreenModel

from .audit import redact
from .safety import FieldSnap, PendingAction

TRUST_NOTE = "untrusted-screen-data"
_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_PUNCT_ONLY = re.compile(r"[=>:.\-_ ]+")


def sanitize(text: str) -> str:
    """Replace control characters (incl. newlines and C1) with spaces, length-preserving."""
    return _CTRL.sub(" ", text)


def field_label(screen: ScreenModel, f: Field) -> str:
    """Best-effort label: the text just left of the field on its row
    (e.g. 'Logon ===>' or 'POLICY NO:'). Screen text, so untrusted."""
    left = screen.rows[f.row][: max(0, f.col - 1)].rstrip()
    chunks = list(re.finditer(r"\S+(?: \S+)*", left))  # runs split by 2+ spaces
    if not chunks:
        return ""
    start = chunks[-1].start()
    # "USERID   ===>": a chunk that is only an arrow/colon belongs to the word before it.
    if len(chunks) > 1 and _PUNCT_ONLY.fullmatch(chunks[-1].group()):
        start = chunks[-2].start()
    return sanitize(left[start:])[-30:].strip()


class FieldOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    row: int
    col: int
    length: int
    protected: bool
    numeric: bool
    hidden: bool
    intensified: bool
    label: str
    value: str | None  # None for hidden fields, always


class ScreenOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    trust: str = TRUST_NOTE
    screen_id: str
    cursor: tuple[int, int]
    rows: list[str]
    fields: list[FieldOut]
    # Positions masked out of screen_id (clocks, paint-time dates, output fields), as
    # (row, col, length) runs, 0-origin. Additive in v1; consumers ignore unknowns.
    volatile: list[tuple[int, int, int]] = []


class PendingOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_id: str
    screen_id: str
    key: str
    expires_in_s: float
    field_snapshot: list[FieldSnap]


class PressOut(BaseModel):
    """press_key result: the key ran, or it is waiting for a human."""

    model_config = ConfigDict(frozen=True)

    status: str  # "executed" | "pending"
    message: str
    screen: ScreenOut | None = None
    action: PendingOut | None = None


def fields_out(screen: ScreenModel) -> list[FieldOut]:
    return [
        FieldOut(
            index=f.index,
            row=f.row,
            col=f.col,
            length=f.length,
            protected=f.protected,
            numeric=f.numeric,
            hidden=f.hidden,
            intensified=f.intensified,
            label=field_label(screen, f),
            value=None if f.hidden or f.value is None else sanitize(f.value),
        )
        for f in screen.fields
    ]


def volatile_runs(positions: tuple[int, ...], cols: int = 80) -> list[tuple[int, int, int]]:
    """Flat masked positions -> (row, col, length) runs, 0-origin.

    A run breaks at a row boundary or a non-consecutive position, so each run stays
    on one row. Deterministic (sorted, unique)."""
    runs: list[tuple[int, int, int]] = []
    for p in sorted(set(positions)):
        row, col = divmod(p, cols)
        if runs:
            r, c, n = runs[-1]
            if r == row and c + n == col:
                runs[-1] = (r, c, n + 1)
                continue
        runs.append((row, col, 1))
    return runs


def screen_out(screen: ScreenModel) -> ScreenOut:
    return ScreenOut(
        screen_id=screen.screen_id,
        cursor=screen.cursor,
        rows=[sanitize(r) for r in screen.rows],
        fields=fields_out(screen),
        volatile=volatile_runs(screen.volatile),
    )


def snapshot(screen: ScreenModel) -> list[FieldSnap]:
    """Unprotected fields as the human will see them in the confirmation."""
    out = []
    for f in screen.fields:
        if f.protected:
            continue
        label = field_label(screen, f)
        shown = redact(sanitize(f.value or "").rstrip(), hidden=f.hidden, label=label)
        out.append(FieldSnap(index=f.index, row=f.row, col=f.col, label=label, value=shown or ""))
    return out


def pending_out(a: PendingAction, now: float) -> PendingOut:
    return PendingOut(
        action_id=a.action_id,
        screen_id=a.screen_id,
        key=a.key,
        expires_in_s=round(max(0.0, a.expires_at - now), 1),
        field_snapshot=list(a.field_snapshot),
    )
