"""An unanswered AID (bridge AmbiguousAckError) is surfaced, never retried, and forces a resync.

Agent A found live on TK4- that an AID can go unanswered forever; the bridge now bounds it and
raises AmbiguousAckError. The service must report `ambiguous_ack`, drop any pending action,
refuse further keys until the screen is re-read, and the real port must forget the dead bridge.
"""
import anyio
import pytest

from seance_bridge import AmbiguousAckError, Key
from seance_mcp.config import ConfirmMode
from seance_mcp.fake import FakePort
from seance_mcp.port import RealBridgePort
from seance_mcp.safety import GateError, decide

from harness import make_rig


class SilentPort(FakePort):
    """Every key press goes out and then the host never answers."""

    async def press(self, key: Key):
        self.calls.append(("press", key.value))
        raise AmbiguousAckError("no answer from s3270 to PF")


def run(coro):
    async def go():
        return await coro

    return anyio.run(go)


def test_unanswered_key_is_reported_audited_sent_once_and_forces_resync():
    rig = make_rig(port=SilentPort(), mode=ConfirmMode.OOB)
    run(rig.service.connect())
    with pytest.raises(GateError) as e:
        run(rig.service.press_key("CLEAR"))            # non-commit key, executes immediately
    assert e.value.code == "ambiguous_ack" and "NOTHING was resent" in e.value.message
    assert rig.port.pressed == ["Clear"]                # sent exactly once
    assert rig.outcomes("press_key")[-1] == "ambiguous_ack"
    with pytest.raises(GateError) as e2:                # nothing may be pressed until the screen is re-read
        run(rig.service.press_key("CLEAR"))
    assert e2.value.code == "needs_resync" and rig.port.pressed == ["Clear"]
    run(rig.service.read_screen())                      # the caller has now seen the real screen
    assert rig.gate.needs_resync is False


def test_unanswered_confirmed_commit_drops_the_pending_action_and_is_not_retried():
    rig = make_rig(port=SilentPort(), mode=ConfirmMode.OOB)
    run(rig.service.connect())
    p = run(rig.service.press_key("ENTER"))             # commit-capable: pending, not sent
    aid = p.action.action_id
    assert rig.port.pressed == []
    rig.gate.approve_oob(aid, "web-ui:t")
    d = decide(ConfirmMode.OOB, None, "t", rig.gate.peek(aid))
    with pytest.raises(GateError) as e:
        run(rig.service.confirm_action(aid, d))
    assert e.value.code == "ambiguous_ack"
    assert rig.port.pressed == ["Enter"]                # the commit key went out once
    assert rig.gate.pending is None                     # the action cannot be replayed
    with pytest.raises(GateError):                      # and a second confirm cannot resend it
        run(rig.service.confirm_action(aid, d))
    assert rig.port.pressed == ["Enter"]


def test_real_port_forgets_its_dead_bridge_after_an_ambiguous_ack():
    class DeadBridge:
        def press(self, key):
            raise AmbiguousAckError("no answer")

        def read_screen(self):
            raise AmbiguousAckError("no answer")

        def disconnect(self):
            pass

    for call in (lambda p: p.press(Key.PF3), lambda p: p.read_screen()):
        port = RealBridgePort()
        port._bridge = DeadBridge()  # type: ignore[assignment]
        assert port.connected
        with pytest.raises(AmbiguousAckError):
            run(call(port))
        assert not port.connected                        # later calls say "not connected", not hang
