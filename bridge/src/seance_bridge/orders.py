"""Decode a 3270 datastream (the order stream) into a Buffer.

This handles the standard 3270 Write-command datastream orders that describe the
screen layout:

    SF   0x1D  Start Field          -> next byte is the attribute byte
    SBA  0x34  Set Buffer Address    -> next 2 bytes encode a 12-bit address
    IC   0x13  Insert Cursor         -> cursor is at the current position
    SFE  0x29  Start Field Extended  -> count, then (type,value) pairs
    RA   0x3C  Repeat to Address     -> next 2 bytes addr + 1 char to repeat
    WCC  0xF5  Write Control Char     -> skipped (1 byte follows)

Any byte that is not an order is a character written at the current position.
The input is assumed to be *ASCII* text; the session layer is responsible for
any EBCDIC->ASCII conversion before calling ``decode_orders``. Text bytes that
fall outside the printable ASCII range are normalised to a space.

Buffer-address encoding (SBA): two bytes, each carries 6 bits of the address with
bit 0x40 set, so  address = ((b1 & 0x3F) << 6) | (b2 & 0x3F). This covers the
24x80 grid (max address 1919). The decoder is validated against real TK4- screens
by the integration test.
"""
from __future__ import annotations

from .attrs import attrs_from_byte
from .models import BUFFER_SIZE, Buffer, COLS, FieldAttrs, FieldStart

SF = 0x1D
SBA = 0x34
IC = 0x13
SFE = 0x29
RA = 0x3C
WCC = 0xF5
GE = 0x08       # Graphic Escape (introduces an EBCDIC char) - take the next byte

_ORDERS = frozenset({SF, SBA, IC, SFE, RA, WCC, GE})


def _decode_addr(b1: int, b2: int) -> int:
    return ((b1 & 0x3F) << 6) | (b2 & 0x3F)


def _to_char(b: int) -> str:
    # Printable ASCII -> char; everything else -> space. Attribute-byte positions
    # are set to space implicitly (we never write a char there).
    if 0x20 <= b <= 0x7E:
        return chr(b)
    return " "


def decode_orders(datastream: bytes) -> Buffer:
    """Decode a 3270 datastream into a Buffer."""
    grid = [" "] * BUFFER_SIZE
    pos = 0
    cursor = (0, 0)
    field_starts: list[FieldStart] = []

    i = 0
    n = len(datastream)
    while i < n:
        b = datastream[i]

        if b == SBA:
            if i + 2 >= n:
                break
            pos = _decode_addr(datastream[i + 1], datastream[i + 2])
            pos = min(pos, BUFFER_SIZE - 1)
            i += 3
            continue

        if b == SF:
            if i + 1 >= n:
                break
            attrs = attrs_from_byte(datastream[i + 1])
            if 0 <= pos < BUFFER_SIZE:
                field_starts.append(FieldStart(pos=pos, attrs=attrs))
                grid[pos] = " "  # attribute byte is not a displayable char
            pos = min(pos + 1, BUFFER_SIZE)
            i += 2
            continue

        if b == SFE:
            # count, then (type, value) pairs; find the attribute pair (type 0xC0).
            if i + 1 >= n:
                break
            count = datastream[i + 1]
            j = i + 2
            attr_byte = 0x00
            for _ in range(count):
                if j + 1 >= n:
                    break
                _type, value = datastream[j], datastream[j + 1]
                if _type == 0xC0:
                    attr_byte = value
                j += 2
            attrs = attrs_from_byte(attr_byte)
            if 0 <= pos < BUFFER_SIZE:
                field_starts.append(FieldStart(pos=pos, attrs=attrs))
                grid[pos] = " "
            pos = min(pos + 1, BUFFER_SIZE)
            i = j
            continue

        if b == IC:
            if 0 <= pos < BUFFER_SIZE:
                cursor = divmod(pos, COLS)
            i += 1
            continue

        if b == RA:
            # Repeat to Address: 2-byte addr + 1 char to repeat into.
            if i + 3 >= n:
                break
            end = _decode_addr(datastream[i + 1], datastream[i + 2])
            end = min(end, BUFFER_SIZE)
            fill = _to_char(datastream[i + 3])
            while pos < end:
                grid[pos] = fill
                pos += 1
            i += 4
            continue

        if b == WCC:
            # Write Control Character follows; skip it.
            i += 2
            continue

        if b == GE:
            # Graphic Escape: next byte is a literal char (already converted).
            if i + 1 >= n:
                break
            if 0 <= pos < BUFFER_SIZE:
                grid[pos] = _to_char(datastream[i + 1])
                pos = min(pos + 1, BUFFER_SIZE)
            i += 2
            continue

        # Plain character.
        if 0 <= pos < BUFFER_SIZE:
            grid[pos] = _to_char(b)
            pos = min(pos + 1, BUFFER_SIZE)
        i += 1

    return Buffer(
        text="".join(grid),
        field_starts=tuple(field_starts),
        cursor_row=cursor[0],
        cursor_col=cursor[1],
    )
