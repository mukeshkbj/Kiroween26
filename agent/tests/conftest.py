"""Shared test fixtures and paths for the seance-agent suite.

All tests run against ``seance_mcp.fake`` with a scripted model: no network, no
credentials, no mainframe. ``integration`` and ``llm`` markers are deselected by
default in ``pyproject.toml``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# Repo root: agent/tests/conftest.py -> agent -> repo.
REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "docs" / "contracts" / "examples"
SCHEMAS = REPO_ROOT / "docs" / "contracts" / "schemas"


@pytest.fixture(scope="session")
def examples_dir() -> Path:
    return EXAMPLES


@pytest.fixture(scope="session")
def schemas_dir() -> Path:
    return SCHEMAS
