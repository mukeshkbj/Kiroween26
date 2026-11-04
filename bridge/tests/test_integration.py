"""Integration tests against a live TK4- 3270 session (the go/no-go).

If these pass, the core idea works: the bridge reads a real 3270 screen into a
structured, deterministic ScreenModel that matches what s3270 itself renders.
Skipped unless ``TN3270_HOST`` is set (see conftest.py).

The bridge's Session auto-finds s3270: the S3270_PATH env var, a repo-local
``.tools/s3270.exe`` (Windows), or ``s3270`` on PATH.
"""
import os
import time

import pytest

from seance_bridge import Bridge, ScreenParser
from seance_bridge.keys import Key

LOGON_ROW, LOGON_COL = 22, 0      # "Logon ===>" on the TK4- VTAM welcome screen
# Date / Time stamps in the top-right corner are fixed at paint time.
CLOCK_REGIONS = [(0, 64, 16), (1, 64, 16)]


def _open(**kw) -> Bridge:
    host = os.environ["TN3270_HOST"]
    port = int(os.environ.get("TN3270_PORT", "3270"))
    bridge = Bridge(host, port, **kw)
    bridge.connect()
    return bridge


def _reach_logon(bridge: Bridge):
    """Return the VTAM welcome screen. CLEAR is a non-committing key; used only
    if the banner is still showing after connect settled."""
    screen = bridge.read_screen()
    for _ in range(2):
        if "Logon ===>" in screen.rows[LOGON_ROW]:
            return screen
        screen = bridge.press(Key.CLEAR).screen
    assert "Logon ===>" in screen.rows[LOGON_ROW], "never reached the logon screen"
    return screen


@pytest.mark.integration
def test_tk4_screen_read_go_no_go():
    bridge = _open(volatile_regions=CLOCK_REGIONS)
    try:
        screen = _reach_logon(bridge)

        # Stable identity across reads.
        assert screen.screen_id == bridge.read_screen().screen_id

        # Logon prompt is where the real screen puts it (a misaligned parse fails).
        assert screen.rows[LOGON_ROW][LOGON_COL:LOGON_COL + 10] == "Logon ===>"
        assert screen.rows[0].startswith("Terminal")

        # Cursor is 0-origin and sits inside the unprotected logon input field.
        assert screen.cursor == (22, 11)
        field = ScreenParser.field_at(screen, *screen.cursor)
        assert field is not None and not field.protected and field.length > 0

        # Row by row against s3270's own Ascii() rendering.
        ascii_rows = bridge.session.ascii_rows()
        again = bridge.read_screen()
        for r, (parsed, reference) in enumerate(zip(again.rows, ascii_rows)):
            assert parsed == reference, f"row {r} differs:\n parsed={parsed!r}\n ascii ={reference!r}"
    finally:
        bridge.disconnect()


@pytest.mark.integration
def test_repaint_changes_clock_but_not_masked_screen_id():
    """The welcome screen's Date/Time is stamped at paint time: two quick reads
    agree, but a repaint differs. Masking the clock region keeps the id stable."""
    plain = _open()
    masked = Bridge(plain._host, plain._port, volatile_regions=CLOCK_REGIONS)
    try:
        plain_first = _reach_logon(plain).screen_id
        time.sleep(1.2)
        plain_second = plain.press(Key.CLEAR).screen
        assert plain_first != plain_second.screen_id, "clock should leak into an unmasked id"
    finally:
        plain.disconnect()

    masked.connect()
    try:
        first = _reach_logon(masked).screen_id
        time.sleep(1.2)
        second = masked.press(Key.CLEAR).screen
        assert first == second.screen_id
        assert second.rows[0].rstrip().endswith(tuple("0123456789"))  # clock still visible
    finally:
        masked.disconnect()
