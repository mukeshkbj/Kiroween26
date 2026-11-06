"""Unit tests for the 3270 datastream helpers (no mainframe needed)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seance_standin import datastream as ds  # noqa: E402


def test_ba_roundtrip() -> None:
    for addr in (0, 1, 79, 80, 160, 1919):
        enc = ds.encode_ba(addr)
        assert len(enc) == 2
        assert ds.decode_ba(enc[0], enc[1]) == addr


def test_field_attr_flags_match_bridge_decoding() -> None:
    # seance_bridge.readbuffer decodes: 0x20 protected, 0x10 numeric,
    # 0x0C non-display, 0x08 intensified.
    assert ds.field_attr(protected=True) & 0x20
    assert ds.field_attr(protected=False) & 0x20 == 0
    assert ds.field_attr(protected=False, numeric=True) & 0x10
    assert ds.field_attr(protected=True, hidden=True) & 0x0C == 0x0C
    assert ds.field_attr(protected=True, intensified=True) & 0x08
    # hidden must win over intensified (both set bits 2-3; non-display is 0x0C)
    a = ds.field_attr(protected=True, hidden=True, intensified=True)
    assert a & 0x0C == 0x0C


def test_erase_write_has_wcc_and_sf_orders() -> None:
    f = ds.OutField(0, 0, ds.field_attr(protected=True), "HI")
    stream = ds.build_erase_write([f], cursor=ds.rc(0, 0))
    assert stream[0] == ds.CMD_ERASE_WRITE
    assert stream[1] == ds.WCC_RESTORE_RESET
    assert ds.ORDER_SF in stream
    assert ds.ORDER_IC in stream


def test_parse_inbound_reads_aid_cursor_and_fields() -> None:
    # Build an inbound: AID=Enter, cursor at (7,15), one modified field "3"
    data = bytearray([0x7D])                 # Enter
    data += ds.encode_ba(ds.rc(7, 15))       # cursor
    data.append(ds.ORDER_SBA)
    data += ds.encode_ba(ds.rc(7, 15))
    data += ds.ascii_to_ebcdic("3")
    inbound = ds.parse_inbound(bytes(data))
    assert inbound.aid == "Enter"
    assert inbound.cursor == ds.rc(7, 15)
    assert len(inbound.fields) == 1
    assert inbound.fields[0].addr == ds.rc(7, 15)
    assert inbound.fields[0].text == "3"


def test_parse_inbound_empty_is_clear() -> None:
    assert ds.parse_inbound(b"").aid == "Clear"
