"""Decode a 3270 field attribute byte into FieldAttrs.

Bit layout of the classic attribute byte (IBM bit 0 = MSB, value 0x80):

    0x80  protected
    0x40  numeric
    0x20  skip (autoskip)           -- not modelled beyond this decode
    0x18  display mode (2 bits):
            00 = non-display (hidden)
            01 = normal display
            10 = normal, selector-pen detectable
            11 = intensified, selector-pen detectable
    0x04  reserved
    0x02  MDT (modified data tag)
    0x01  reserved

Exact semantics are validated against real TK4- screens by the integration test.
The parser itself only consumes FieldAttrs, so it is independent of this layout.
"""
from __future__ import annotations

from .models import FieldAttrs


def attrs_from_byte(b: int) -> FieldAttrs:
    """Decode one 3270 attribute byte into FieldAttrs."""
    if not (0 <= b <= 0xFF):
        raise ValueError(f"attribute byte out of range: {b}")

    protected = bool(b & 0x80)
    numeric = bool(b & 0x40)
    display = (b & 0x18) >> 3          # 0..3
    hidden = display == 0
    intensified = display == 3
    mdt = bool(b & 0x02)
    return FieldAttrs(
        protected=protected,
        numeric=numeric,
        hidden=hidden,
        intensified=intensified,
        mdt=mdt,
    )
