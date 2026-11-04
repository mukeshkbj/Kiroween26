"""ScreenParser: Buffer -> ScreenModel.

This is the pure, deterministic, heavily property-tested core. It has no I/O and
no emulator dependency, so it can be developed and hardened before TK4- exists.

Key invariants (enforced + tested):
  * parsing never crashes for any valid buffer;
  * fields never overlap and stay inside the 24x80 grid;
  * hidden (non-display) field values never appear anywhere in the output;
  * screen_id is deterministic and invariant under changes to unprotected or
    hidden field values (those positions are replaced by a fixed placeholder).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .models import COLS, ROWS, BUFFER_SIZE, Buffer, Field, FieldAttrs, FieldStart, ScreenModel

# Stands in for any value we deliberately exclude from screen_id (unprotected
# fields, where users type, and hidden fields, whose values are secret).
_PLACEHOLDER = "\x00"


@dataclass(frozen=True)
class _FieldRegion:
    index: int
    begin: int    # first DATA position (attribute pos + 1)
    end: int      # exclusive
    attrs: FieldAttrs


class ScreenParser:
    """Turn a decoded Buffer into a structured, deterministic ScreenModel."""

    def parse(self, buffer: Buffer) -> ScreenModel:
        text = buffer.text
        if len(text) != BUFFER_SIZE:
            raise ValueError(
                f"buffer text must be {BUFFER_SIZE} chars, got {len(text)}"
            )

        # Sort by position and drop duplicate positions so data regions cannot
        # overlap (a duplicate SF at the same pos would produce overlapping data).
        seen: set[int] = set()
        ordered: list[FieldStart] = []
        for fs in sorted(buffer.field_starts, key=lambda f: f.pos):
            if fs.pos in seen:
                continue
            seen.add(fs.pos)
            ordered.append(fs)

        regions = self._regions(ordered)

        # Build the visible grid: copy text, then blank out hidden field data.
        grid = list(text)
        for r in regions:
            if r.attrs.hidden:
                for p in range(r.begin, r.end):
                    if 0 <= p < BUFFER_SIZE:
                        grid[p] = " "

        # Build the exposed Field list.
        fields: list[Field] = []
        for r in regions:
            if r.begin >= BUFFER_SIZE:
                value = "" if not r.attrs.hidden else None
                length = 0
                row = 0
                col = 0
            else:
                length = r.end - r.begin
                row, col = divmod(r.begin, COLS)
                if r.attrs.hidden:
                    value = None
                else:
                    value = text[r.begin:r.end]
            fields.append(
                Field(
                    index=r.index,
                    row=row,
                    col=col,
                    length=length,
                    protected=r.attrs.protected,
                    numeric=r.attrs.numeric,
                    hidden=r.attrs.hidden,
                    intensified=r.attrs.intensified,
                    value=value,
                )
            )

        rows = tuple("".join(grid[i * COLS:(i + 1) * COLS]) for i in range(ROWS))
        screen_id = self._screen_id(text, regions)
        return ScreenModel(
            rows=rows,
            cursor=(buffer.cursor_row, buffer.cursor_col),
            fields=tuple(fields),
            screen_id=screen_id,
        )

    # --- internals -------------------------------------------------------

    def _regions(self, ordered: list[FieldStart]) -> list[_FieldRegion]:
        regions: list[_FieldRegion] = []
        for i, fs in enumerate(ordered):
            begin = fs.pos + 1
            end = ordered[i + 1].pos if i + 1 < len(ordered) else BUFFER_SIZE
            # Clamp: an attribute at the last position has no data room.
            if end < begin:
                end = begin
            if begin > BUFFER_SIZE:
                begin = BUFFER_SIZE
                end = BUFFER_SIZE
            regions.append(_FieldRegion(index=i, begin=begin, end=end, attrs=fs.attrs))
        return regions

    def _screen_id(self, text: str, regions: list[_FieldRegion]) -> str:
        # Positions excluded from the hash: anything a user can type (unprotected)
        # or that is hidden (secret). Including these would make screen_id depend
        # on typed values or leak secrets into the hash.
        excluded = [False] * BUFFER_SIZE
        for r in regions:
            if (not r.attrs.protected) or r.attrs.hidden:
                for p in range(r.begin, r.end):
                    if 0 <= p < BUFFER_SIZE:
                        excluded[p] = True

        parts: list[str] = []
        for p in range(BUFFER_SIZE):
            parts.append(_PLACEHOLDER if excluded[p] else text[p])
        # Append the field structure so layout/attribute changes are detected even
        # when the visible text is identical.
        for r in regions:
            a = r.attrs
            parts.append(
                f"|{r.begin}:{int(a.protected)},{int(a.numeric)},"
                f"{int(a.hidden)},{int(a.intensified)},{int(a.mdt)}"
            )
        return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()

    # --- helper for callers (bridge.fill_field) -------------------------

    @staticmethod
    def field_at(model: ScreenModel, row: int, col: int) -> Field | None:
        """Return the field covering (row, col), or None if none."""
        for f in model.fields:
            if f.length == 0:
                continue
            start = f.row * COLS + f.col
            pos = row * COLS + col
            if start <= pos < start + f.length:
                return f
        return None
