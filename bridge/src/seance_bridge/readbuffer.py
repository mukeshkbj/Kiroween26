"""Parse s3270's ``ReadBuffer(Ascii)`` output into a Buffer.

s3270 ``ReadBuffer(Ascii)`` dumps the screen buffer one row per line. Each buffer
position is a whitespace-separated token:

  - ``20``..``7e``  2-hex-digit ASCII code for a character position
  - ``00``           NULL (displayed as a blank)
  - ``SF(c0=nn[,...])``  start-of-field; the c0 value(s) encode field attributes
  - ``SA(...)``      extended attribute (NOT a display position) -> ignored
  - ``GE(xx)``       graphic-escape character (hex code)
  - ``-``            DBCS continuation position -> blank

The x3270 c0 (basic 3270) flag values (per the x3270-script man page):
  0x20 protected, 0x10 numeric, 0x04 detectable, 0x08 intensified,
  0x0c non-display, 0x01 modified.

NOTE: this adapter is the one part that depends on the exact s3270 output format.
It is validated against a real TK4- screen by the integration test; the flag
decoding is confirmed against observed output then. The parser/ScreenModel core
does not depend on this format at all.
"""
from __future__ import annotations

from .models import BUFFER_SIZE, Buffer, COLS, FieldAttrs, FieldStart


def _attrs_from_c0(mask: int) -> FieldAttrs:
    """Decode the OR of x3270 c0 flag values into FieldAttrs."""
    protected = bool(mask & 0x20)
    numeric = bool(mask & 0x10)
    hidden = (mask & 0x0C) == 0x0C            # non-display
    intensified = bool(mask & 0x08) and not hidden
    mdt = bool(mask & 0x01)
    return FieldAttrs(
        protected=protected,
        numeric=numeric,
        hidden=hidden,
        intensified=intensified,
        mdt=mdt,
    )


_DATA_PREFIX = "data: "


def _hex_to_char(code: int) -> str:
    if code == 0x00:
        return " "  # NULL displays as a blank
    if 0x20 <= code <= 0x7E:
        return chr(code)
    if 0xA0 <= code <= 0xFF:
        return chr(code)  # same Latin-1 glyph that Ascii() shows for this code
    return " "


def parse_readbuffer_ascii(
    output: str | list[str],
    cursor_row: int = 0,
    cursor_col: int = 0,
    rows: int = 24,
    cols: int = 80,
) -> Buffer:
    """Parse s3270 ``ReadBuffer(Ascii)`` output into a Buffer.

    Line-aware: output line N is screen row N and starts at position N*cols, so a
    short, long or odd line can never shift any other row. A leading ``data: ``
    prefix (s3270 peer-script mode) is stripped if still present. ``output`` may
    be a list of lines or one newline-joined string.
    """
    size = rows * cols
    grid = [" "] * size
    field_starts: list[FieldStart] = []

    lines = output.split("\n") if isinstance(output, str) else list(output)
    for row_index, line in enumerate(lines):
        if row_index >= rows:
            break
        if line.startswith(_DATA_PREFIX):
            line = line[len(_DATA_PREFIX):]
        col = 0
        for tok in line.split():
            if col >= cols:
                break
            pos = row_index * cols + col
            if tok.startswith("SF(") and tok.endswith(")"):
                mask = 0
                for part in tok[3:-1].split(","):
                    part = part.strip()
                    if part.lower().startswith("c0="):
                        try:
                            mask |= int(part[3:], 16)
                        except ValueError:
                            pass
                field_starts.append(FieldStart(pos=pos, attrs=_attrs_from_c0(mask)))
                grid[pos] = " "   # attribute byte is not a displayable char
                col += 1
            elif tok.startswith("SA("):
                continue  # extended attribute does not consume a position
            elif tok.startswith("GE(") and tok.endswith(")"):
                try:
                    grid[pos] = _hex_to_char(int(tok[3:-1], 16))
                except ValueError:
                    grid[pos] = " "
                col += 1
            elif tok == "-":
                grid[pos] = " "   # DBCS continuation
                col += 1
            else:
                try:
                    grid[pos] = _hex_to_char(int(tok, 16))
                except ValueError:
                    grid[pos] = " "
                col += 1

    return Buffer(
        text="".join(grid),
        field_starts=tuple(field_starts),
        cursor_row=cursor_row,
        cursor_col=cursor_col,
    )
