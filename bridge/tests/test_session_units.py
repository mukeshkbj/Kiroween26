"""Unit tests for s3270 protocol helpers (no emulator needed)."""
import pytest

from seance_bridge import Bridge, SessionError
from seance_bridge.models import BUFFER_SIZE, COLS, Buffer
from seance_bridge.readbuffer import parse_readbuffer_ascii
from seance_bridge.session import Session, quote_string_arg


def test_status_cursor_is_zero_origin():
    kb, row, col = Session._parse_status("U F U C(127.0.0.1) I 4 24 80 22 11 0x0 0.001")
    assert (kb, row, col) == ("U", 22, 11)


def test_status_cursor_origin_stays_zero():
    assert Session._parse_status("U F U C(h) I 4 24 80 0 0 0x0 -")[1:] == (0, 0)


@pytest.mark.parametrize(
    "text, quoted",
    [
        ("HERC01", '"HERC01"'),
        ('say "hi"', '"say \\"hi\\""'),
        ("a\\b", '"a\\\\b"'),
        ("(parens), commas", '"(parens), commas"'),
    ],
)
def test_quote_string_arg(text, quoted):
    assert quote_string_arg(text) == quoted


@pytest.mark.parametrize("bad", ["a\nEnter", "x\ry", "tab\there", "nul\x00"])
def test_quote_string_rejects_control_characters(bad):
    with pytest.raises(SessionError):
        quote_string_arg(bad)


def test_readbuffer_strips_data_prefix_and_is_row_aligned():
    lines = ["data: 41 42", "data: 43", "data: 44 45"]
    buf = parse_readbuffer_ascii(lines)
    assert buf.text[0:2] == "AB"
    assert buf.text[COLS] == "C"          # short row 0/1 does not shift row 2
    assert buf.text[2 * COLS : 2 * COLS + 2] == "DE"


def test_readbuffer_short_and_empty_lines_do_not_shift_later_rows():
    buf = parse_readbuffer_ascii(["41", "", "42 43"])
    assert buf.text[0] == "A"
    assert buf.text[2 * COLS : 2 * COLS + 2] == "BC"


def test_readbuffer_overlong_row_is_clipped_not_wrapped():
    buf = parse_readbuffer_ascii([" ".join(["41"] * 100), "42"])
    assert buf.text[COLS] == "B"


def test_readbuffer_high_codes_use_latin1_like_ascii_action():
    buf = parse_readbuffer_ascii(["aa 7c"])
    assert buf.text[0] == "\u00aa" and buf.text[1] == "|"


class _FakeSession(Session):
    """Serves queued Buffers; no subprocess."""

    def __init__(self, buffers):
        self._buffers = list(buffers)

    def read_buffer(self):
        return self._buffers.pop(0) if len(self._buffers) > 1 else self._buffers[0]


def _buf(text: str) -> Buffer:
    return Buffer(text=(text + " " * BUFFER_SIZE)[:BUFFER_SIZE])


def test_bridge_reads_twice_and_masks_changed_positions():
    a = _buf("Time 10:00:01 MENU")
    b = _buf("Time 10:00:02 MENU")
    c = _buf("Time 10:00:03 MENU")
    bridge = Bridge("x", session=_FakeSession([a, b]), volatile_gap_s=0)
    s1 = bridge.read_screen()
    assert s1.volatile == (12,)                  # only the changed digit
    bridge2 = Bridge("x", session=_FakeSession([b, c]), volatile_gap_s=0)
    # Different second, same masked position -> same screen_id.
    assert bridge2.read_screen().screen_id == s1.screen_id


def test_bridge_static_volatile_region_masks_repaint_stamps():
    a = _buf("Time 10:00:01 MENU")
    b = _buf("Time 10:07:59 MENU")
    kw = dict(volatile_regions=[(0, 5, 8)], volatile_gap_s=0)
    ida = Bridge("x", session=_FakeSession([a]), **kw).read_screen().screen_id
    idb = Bridge("x", session=_FakeSession([b]), **kw).read_screen().screen_id
    assert ida == idb
    plain_a = Bridge("x", session=_FakeSession([a]), volatile_gap_s=0).read_screen().screen_id
    plain_b = Bridge("x", session=_FakeSession([b]), volatile_gap_s=0).read_screen().screen_id
    assert plain_a != plain_b                    # without the region the clock leaks in
