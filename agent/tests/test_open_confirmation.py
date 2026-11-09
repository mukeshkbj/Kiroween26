"""Product question from request-d-tests-after-b1.md: what happens to an open confirmation
when the model calls another business tool?

Answer (D): **the open confirmation is resolved first.** A pending result suspends the turn;
no other tool runs, from the same model step or a later one, until the person decides or the
confirmation expires. Since B-1, the next business tool would route home with PF3/CLEAR, which
the app treats as cancel. So letting it run would leave the modal showing an action the app had
already dropped. Nothing is ever sent for the pending key either way; this is about the modal
staying truthful.

Two layers, both tested here:
1. the loop runs tool uses one at a time and blocks on the human (ordering);
2. a guard: a tool call that arrives while a confirmation is open is refused with
   ``session_busy`` and never reaches the 3270 session (defence in depth, for any future path
   that could interleave).
"""
from __future__ import annotations

from typing import Any

import anyio
import pytest

from seance_agent.llm.base import ToolUse
from seance_agent.llm.scripted import ScriptedLlm

from ._harness import agent_harness, assert_stream_ok, events, make_loop

pytestmark = pytest.mark.anyio

UPDATE = ToolUse("u1", "update_policy", {"policy_number": "P0000003", "premium": "300"})
LOOKUP = ToolUse("l1", "lookup_policy", {"policy_number": "P0000004"})


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _connected(**kw: Any):
    cm = agent_harness(real_pack=True, **kw)
    h = await cm.__aenter__()
    await h.service.connect()
    h.mapper.take_bus()
    return cm, h


@pytest.mark.parametrize("decision", ["approve", "deny"])
async def test_a_second_tool_waits_until_the_confirmation_is_resolved(decision: str) -> None:
    """The model asks for an update AND a lookup in one step. The lookup (which would route home
    and cancel the review screen) must not run while the modal is open."""
    cm, h = await _connected()
    try:
        loop = make_loop(h, ScriptedLlm([[UPDATE, LOOKUP], ["Done."]]))
        seen: dict[str, Any] = {}

        async with anyio.create_task_group() as tg:
            async def turn() -> None:
                await loop.run_turn("update and look up")
                tg.cancel_scope.cancel()

            async def human() -> None:
                while not events(h, "confirmation_required"):
                    await anyio.sleep(0.01)
                req = events(h, "confirmation_required")[0]["data"]
                pressed = list(h.app.pressed)
                await anyio.sleep(0.3)  # give any rogue concurrent call time to act
                seen["keys_while_open"] = h.app.pressed[len(pressed):]
                seen["calls_while_open"] = [e["data"]["tool"] for e in events(h, "tool_call")]
                seen["still_pending"] = (h.service.gate.pending is not None
                                         and h.service.gate.pending.action_id == req["action_id"])
                seen["app_screen"] = h.app.current
                await loop.confirm_broker.decide(req["action_id"], decision, session_id="s_01")  # type: ignore[attr-defined]

            tg.start_soon(turn)
            tg.start_soon(human)

        assert seen["keys_while_open"] == [], "a key reached the app while the modal was open"
        assert seen["calls_while_open"] == ["update_policy"], "the second tool ran before the decision"
        assert seen["still_pending"] and seen["app_screen"] == "confirm"  # the modal stayed truthful
        assert_stream_ok(h)
        evs = events(h)
        resolved_seq = events(h, "confirmation_resolved")[0]["seq"]
        lookup_seq = next(e["seq"] for e in evs if e["type"] == "tool_call" and e["data"]["tool"] == "lookup_policy")
        assert lookup_seq > resolved_seq
        if decision == "approve":
            assert h.app.policies["P0000003"]["premium"] == "300.00" and len(h.app.mutations) == 1
        else:
            assert not h.app.mutations
        # The lookup ran afterwards. After an approve the app is back on the menu, so it works on any
        # runtime. After a deny the app is still on the review screen: B-1's goto routes home (ok);
        # an older runtime fails closed (unknown_start). Either is fine here; the ordering is the point.
        lookup_res = [e["data"] for e in events(h, "tool_result")][-1]
        if decision == "approve":
            assert lookup_res["status"] == "ok"
        else:
            assert lookup_res["status"] == "ok" or lookup_res["error_code"] == "unknown_start"
    finally:
        await cm.__aexit__(None, None, None)


async def test_a_tool_call_while_a_confirmation_is_open_is_refused() -> None:
    """Defence in depth: if any path ever offered a tool call while a confirmation is open,
    it is refused with session_busy and nothing is sent."""
    cm, h = await _connected()
    try:
        s = h.service
        await s.press_key("CLEAR")
        await s.fill_field(h.app.screens["menu"].names["option"], "3")
        await s.press_key("ENTER")
        await s.fill_field(h.app.screens["update"].names["polno"], "P0000003")
        await s.fill_field(h.app.screens["update"].names["premium"], "300")
        await s.press_key("ENTER")
        assert (await s.press_key("ENTER")).status == "pending"
        h.mapper.take_bus()
        loop = make_loop(h, ScriptedLlm([[LOOKUP], ["ok"]]))
        aid = loop.confirm_broker.register_pending(  # type: ignore[attr-defined]
            tool_call_id="c_open", turn_id=None, read_only=False, agent_summary=None)
        pressed = list(h.app.pressed)

        await loop.run_turn("look something up")

        res = events(h, "tool_result")[0]["data"]
        assert res["status"] == "error" and res["error_code"] == "session_busy"
        assert "waiting for your decision" in res["summary"]
        assert h.app.pressed == pressed and h.app.current == "confirm"
        assert h.service.gate.pending is not None and h.service.gate.pending.action_id == aid
        # The open confirmation is untouched and still decidable.
        res2 = await loop.confirm_broker.decide(aid, "approve", session_id="s_01")  # type: ignore[attr-defined]
        assert res2 is not None and res2.outcome == "approved" and len(h.app.mutations) == 1
    finally:
        await cm.__aexit__(None, None, None)
