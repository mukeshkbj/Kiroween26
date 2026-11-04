"""Property-based tests (Hypothesis) for ScreenParser.

These are the go/no-go de-risking tests for the parser logic. They run with no
emulator and prove the core invariants hold for any valid buffer.
"""
from hypothesis import given, settings, HealthCheck

from seance_bridge.models import BUFFER_SIZE, COLS, ROWS, Buffer
from seance_bridge.parser import ScreenParser

from _strategies import SENTINEL, arbitrary_buffer, change_unprotected_data

PARSER = ScreenParser()

_SETTINGS = dict(deadline=None, suppress_health_check=[HealthCheck.too_slow])


@settings(max_examples=200, **_SETTINGS)
@given(arbitrary_buffer())
def test_parse_never_crashes(buf):
    PARSER.parse(buf)


@settings(max_examples=200, **_SETTINGS)
@given(arbitrary_buffer())
def test_rows_are_24x80(buf):
    screen = PARSER.parse(buf)
    assert len(screen.rows) == ROWS
    assert all(len(r) == COLS for r in screen.rows)


@settings(max_examples=200, **_SETTINGS)
@given(arbitrary_buffer())
def test_fields_in_bounds_and_disjoint(buf):
    screen = PARSER.parse(buf)
    ranges = sorted((f.row * COLS + f.col, f.row * COLS + f.col + f.length) for f in screen.fields)
    for b, e in ranges:
        assert 0 <= b <= BUFFER_SIZE
        assert 0 <= e <= BUFFER_SIZE
        assert b <= e
    for (b1, e1), (b2, e2) in zip(ranges, ranges[1:]):
        assert e1 <= b2  # data regions never overlap


@settings(max_examples=200, **_SETTINGS)
@given(arbitrary_buffer())
def test_hidden_values_never_leak(buf):
    screen = PARSER.parse(buf)
    flat = "".join(screen.rows)
    assert SENTINEL not in flat          # sentinel only ever lives in hidden data
    for f in screen.fields:
        if f.hidden:
            assert f.value is None


@settings(max_examples=100, **_SETTINGS)
@given(arbitrary_buffer())
def test_screen_id_deterministic(buf):
    assert PARSER.parse(buf).screen_id == PARSER.parse(buf).screen_id


@settings(max_examples=200, **_SETTINGS)
@given(arbitrary_buffer())
def test_screen_id_invariant_under_unprotected_value_change(buf):
    id1 = PARSER.parse(buf).screen_id
    id2 = PARSER.parse(change_unprotected_data(buf)).screen_id
    assert id1 == id2


@settings(max_examples=100, **_SETTINGS)
@given(arbitrary_buffer())
def test_screen_id_invariant_under_cursor_change(buf):
    other = Buffer(
        text=buf.text,
        field_starts=buf.field_starts,
        cursor_row=(buf.cursor_row + 1) % ROWS,
        cursor_col=buf.cursor_col,
    )
    assert PARSER.parse(buf).screen_id == PARSER.parse(other).screen_id
