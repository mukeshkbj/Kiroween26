"""Unit tests for the raw 3270 datastream decoder.

These use hand-crafted datastreams (order bytes + ASCII text) to check that
decode_orders walks the buffer correctly. The real s3270 ReadBuffer textual
format is exercised by the integration test instead.
"""
from seance_bridge.orders import decode_orders
from seance_bridge.models import COLS, BUFFER_SIZE


def _pos(row, col):
    return row * COLS + col


def _addr_bytes(pos):
    # 12-bit address, each byte carries 6 bits with 0x40 set
    return bytes([0x40 | ((pos >> 6) & 0x3F), 0x40 | (pos & 0x3F)])


def test_empty_datastream_is_blank_grid():
    buf = decode_orders(b"")
    assert len(buf.text) == BUFFER_SIZE
    assert buf.text == " " * BUFFER_SIZE
    assert buf.field_starts == ()


def test_text_is_written_at_current_position():
    # write "HI" starting at (0,0)
    buf = decode_orders(b"HI")
    assert buf.text[0] == "H"
    assert buf.text[1] == "I"


def test_sba_moves_position():
    pos = _pos(2, 5)
    # SBA order (0x34) + 2-byte address + text
    ds = bytes([0x34]) + _addr_bytes(pos) + b"X"
    buf = decode_orders(ds)
    assert buf.text[pos] == "X"


def test_start_field_records_attribute_and_advances():
    pos = _pos(0, 0)
    # SBA to (0,0), then SF with protected+normal-display attribute (0x88), then "AB"
    ds = bytes([0x34]) + _addr_bytes(pos) + bytes([0x1D, 0x88]) + b"AB"
    buf = decode_orders(ds)
    assert len(buf.field_starts) == 1
    assert buf.field_starts[0].pos == pos
    assert buf.field_starts[0].attrs.protected is True
    # attribute byte position is blank; data starts at pos+1
    assert buf.text[pos] == " "
    assert buf.text[pos + 1] == "A"
    assert buf.text[pos + 2] == "B"


def test_insert_cursor_sets_cursor():
    pos = _pos(3, 7)
    ds = bytes([0x34]) + _addr_bytes(pos) + bytes([0x13])
    buf = decode_orders(ds)
    assert (buf.cursor_row, buf.cursor_col) == (3, 7)


def test_non_printable_bytes_become_spaces():
    buf = decode_orders(bytes([0x01, 0x7F]))
    assert buf.text[0] == " "
    assert buf.text[1] == " "  # 0x7f is outside 0x20-0x7e
