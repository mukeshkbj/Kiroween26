"""The hand-written golden key policy for fake_insurance (docs/contracts.md 10.2).

Only ENTER on ``confirm`` can change data. Everything else the app does with ENTER
or PF keys is navigation or lookup. This is the policy B's approved policy must
equal (modulo screen_id) and what lets mcp-server task 6.3 close for the fake.
"""
from __future__ import annotations

from ..fake import FakeApp, fake_insurance

GOLDEN_READ_ONLY_KEYS: dict[str, list[str]] = {
    "menu": ["ENTER", "PF3"],
    "enquiry": ["ENTER", "PF3"],
    "list": ["ENTER", "PF3", "PF7", "PF8"],
    "update": ["ENTER", "PF3"],
    "confirm": ["PF3"],
}

SCREEN_ORDER = ["menu", "enquiry", "list", "update", "confirm"]


def screen_ids(app: FakeApp | None = None) -> dict[str, str]:
    app = app or fake_insurance()
    return {name: app.screens[name].model().screen_id for name in SCREEN_ORDER}


def node_id(screen_id: str) -> str:
    return "n_" + screen_id[:10]


def golden_policy(app: FakeApp | None = None) -> dict[str, dict[str, list[str]]]:
    """{screen_id: {"read_only_keys": [...]}} in the exact format KeyPolicy.load reads."""
    ids = screen_ids(app)
    return {ids[name]: {"read_only_keys": keys} for name, keys in GOLDEN_READ_ONLY_KEYS.items()}
