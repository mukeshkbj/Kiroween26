"""Integration test against a live TK4- 3270 session.

This is the project go/no-go: if it passes, the core idea works -- the bridge can
read a real 3270 screen into a structured, deterministic ScreenModel with fields.
Skipped unless ``TN3270_HOST`` is set (see conftest.py).

The bridge's Session auto-finds s3270: the S3270_PATH env var, a repo-local
``.tools/s3270.exe`` (Windows), or ``s3270`` on PATH.
"""
import os

import pytest

from seance_bridge import Bridge
from seance_bridge.keys import Key


@pytest.mark.integration
def test_tk4_screen_read_go_no_go():
    host = os.environ["TN3270_HOST"]
    port = int(os.environ.get("TN3270_PORT", "3270"))

    bridge = Bridge(host, port)
    bridge.connect()
    try:
        # Banner: two reads must give the same screen_id (deterministic parsing).
        banner = bridge.read_screen()
        assert banner.screen_id == bridge.read_screen().screen_id
        assert len(banner.fields) > 0, "expected a structured (formatted) screen"

        # Past the banner, the TK4- command screen exposes an unprotected field.
        bridge.press(Key.ENTER)
        cmd = bridge.read_screen()
        assert any(not f.protected for f in cmd.fields), "expected >=1 unprotected field"
    finally:
        bridge.disconnect()
