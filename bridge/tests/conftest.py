"""Shared pytest config.

Integration tests are marked ``@pytest.mark.integration`` and skipped unless
``TN3270_HOST`` is set (i.e. a TK4- container is running).
"""
import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("TN3270_HOST"):
        return
    skip = pytest.mark.skip(reason="TN3270_HOST unset; needs a live TK4- 3270 session")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
