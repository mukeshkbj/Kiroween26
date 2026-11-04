"""Step and audit observers (P0.4): live events for the planchette and audit drawer."""
from __future__ import annotations

import json

import anyio
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from _strategies import SENTINEL, arbitrary_buffer  # bridge/tests/_strategies.py
from seance_mcp.config import ConfirmMode
from seance_mcp.fake import FakePort, ScreenSpec, fake_insurance, logon_screen, menu_screen

from harness import make_rig


def run(coro):
    async def go():
        return await coro

    return anyio.run(go)


def collect(service):
    events = []
    service.observe(events.append)
    return events


def shape(events):
    return [(e.tool, e.phase, e.outcome) for e in events]


def test_fill_then_press_emit_start_end_with_target_and_redaction():
    rig = make_rig(port=FakePort())
    ev = collect(rig.service)
    run(rig.service.connect())
    ev.clear()
    run(rig.service.fill_field((5, 16), "BOB"))         # USERID
    f = ev[0]
    assert (f.tool, f.phase) == ("fill_field", "start") and f.value == "BOB"
    assert (f.target.row, f.target.col, f.target.length) == (5, 16, 8) and f.target.label.startswith("USERID")
    assert f.screen_before is not None and ev[1].phase == "end" and ev[1].outcome == "ok"
    assert ev[1].screen_after is not None and ev[1].screen_after.screen_id
    ev.clear()
    run(rig.service.fill_field((6, 16), "hunter2"))     # PASSWORD (hidden)
    run(rig.service.fill_field((8, 16), "9999"))        # PIN (hidden, numeric)
    run(rig.service.fill_field((7, 16), "123"))         # ACCOUNT
    blob = json.dumps([e.model_dump() for e in ev])
    assert "hunter2" not in blob and "9999" not in blob and "<hidden>" in blob and '"123"' in blob


def test_press_non_commit_ok_and_commit_pending_and_confirm():
    rig = make_rig(mode=ConfirmMode.OOB)
    ev = collect(rig.service)
    run(rig.service.connect())
    ev.clear()
    out = run(rig.service.press_key("CLEAR"))
    assert shape(ev) == [("press_key", "start", None), ("press_key", "end", "ok")]
    assert ev[0].key == "Clear" and ev[1].screen_after is not None and out.status == "executed"
    ev.clear()
    p = run(rig.service.press_key("ENTER"))
    assert shape(ev) == [("press_key", "start", None), ("press_key", "end", "pending")]
    assert ev[1].action_id == p.action.action_id and ev[1].screen_after is None
    assert rig.port.pressed == ["Clear"]                      # nothing committed
    ev.clear()
    rig.gate.approve_oob(p.action.action_id, "web-ui:t")
    from seance_mcp.safety import decide

    run(rig.service.confirm_action(p.action.action_id, decide(ConfirmMode.OOB, None, "t", rig.gate.peek(p.action.action_id))))
    assert shape(ev) == [("confirm_action", "start", None), ("confirm_action", "end", "ok")]
    assert ev[0].action_id == p.action.action_id and ev[0].key == "Enter"


def test_every_failure_still_gets_exactly_one_end():
    rig = make_rig()
    ev = collect(rig.service)
    for coro in (rig.service.read_screen(), rig.service.press_key("ENTER")):
        try:
            run(coro)
        except Exception:
            pass
    assert shape(ev) == [("read_screen", "start", None), ("read_screen", "end", "not_connected"),
                         ("press_key", "start", None), ("press_key", "end", "not_connected")]
    ev.clear()
    run(rig.service.connect())
    ev.clear()
    try:
        run(rig.service.fill_field(99, "x"))
    except Exception:
        pass
    assert [e.phase for e in ev] == ["start", "end"] and ev[1].outcome == "field_invalid"
    ev.clear()
    try:
        run(rig.service.confirm_action("nope", __import__("seance_mcp.safety", fromlist=["x"]).Decision(False, "oob", "awaiting_oob")))
    except Exception:
        pass
    assert [(e.tool, e.phase) for e in ev] == [("confirm_action", "start"), ("confirm_action", "end")]


def test_failing_or_removed_observer_never_breaks_an_operation():
    rig = make_rig()

    def boom(_e):
        raise RuntimeError("SECRET-LOOKING-TEXT")

    seen = []
    rig.service.observe(boom)
    off = rig.service.observe(seen.append)
    run(rig.service.connect())
    run(rig.service.read_screen())
    assert len(seen) == 4
    off()
    run(rig.service.read_screen())
    assert len(seen) == 4


def test_audit_subscribers_get_every_entry_in_order_and_are_isolated():
    rig = make_rig()
    got = []
    rig.service.audit.subscribe(lambda e: (_ for _ in ()).throw(ValueError("x")))
    off = rig.service.audit.subscribe(got.append)
    run(rig.service.connect())
    run(rig.service.read_screen())
    on_disk = rig.service.audit.read()
    assert [e.seq for e in got] == [e.seq for e in on_disk] == [1, 2]
    assert got == on_disk and rig.service.audit.verify() is None
    off()
    run(rig.service.read_screen())
    assert len(got) == 2 and len(rig.service.audit.read()) == 3


def test_business_style_sequence_streams_steps_in_order():
    """What a recipe looks like to the planchette: fill, press, read, in order."""
    app = fake_insurance()
    rig = make_rig(port=app)
    ev = collect(rig.service)
    run(rig.service.connect())
    ev.clear()
    run(rig.service.fill_field(app.screens["menu"].names["option"], "1"))
    run(rig.service.press_key("ENTER"))      # menu ENTER is commit-capable by default policy: pending
    kinds = [(e.tool, e.phase) for e in ev]
    assert kinds[:2] == [("fill_field", "start"), ("fill_field", "end")]
    assert ev[0].target.label.startswith("OPTION")


def _is_hidden(rig, e) -> bool:
    f = next(f for f in rig.port.screens["s"].model().fields if f.index == e.target.index)
    return f.hidden


def spec_from_buffer(buf) -> ScreenSpec:
    spec = ScreenSpec({}, [])
    spec.text = list(buf.text)
    spec.starts = buf.field_starts
    spec.cursor = (buf.cursor_row, buf.cursor_col)
    return spec


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
@given(arbitrary_buffer(), st.lists(st.sampled_from(["read", "fields", "fill0", "fill1", "ENTER", "CLEAR", "PF3"]), max_size=8))
def test_hidden_sentinel_never_appears_in_any_event_and_events_are_paired(buf, ops):
    port = FakePort(screens={"s": spec_from_buffer(buf)}, start="s", transitions={})
    rig = make_rig(port=port)
    ev = collect(rig.service)
    entries = []
    rig.service.audit.subscribe(entries.append)
    run(rig.service.connect())
    for op in ops:
        try:
            if op == "read":
                run(rig.service.read_screen())
            elif op == "fields":
                run(rig.service.list_fields())
            elif op.startswith("fill"):
                run(rig.service.fill_field(int(op[-1]), SENTINEL * 3))
            else:
                run(rig.service.press_key(op))
        except Exception:
            pass
    blob = json.dumps([e.model_dump() for e in ev]) + json.dumps([e.model_dump() for e in entries])
    hidden_fills = [e for e in ev if e.tool == "fill_field" and e.phase == "start" and e.target is not None
                    and _is_hidden(rig, e)]
    assert all(e.value == "<hidden>" for e in hidden_fills)
    del blob
    # Hidden DATA in the buffer is stripped by the bridge; the sentinel as hidden data never shows.
    # (A sentinel the test itself types into a visible field may legitimately appear.)
    typed_hidden = [e for e in ev if e.tool == "fill_field" and e.target is not None and e.phase == "start"]
    assert all(e.value != SENTINEL * 3 or not _is_hidden(rig, e) for e in typed_hidden)
    for e in ev:
        for s in (e.screen_before, e.screen_after):
            if s is not None:
                assert all(f.value is None for f in s.fields if f.hidden)
    # start/end pairing: strictly alternating, same tool
    assert len(ev) % 2 == 0
    for a, b in zip(ev[::2], ev[1::2]):
        assert (a.phase, b.phase, a.tool) == ("start", "end", b.tool) and b.outcome is not None
