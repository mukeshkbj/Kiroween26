"""Data models for the screen-bridge.

The 3270 screen is a 24x80 (1920-position) buffer. This module defines:

- ``FieldAttrs``  — the attributes of one field (decoded from a 3270 attribute byte).
- ``FieldStart``   — a Start Field order: the attribute byte sits at ``pos``.
- ``Buffer``      — a *decoded* buffer: the 1920-char text grid + field starts + cursor.
- ``Field``       — one extracted field as exposed to callers.
- ``ScreenModel`` — the full structured model returned by the parser.

A field's attribute byte occupies a buffer position (displayed as a blank); the
field's *data* begins at ``pos + 1`` and runs until the next field start or the
end of the buffer. Hidden (non-display) field values are never exposed.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

ROWS = 24
COLS = 80
BUFFER_SIZE = ROWS * COLS  # 1920


class FieldAttrs(BaseModel):
    model_config = ConfigDict(frozen=True)

    protected: bool = False
    numeric: bool = False
    hidden: bool = False        # non-display
    intensified: bool = False
    mdt: bool = False          # modified data tag (internal; not exposed in Field)


class FieldStart(BaseModel):
    """A Start Field order. The attribute byte sits at flat position ``pos``."""
    model_config = ConfigDict(frozen=True)

    pos: int
    attrs: FieldAttrs


class Buffer(BaseModel):
    """A decoded 3270 screen buffer.

    ``text`` is the flat 1920-char grid. Positions occupied by a field attribute
    byte hold a space (attributes are not displayable characters). Field data
    begins at ``pos + 1`` for each FieldStart and runs to the next field start
    (or end of buffer). Hidden field data is kept here so the parser can suppress
    it; it never leaves the parser in ``ScreenModel``.
    """
    model_config = ConfigDict(frozen=True)

    text: str
    field_starts: tuple[FieldStart, ...] = ()
    cursor_row: int = 0
    cursor_col: int = 0

    @model_validator(mode="after")
    def _check(self) -> "Buffer":
        if len(self.text) != BUFFER_SIZE:
            raise ValueError(f"buffer text must be {BUFFER_SIZE} chars, got {len(self.text)}")
        if not (0 <= self.cursor_row < ROWS) or not (0 <= self.cursor_col < COLS):
            raise ValueError(f"cursor out of range: ({self.cursor_row},{self.cursor_col})")
        for fs in self.field_starts:
            if not (0 <= fs.pos < BUFFER_SIZE):
                raise ValueError(f"field start pos out of range: {fs.pos}")
        return self

    def rows(self) -> list[str]:
        """Return the grid as 24 strings of length 80."""
        return [self.text[i * COLS:(i + 1) * COLS] for i in range(ROWS)]


class Field(BaseModel):
    """One field, as exposed to callers."""
    model_config = ConfigDict(frozen=True)

    index: int
    row: int                 # first DATA position (where input begins)
    col: int
    length: int              # number of data positions
    protected: bool
    numeric: bool
    hidden: bool
    intensified: bool
    value: str | None        # None when hidden; never the hidden value


class ScreenModel(BaseModel):
    """The structured, deterministic model of one 3270 screen."""
    model_config = ConfigDict(frozen=True)

    rows: tuple[str, ...]     # 24 strings of length 80
    cursor: tuple[int, int]
    fields: tuple[Field, ...]
    screen_id: str            # stable hash; ignores unprotected/hidden values
