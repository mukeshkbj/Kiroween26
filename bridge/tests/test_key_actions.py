"""s3270 key wire form (Agent A's request, 2026-11-05): PF3 -> PF(3), allowlist only."""
import pytest
from hypothesis import given
from hypothesis import strategies as st

from seance_bridge import Key, SessionError
from seance_bridge.session import Session, s3270_key_action


def test_documented_forms():
    assert s3270_key_action("Enter") == "Enter"
    assert s3270_key_action("Clear") == "Clear"
    assert s3270_key_action("PF3") == "PF(3)"
    assert s3270_key_action("PF24") == "PF(24)"
    assert s3270_key_action("PA1") == "PA(1)"


@pytest.mark.parametrize("key", list(Key))
def test_every_bridge_key_has_a_valid_action(key):
    act = s3270_key_action(key.value)
    assert act in ("Enter", "Clear") or act.startswith(("PF(", "PA("))


@pytest.mark.parametrize("bad", ["PF0", "PF25", "PA0", "PA4", "pf3", "ENTER", "enter", "PF03", "PF(3)", "",
                                 "Enter\nQuit", "String(x)", "Quit", "Disconnect", "PF3 ", " PF3", "PF3;Quit"])
def test_anything_else_is_refused_not_forwarded(bad):
    with pytest.raises(SessionError):
        s3270_key_action(bad)


@given(st.text(max_size=20))
def test_property_output_is_always_a_known_safe_action(s):
    try:
        out = s3270_key_action(s)
    except SessionError:
        return
    assert out in ("Enter", "Clear") or (out[:3] in ("PF(", "PA(") and out.endswith(")") and out[3:-1].isdigit())
    assert "\n" not in out and ";" not in out


class _Recorder(Session):
    def __init__(self):
        self._proc = None  # never spawn s3270: _exec is replaced below
        self.sent: list[str] = []

    def _exec(self, command):  # type: ignore[override]
        self.sent.append(command)
        return [], "", True

    def wait_unlock(self, timeout_s):  # type: ignore[override]
        self.sent.append("<wait_unlock>")


def test_press_key_sends_the_translated_action_once_then_waits():
    s = _Recorder()
    s.press_key("PF3")
    assert s.sent == ["PF(3)", "<wait_unlock>"]
    s.sent.clear()
    with pytest.raises(SessionError):
        s.press_key("Quit")
    assert s.sent == []  # nothing reached s3270
