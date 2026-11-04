"""Plain-text rendering of a screen for the screen://current resource.

Unprotected (typeable) field areas are wrapped in [ ]. The brackets replace the
attribute byte before the field and the first position after it (or the next
attribute byte), so every row stays exactly 80 characters wide. Hidden fields
are already blank in ``rows``.
"""
from __future__ import annotations

from .screens import ScreenOut

COLS = 80


def render_screen(screen: ScreenOut) -> str:
    grid = [list(r.ljust(COLS)[:COLS]) for r in screen.rows]
    for f in screen.fields:
        if f.protected or f.length == 0:
            continue
        start = f.row * COLS + f.col
        open_pos = start - 1
        close_pos = start + f.length
        if open_pos >= 0:
            grid[open_pos // COLS][open_pos % COLS] = "["
        if close_pos < len(grid) * COLS:
            grid[close_pos // COLS][close_pos % COLS] = "]"
    return "\n".join("".join(r) for r in grid)
