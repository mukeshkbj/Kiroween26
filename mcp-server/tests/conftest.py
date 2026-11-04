"""Shared pytest config: integration tests skip unless TN3270_HOST is set."""
import os
import sys
from pathlib import Path

import pytest

# Re-use the bridge's Hypothesis buffer strategy (tests/_strategies.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bridge" / "tests"))


def pytest_collection_modifyitems(config, items):
    if os.environ.get("TN3270_HOST"):
        return
    skip = pytest.mark.skip(reason="TN3270_HOST unset; needs a live TK4- 3270 session")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
