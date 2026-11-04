"""Shared pytest config.

Integration tests are marked ``@pytest.mark.integration`` and run only when a TK4-
container is up (``TN3270_HOST`` set) AND live use is allowed in this checkout
(``GSS_LIVE_OK=1`` or the gitignored marker file ``.gss-live-ok`` in the repo root;
docs/contracts.md section 2.1: only Agent A and the integrator touch the container).
"""
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


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