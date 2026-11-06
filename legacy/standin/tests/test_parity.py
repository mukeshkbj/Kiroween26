"""Contract parity: the stand-in's screens hash to the SAME screen_id as
seance_mcp.fake.fake_insurance() (contracts section 10).

Why it matters: B's approved key policy and seed are keyed by screen_id. If the
ids match, the policy approved on the fake applies unchanged to the live,
COBOL-backed app.

Each stand-in screen is rendered into a bridge Buffer, mirroring what s3270
decodes from our Erase/Write: plain text first, field starts on top, attribute
cells blank. That Buffer goes through the real ScreenParser with the contract
VOLATILE_REGIONS. Needs seance_bridge + seance_mcp, so run it with
mcp-server/.venv; it skips otherwise.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

bridge = pytest.importorskip("seance_bridge")
fake = pytest.importorskip("seance_mcp.fake")

from seance_standin.datastream import COLS, SIZE, rc  # noqa: E402
from seance_standin.screens import VOLATILE_REGIONS, all_screens  # noqa: E402


def _attrs(a: int):
    return bridge.FieldAttrs(protected=bool(a & 0x20), numeric=bool(a & 0x10),
                             hidden=(a & 0x0C) == 0x0C,
                             intensified=bool(a & 0x08) and (a & 0x0C) != 0x0C)


def _buffer(screen, values: dict[str, str]):
    grid = [" "] * SIZE
    for t in screen.texts():
        for i, ch in enumerate(t.text):
            grid[rc(t.row, t.col) + i] = ch
    starts = []
    for f in screen.out_fields(values):
        pos = rc(f.row, f.col)
        grid[pos] = " "
        for i, ch in enumerate(f.text):
            grid[pos + 1 + i] = ch
        starts.append(bridge.FieldStart(pos=pos, attrs=_attrs(f.attr)))
    cur = screen.cursor_offset()
    return bridge.Buffer(text="".join(grid), field_starts=tuple(starts),
                         cursor_row=cur // COLS, cursor_col=cur % COLS)


def _vol():
    return fake.region_positions(VOLATILE_REGIONS)


@pytest.mark.parametrize("name", ["menu", "enquiry", "list", "update", "confirm"])
def test_empty_screen_id_equals_fake(name: str) -> None:
    ours = bridge.ScreenParser().parse(_buffer(all_screens()[name], {}), _vol())
    theirs = fake.fake_insurance().screens[name].model()
    assert ours.rows == theirs.rows
    assert ours.screen_id == theirs.screen_id


def test_screen_id_ignores_output_data_and_messages() -> None:
    # A result screen (holder etc. filled, message set) must keep the empty
    # screen's id, or a per-screen key policy would never match a result.
    enq = all_screens()["enquiry"]
    empty = bridge.ScreenParser().parse(_buffer(enq, {}), _vol()).screen_id
    filled = bridge.ScreenParser().parse(_buffer(enq, {
        "polno": "P0000003", "out_5_13": "A. ROSE", "out_6_13": "ACTIVE",
        "out_7_13": "250.00", "out_8_13": "2026-10-21", "msg": "POLICY NOT FOUND"}), _vol()).screen_id
    assert empty == filled
