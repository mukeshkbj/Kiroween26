"""Shared pytest config: integration tests skip unless a live session is both
available (TN3270_HOST) and allowed in this checkout (GSS_LIVE_OK=1 or .gss-live-ok;
docs/contracts.md section 2.1)."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Re-use the bridge's Hypothesis buffer strategy (tests/_strategies.py).
sys.path.insert(0, str(ROOT / "bridge" / "tests"))


def live_allowed() -> bool:
    return os.environ.get("GSS_LIVE_OK") == "1" or (ROOT / ".gss-live-ok").is_file()


def pytest_collection_modifyitems(config, items):
    if os.environ.get("TN3270_HOST") and live_allowed():
        return
    why = ("TN3270_HOST unset; needs a live TK4- 3270 session" if not os.environ.get("TN3270_HOST")
           else "live container not allowed in this checkout (GSS_LIVE_OK=1 or .gss-live-ok)")
    skip = pytest.mark.skip(reason=why)
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)