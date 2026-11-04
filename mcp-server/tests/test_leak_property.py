"""Property (task 4.6): for ANY screen the bridge can produce, hidden data never
reaches a tool result, a resource, the confirmation prompt or the audit file.

Uses the bridge's own Hypothesis strategy: hidden field data is the sentinel
'@', which appears nowhere else by construction.
"""
from hypothesis import HealthCheck, given, settings

from _strategies import SENTINEL, arbitrary_buffer  # bridge/tests/_strategies.py

from fakes import FakePort, ScreenSpec
from harness import Session, dump, human, make_rig


def spec_from_buffer(buf) -> ScreenSpec:
    spec = ScreenSpec({}, [])
    spec.text = list(buf.text)
    spec.starts = buf.field_starts
    spec.cursor = (buf.cursor_row, buf.cursor_col)
    return spec


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(arbitrary_buffer())
def test_hidden_sentinel_never_leaks_through_any_tool(buf):
    port = FakePort(screens={"s": spec_from_buffer(buf)}, start="s", transitions={})
    rig = make_rig(port=port)
    s = Session(rig, elicitation_callback=human(rig))
    outputs = [s.ok("connect"), s.ok("read_screen"), s.ok("list_fields")]

    # Type the sentinel into every hidden, unprotected field we can.
    for f in s.ok("list_fields")["result"]:
        if f["hidden"] and not f["protected"] and 0 < f["length"] and not f["numeric"]:
            outputs.append(s.ok("fill_field", field_ref=f["index"], value=SENTINEL * min(3, f["length"])))

    press = s.ok("press_key", key="ENTER")
    outputs.append(press)
    if press["status"] == "pending":
        outputs.append(s.call("confirm_action", action_id=press["action"]["action_id"]).structured_content)
    outputs += [s.ok("get_audit_log"), s.read_resource("screen://current"), s.read_resource("audit://log")]

    assert SENTINEL not in dump(outputs)
    assert SENTINEL not in rig.audit_text
    assert SENTINEL not in " ".join(rig.asked)
