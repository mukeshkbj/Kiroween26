"""Minimal 3270 datastream + EBCDIC encoding for the Seance Insurance stand-in.

Enough of the 3270 data stream to drive s3270 (the bridge's client): write an
Erase/Write with Start-Field orders and read back an inbound AID + modified
fields. Not a general 3270 implementation -- only what the five demo screens use.

References: IBM 3270 Data Stream Programmer's Reference (orders SBA, SF, IC; the
field attribute byte; AID codes). All screen positions here are 0-origin
(row, col); the wire uses 12-bit buffer addresses.
"""
from __future__ import annotations

from dataclasses import dataclass

ROWS = 24
COLS = 80
SIZE = ROWS * COLS

# ---- 3270 orders / commands -------------------------------------------------
CMD_ERASE_WRITE = 0xF5          # EBCDIC; also the "erase/write" command code
ORDER_SF = 0x1D                 # Start Field
ORDER_SBA = 0x11                # Set Buffer Address
ORDER_IC = 0x13                 # Insert Cursor
ORDER_SF_EXT = 0x29            # Start Field Extended (unused; kept for clarity)

# Write Control Character: reset + keyboard restore + reset MDT.
WCC_RESTORE_RESET = 0xC3

# AID bytes (inbound) -> our key names (match seance_bridge Key names).
AID_NAMES = {
    0x7D: "Enter",
    0x6D: "Clear",
    0x6C: "PA2",
    0x6E: "PA3",
    0x6B: "PA1",
    0xF1: "PF1", 0xF2: "PF2", 0xF3: "PF3", 0xF4: "PF4", 0xF5: "PF5",
    0xF6: "PF6", 0xF7: "PF7", 0xF8: "PF8", 0xF9: "PF9", 0x7A: "PF10",
    0x7B: "PF11", 0x7C: "PF12",
    0xC1: "PF13", 0xC2: "PF14", 0xC3: "PF15", 0xC4: "PF16", 0xC5: "PF17",
    0xC6: "PF18", 0xC7: "PF19", 0xC8: "PF20", 0xC9: "PF21", 0x4A: "PF22",
    0x4B: "PF23", 0x4C: "PF24",
}

# Field attribute byte bits (the byte that follows an SF order).
ATTR_PROTECTED = 0x20
ATTR_NUMERIC = 0x10
ATTR_MDT = 0x01
ATTR_DISPLAY_NORMAL = 0x00      # bits 2-3 = 00 display, not light-pen
ATTR_INTENSIFIED = 0x08         # bits 2-3 = 10 intensified
ATTR_NONDISPLAY = 0x0C          # bits 2-3 = 11 non-display (hidden)


def field_attr(*, protected: bool, numeric: bool = False, hidden: bool = False,
               intensified: bool = False) -> int:
    """Build a 3270 field attribute byte.

    s3270 decodes the c0 flags exactly as seance_bridge.readbuffer expects:
    0x20 protected, 0x10 numeric, 0x0C non-display, 0x08 intensified.
    """
    a = 0
    if protected:
        a |= ATTR_PROTECTED
    if numeric:
        a |= ATTR_NUMERIC
    if hidden:
        a |= ATTR_NONDISPLAY
    elif intensified:
        a |= ATTR_INTENSIFIED
    # The attribute byte's high two bits (0xC0) are set by hardware/encoding to
    # keep it a valid (printable) EBCDIC-range graphic; s3270 masks them off when
    # decoding c0, so we must NOT set them here.
    return a


# ---- EBCDIC (code page 037, the printable subset we need) -------------------
# Build a bidirectional ASCII<->EBCDIC map for the graphic characters used on the
# screens. Python's 'cp037' codec covers the full set; we use it directly.

def ascii_to_ebcdic(text: str) -> bytes:
    return text.encode("cp037")


def ebcdic_to_ascii(data: bytes) -> str:
    return data.decode("cp037")


def encode_ba(addr: int) -> bytes:
    """Encode a 12-bit buffer address in the standard 2-byte 3270 form.

    The 14-bit/12-bit address uses a 6-bit-per-byte code table so the bytes stay
    in a safe range. We use the classic 12-bit scheme (good for a 24x80 = 1920
    buffer): each 6-bit half is mapped through SIXBIT.
    """
    addr &= 0x0FFF
    hi = (addr >> 6) & 0x3F
    lo = addr & 0x3F
    return bytes([_SIXBIT[hi], _SIXBIT[lo]])


def decode_ba(b0: int, b1: int) -> int:
    """Inverse of encode_ba: two address bytes -> 0-origin buffer offset."""
    return (_SIXBIT_INV.get(b0, 0) << 6) | _SIXBIT_INV.get(b1, 0)


# The 64-entry code used by the 12-bit buffer-address scheme (3270 standard).
_SIXBIT = [
    0x40, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
    0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F,
    0x50, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9,
    0x5A, 0x5B, 0x5C, 0x5D, 0x5E, 0x5F,
    0x60, 0x61, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9,
    0x6A, 0x6B, 0x6C, 0x6D, 0x6E, 0x6F,
    0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9,
    0x7A, 0x7B, 0x7C, 0x7D, 0x7E, 0x7F,
]
_SIXBIT_INV = {code: i for i, code in enumerate(_SIXBIT)}


def rc(row: int, col: int) -> int:
    return row * COLS + col


@dataclass
class OutField:
    """A field to place on an outbound screen (0-origin attribute position)."""

    row: int
    col: int                      # attribute-byte column; data starts at col+1
    attr: int
    text: str = ""                # initial data to the right of the attribute


def build_erase_write(fields: list[OutField], cursor: int | None = None) -> bytes:
    """Build an Erase/Write stream: WCC, then SF+data per field, then IC.

    The screen is addressed field by field: SBA to the attribute position, SF
    with the attribute byte, then the field's EBCDIC data. ``cursor`` is an
    absolute buffer offset for the Insert Cursor order.
    """
    out = bytearray()
    out.append(CMD_ERASE_WRITE)
    out.append(WCC_RESTORE_RESET)
    for f in sorted(fields, key=lambda x: rc(x.row, x.col)):
        pos = rc(f.row, f.col)
        out.append(ORDER_SBA)
        out += encode_ba(pos)
        out.append(ORDER_SF)
        out.append(f.attr)
        if f.text:
            out += ascii_to_ebcdic(f.text)
    if cursor is not None:
        out.append(ORDER_SBA)
        out += encode_ba(cursor)
        out.append(ORDER_IC)
    return bytes(out)


@dataclass
class InboundField:
    """A modified field read from an inbound stream: data at a buffer address."""

    addr: int                     # buffer offset of the first data byte
    text: str


@dataclass
class Inbound:
    aid: str
    cursor: int
    fields: list[InboundField]


def parse_inbound(data: bytes) -> Inbound:
    """Parse an inbound 3270 stream: AID, cursor address, then SBA+data runs.

    Modified fields arrive as: SBA <ba><ba> <ebcdic data...> repeated. Data runs
    until the next order byte. Orders other than SBA are skipped defensively.
    """
    if not data:
        return Inbound(aid="Clear", cursor=0, fields=[])
    aid = AID_NAMES.get(data[0], "Enter")
    cursor = 0
    i = 1
    if len(data) >= 3:
        cursor = decode_ba(data[1], data[2])
        i = 3
    fields: list[InboundField] = []
    while i < len(data):
        b = data[i]
        if b == ORDER_SBA and i + 2 < len(data):
            addr = decode_ba(data[i + 1], data[i + 2])
            i += 3
            start = i
            while i < len(data) and data[i] not in (ORDER_SBA, ORDER_SF, ORDER_IC):
                i += 1
            text = ebcdic_to_ascii(data[start:i])
            fields.append(InboundField(addr=addr, text=text))
        else:
            i += 1
    return Inbound(aid=aid, cursor=cursor, fields=fields)
