"""Live-container guard (P0.6, docs/contracts.md section 2.1)."""
import tempfile
from pathlib import Path

import anyio
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from seance_mcp.fake import FakePort
from seance_mcp.live import MARKER, live_allowed
from seance_mcp.safety import GateError

from harness import make_rig


_EMPTY_ROOT = Path(tempfile.mkdtemp())  # a directory with no marker file


class LivePort(FakePort):
    """Stands in for RealBridgePort: marked live, never opens a real session."""

    is_live = True


def test_live_allowed_needs_exactly_env_1_or_the_marker(tmp_path):
    assert not live_allowed({}, tmp_path)
    for v in ("0", "", "true", "yes", "2", " 1"):
        assert not live_allowed({"GSS_LIVE_OK": v}, tmp_path)
    assert live_allowed({"GSS_LIVE_OK": "1"}, tmp_path)
    (tmp_path / MARKER).write_text("")
    assert live_allowed({}, tmp_path)


def test_marker_is_per_checkout(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / MARKER).write_text("")
    assert live_allowed({}, a) and not live_allowed({}, b)


def test_connect_to_a_live_port_is_refused_and_audited_when_not_allowed():
    rig = make_rig(port=LivePort())
    rig.service._live_ok = lambda: False
    with pytest.raises(GateError) as e:
        anyio.run(rig.service.connect)
    assert e.value.code == "live_not_allowed"
    assert all(c[0] != "connect" for c in rig.port.calls) and not rig.port.connected
    assert rig.outcomes("connect") == ["live_not_allowed"]


def test_connect_to_a_live_port_works_when_allowed():
    rig = make_rig(port=LivePort())
    rig.service._live_ok = lambda: True
    anyio.run(rig.service.connect)
    assert rig.port.connected


def test_fake_ports_are_never_blocked():
    rig = make_rig(port=FakePort())
    rig.service._live_ok = lambda: False
    anyio.run(rig.service.connect)
    assert rig.port.connected


def test_real_port_is_marked_live():
    from seance_mcp.port import RealBridgePort

    assert RealBridgePort.is_live is True


def test_refusal_goes_through_the_mcp_tool_with_a_stable_code():
    from harness import Session

    rig = make_rig(port=LivePort())
    rig.service._live_ok = lambda: False
    assert "[live_not_allowed]" in Session(rig).err("connect")


@settings(deadline=None, max_examples=200)
@given(st.dictionaries(st.text(max_size=8), st.text(max_size=8), max_size=4))
def test_property_only_the_exact_env_value_allows(tmp_path_factory, env):
    root = _EMPTY_ROOT   # one directory with no marker; creating one per example is slow and pointless
    assert live_allowed(env, root) == (env.get("GSS_LIVE_OK") == "1")