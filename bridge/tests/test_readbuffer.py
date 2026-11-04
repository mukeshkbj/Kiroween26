"""Unit tests for the s3270 ReadBuffer(Ascii) text parser.

These prove the adapter is self-consistent with the documented token format.
The real s3270 output is validated by the integration test (format/flag details
are confirmed against TK4- then).
"""
from seance_bridge.readbuffer import parse_readbuffer_ascii


def test_protected_label_then_input_field():
    # row tokens: "POLICY NO", then a protected SF, then input "ABC"
    tokens = " ".join([
        "50", "4F", "4C", "49", "43", "59", "20", "4E", "4F",   # P O L I C Y (sp) N O
        "SF(c0=20)",                                              # protected field start
        "41", "42", "43",                                         # A B C
    ])
    buf = parse_readbuffer_ascii(tokens)
    assert buf.text[0:9] == "POLICY NO"
    assert len(buf.field_starts) == 1
    assert buf.field_starts[0].pos == 9
    assert buf.field_starts[0].attrs.protected is True
    assert buf.text[10:13] == "ABC"


def test_non_display_field_is_hidden():
    # SF with c0=0c (non-display) decodes to hidden
    tokens = "SF(c0=0c) 41 42"
    buf = parse_readbuffer_ascii(tokens)
    assert buf.field_starts[0].attrs.hidden is True
    assert buf.text[1:3] == "AB"


def test_null_and_dash_become_spaces():
    tokens = "00 -"  # 0x00 NULL -> blank; literal "-" DBCS continuation token -> blank
    buf = parse_readbuffer_ascii(tokens)
    assert buf.text[0] == " "
    assert buf.text[1] == " "


def test_sa_extended_attribute_does_not_consume_position():
    # SA(...) is not a display position; the following 41 lands at pos 0
    tokens = "SA(c0=20) 41"
    buf = parse_readbuffer_ascii(tokens)
    assert buf.text[0] == "A"
    assert buf.field_starts == ()


def test_multiple_rows_fill_top_to_bottom():
    row0 = "41 42"   # A B at positions 0,1
    row1 = "43 44"   # C D at positions 80,81
    buf = parse_readbuffer_ascii(row0 + "\n" + row1)
    assert buf.text[0] == "A"
    assert buf.text[1] == "B"
    assert buf.text[80] == "C"
    assert buf.text[81] == "D"
