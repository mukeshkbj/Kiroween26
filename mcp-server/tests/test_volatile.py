"""The MCP path must mask the TK4- welcome clock, or every repaint changes screen_id
(which would also trip the safety gate's stale-screen check on a pending action)."""
import anyio
import pytest

from seance_bridge import Bridge
from seance_bridge.models import BUFFER_SIZE, COLS, Buffer
from seance_bridge.session import Session

import seance_mcp.port as port_mod
from seance_mcp.config import TK4_CLOCK_REGIONS, Settings, parse_regions
from seance_mcp.port import RealBridgePort


class _StubSession(Session):
    """No subprocess; serves whatever ``buf`` currently is."""

    def __init__(self):
        self.buf = _welcome("Date 2026-11-04", "Time 10:00:01")

    def connect(self, host, port):
        pass

    def disconnect(self):
        pass

    def read_buffer(self):
        return self.buf


def _welcome(date: str, time_: str) -> Buffer:
    grid = [" "] * BUFFER_SIZE
    for row, col, txt in (
        (0, 1, "Terminal: LCL1"), (0, 64, date), (1, 64, time_), (22, 0, "Logon ===>"),
    ):
        for i, ch in enumerate(txt):
            grid[row * COLS + col + i] = ch
    return Buffer(text="".join(grid))


@pytest.fixture
def stub(monkeypatch):
    s = _StubSession()

    def make(host, port, **kw):
        return Bridge(host, port, session=s, volatile_gap_s=0, **kw)

    monkeypatch.setattr(port_mod, "Bridge", make)
    return s


def _ids_across_repaint(port: RealBridgePort, stub: _StubSession) -> tuple[str, str]:
    async def go():
        first = await port.connect("h", 3270)
        stub.buf = _welcome("Date 2026-11-04", "Time 10:07:59")  # repaint: clock moved on
        second = await port.read_screen()
        return first.screen_id, second.screen_id

    return anyio.run(go)


def test_default_port_masks_welcome_clock(stub):
    a, b = _ids_across_repaint(RealBridgePort(), stub)
    assert a == b


def test_without_regions_the_clock_leaks_into_screen_id(stub):
    # Guards the test above: proves the repaint really would change the id.
    a, b = _ids_across_repaint(RealBridgePort(volatile_regions=()), stub)
    assert a != b


def test_masking_does_not_hide_real_screen_changes(stub):
    async def go():
        port = RealBridgePort()
        first = await port.connect("h", 3270)
        stub.buf = Buffer(text=_welcome("Date 2026-11-04", "Time 10:00:01").text.replace(
            "Logon ===>", "Other ===>"))
        return first.screen_id, (await port.read_screen()).screen_id

    a, b = anyio.run(go)
    assert a != b


def test_settings_default_masks_tk4_clock():
    assert Settings.from_env({}).volatile_regions == TK4_CLOCK_REGIONS


def test_settings_regions_from_env_and_none():
    assert Settings.from_env({"VOLATILE_REGIONS": "2,10,5;3,0,8"}).volatile_regions == (
        (2, 10, 5), (3, 0, 8))
    assert Settings.from_env({"VOLATILE_REGIONS": "none"}).volatile_regions == ()


@pytest.mark.parametrize("bad", ["1,2", "a,b,c", "-1,0,5", "0,0,0"])
def test_bad_regions_are_an_error_not_a_fallback(bad):
    with pytest.raises(ValueError):
        parse_regions(bad)
