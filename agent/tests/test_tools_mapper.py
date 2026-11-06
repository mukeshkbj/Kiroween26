"""Section 3 tests: the allowlist, schema validation and no-leak rules.

These exercise the real ToolBroker over the real service and FakeApp:

* REQ-006: ``confirm_action``, ``connect``, ``get_audit_log`` are never in the
  catalogue the model sees, and are refused if the model names them.
* REQ-007: an argument that does not match the tool schema is turned into an
  error outcome and never sent to the bridge (the fake records no key for it).
* REQ-028 (direct; the property version lives in section 5): a value typed into a
  hidden field never appears in any emitted event, and hidden screen fields are
  always nulled.
"""
from __future__ import annotations

import json

import anyio
import pytest

from seance_bridge import Buffer, FieldAttrs, FieldStart, Key, ScreenParser
from seance_mcp.config import ConfirmMode, Settings
from seance_mcp.factory import build_service
from seance_mcp.fake import FakeApp, Rule, ScreenSpec, rc

from seance_agent.mapper import CallScope, EventMapper
from seance_agent.session import Session
from seance_agent.tools import GENERIC_TOOLS, WITHHELD_TOOLS, ToolBroker

from ._harness import agent_harness

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_withheld_tools_never_offered() -> None:
    async with agent_harness() as h:
        names = {s.name for s in h.broker.specs()}
        assert not (names & WITHHELD_TOOLS), f"withheld tools leaked into the catalogue: {names & WITHHELD_TOOLS}"
        assert GENERIC_TOOLS <= names  # the four generic tools are offered by default


async def test_generic_tools_can_be_turned_off() -> None:
    async with agent_harness(generic_tools=False) as h:
        names = {s.name for s in h.broker.specs()}
        assert not (names & GENERIC_TOOLS)


async def test_model_naming_a_withheld_tool_is_refused_not_sent() -> None:
    async with agent_harness() as h:
        await h.service.connect()
        before = list(h.app.pressed)
        out = await h.broker.call("confirm_action", {"action_id": "whatever"})
        assert out.status == "error" and out.error_code == "invalid_arguments"
        assert h.app.pressed == before  # nothing reached the bridge


async def test_invalid_arguments_are_not_sent() -> None:
    async with agent_harness() as h:
        await h.service.connect()
        before = list(h.app.pressed)
        # press_key expects a string key; an integer fails the schema.
        out = await h.broker.call("press_key", {"key": 123})
        assert out.status == "error" and out.error_code == "invalid_arguments"
        # read_screen takes no arguments; an extra one fails (additionalProperties).
        out2 = await h.broker.call("read_screen", {"bogus": 1})
        assert out2.status == "error" and out2.error_code == "invalid_arguments"
        assert h.app.pressed == before


async def test_press_key_pending_is_classified_pending() -> None:
    async with agent_harness() as h:
        s = h.service
        await s.connect()
        # Stage an update to reach the confirm screen, where ENTER is commit-capable.
        await s.press_key("CLEAR")
        await s.fill_field(h.app.screens["menu"].names["option"], "3")
        await s.press_key("ENTER")
        await s.fill_field(h.app.screens["update"].names["polno"], "P0000003")
        await s.fill_field(h.app.screens["update"].names["premium"], "300")
        await s.press_key("ENTER")  # update -> confirm (read-only under golden policy)
        out = await h.broker.call("press_key", {"key": "ENTER"})  # commit on confirm
        assert out.status == "pending"
        assert h.service.gate.pending is not None


# ---------------------------------------------------------------- no leak (REQ-028)

CANARY = "S3CRET-CANARY-9Z"


def _hidden_field_app() -> FakeApp:
    """A one-screen app with a single hidden, unprotected input field."""
    texts = {rc(0, 1): "HIDDEN FIELD TEST", rc(3, 1): "PW ===>"}
    starts = [(rc(0, 0), FieldAttrs(protected=True)),
              (rc(3, 8), FieldAttrs(protected=False, hidden=True)),
              (rc(3, 30), FieldAttrs(protected=True))]
    spec = ScreenSpec(texts, starts, cursor=(3, 9), names={"pw": (3, 8)}, kinds={"pw": "hidden"})
    return FakeApp({"home": spec}, "home", [Rule("*", "CLEAR", "home")])


async def test_hidden_field_value_never_appears_in_events() -> None:
    app = _hidden_field_app()
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    settings = Settings(allow_commit=True, confirm_mode=ConfirmMode.OOB, audit_log_path=tmp / "a.jsonl")
    server, service = build_service(settings, app, audit_path=tmp / "a.jsonl")
    session = Session("s_01", ring_size=10_000)
    box: dict[str, str | None] = {"turn": "t_01"}
    mapper = EventMapper(session, turn_id_getter=lambda: box["turn"])
    mapper.attach(service)

    async with ToolBroker.start(server) as broker:
        await service.connect()
        scope = CallScope(tool_call_id="c_01")
        # Type the canary into the hidden field through the broker, then map.
        pw_index = next(f.index for f in (await service.list_fields()) if f.hidden)
        out = await broker.call("fill_field", {"field_ref": pw_index, "value": CANARY})
        mapper.flush(scope)
        assert out.status == "ok"

    mapper.detach()
    blob = json.dumps(list(session._ring), ensure_ascii=False)
    assert CANARY not in blob, "hidden field value leaked into an emitted event"
    # And every hidden screen field in those events is nulled.
    for ev in session._ring:
        if ev["type"] == "screen":
            for f in ev["data"]["screen"]["fields"]:
                if f["hidden"]:
                    assert f["value"] is None
