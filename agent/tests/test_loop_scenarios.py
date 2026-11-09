"""REQ-025: agent loop scenarios with the scripted model over FakeApp and B's real pack."""
from __future__ import annotations

import json

import pytest

from seance_agent.llm.base import ToolUse
from seance_agent.llm.scripted import ScriptedLlm

from ._harness import agent_harness, assert_stream_ok, events, make_loop, park_off_map, run_with_decision

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def tu(name: str, **args) -> ToolUse:
    return ToolUse(f"tu_{name}", name, args)


async def _connected(**kw):
    cm = agent_harness(real_pack=True, **kw)
    h = await cm.__aenter__()
    await h.service.connect()
    h.mapper.take_bus()
    return cm, h


async def test_lookup_reads_and_streams_inner_steps() -> None:
    cm, h = await _connected()
    try:
        llm = ScriptedLlm([[tu("lookup_policy", policy_number="P0000003")], ["P0000003 is A. ROSE."]])
        loop = make_loop(h, llm)
        assert await loop.run_turn("Look up P0000003") == "completed"
        assert_stream_ok(h)
        types = [e["type"] for e in events(h)]
        assert types[0] == "turn_started" and types[-1] == "turn_finished"
        assert "field_focus" in types and types.count("tool_result") == 1
        res = events(h, "tool_result")[0]["data"]
        assert res["status"] == "ok" and "A. ROSE" in json.dumps(res["result"])
        assert not h.app.dirty
    finally:
        await cm.__aexit__(None, None, None)


async def test_list_policies() -> None:
    cm, h = await _connected()
    try:
        loop = make_loop(h, ScriptedLlm([[tu("list_policies")], ["Here they are."]]))
        assert await loop.run_turn("list") == "completed"
        assert events(h, "tool_result")[0]["data"]["status"] == "ok"
    finally:
        await cm.__aexit__(None, None, None)


UPDATE = [[tu("update_policy", policy_number="P0000003", premium="300")], ["Done."]]


async def test_update_approve_commits_once_and_model_sees_confirmation() -> None:
    cm, h = await _connected()
    try:
        llm = ScriptedLlm([list(x) for x in UPDATE])
        loop = make_loop(h, llm)
        assert await run_with_decision(h, loop, "set premium", "approve") == "completed"
        assert_stream_ok(h)
        assert h.app.dirty and len(h.app.mutations) == 1
        assert [e["data"]["outcome"] for e in events(h, "confirmation_resolved")] == ["approved"]
        res = events(h, "tool_result")[0]["data"]
        assert res["status"] == "ok"
        # The model never saw the pending text or the action id.
        sent = json.dumps([c["messages"] for c in llm.calls])
        assert "confirm_action" not in llm.calls[0]["tools"]
        assert events(h, "confirmation_required")[0]["data"]["action_id"] not in sent
    finally:
        await cm.__aexit__(None, None, None)


async def test_update_deny_is_final_and_sends_nothing() -> None:
    cm, h = await _connected()
    try:
        llm = ScriptedLlm([list(x) for x in UPDATE])
        loop = make_loop(h, llm)
        assert await run_with_decision(h, loop, "set premium", "deny") == "completed"
        assert_stream_ok(h)
        assert not h.app.dirty
        res = events(h, "tool_result")[0]["data"]
        assert res["status"] == "error" and res["error_code"] == "denied_by_user"
        assert "do not retry" in llm.calls[1]["messages"][-1]["content"].lower()
    finally:
        await cm.__aexit__(None, None, None)


async def test_update_expires() -> None:
    cm, h = await _connected(ttl=0.2)
    try:
        loop = make_loop(h, ScriptedLlm([list(x) for x in UPDATE]))
        assert await run_with_decision(h, loop, "set premium", None) == "completed"
        assert_stream_ok(h)
        assert not h.app.dirty
        assert events(h, "tool_result")[0]["data"]["error_code"] == "action_expired"
        assert events(h, "confirmation_resolved")[0]["data"]["outcome"] == "expired"
    finally:
        await cm.__aexit__(None, None, None)


async def test_read_only_is_visible_not_silent() -> None:
    cm, h = await _connected(allow_commit=False)
    try:
        loop = make_loop(h, ScriptedLlm([list(x) for x in UPDATE]))
        await run_with_decision(h, loop, "set premium", "approve")
        assert_stream_ok(h)
        assert not h.app.dirty
        assert events(h, "confirmation_required")[0]["data"]["read_only"] is True
        assert events(h, "confirmation_resolved")[0]["data"]["outcome"] == "blocked_read_only"
        assert events(h, "tool_result")[0]["data"]["error_code"] == "read_only"
    finally:
        await cm.__aexit__(None, None, None)


async def test_schema_invalid_call_is_not_sent() -> None:
    cm, h = await _connected()
    try:
        before = list(h.app.pressed)
        loop = make_loop(h, ScriptedLlm([[tu("lookup_policy", policy_number=5)], ["Sorry."]]))
        await loop.run_turn("x")
        assert events(h, "tool_result")[0]["data"]["error_code"] == "invalid_arguments"
        assert h.app.pressed == before
    finally:
        await cm.__aexit__(None, None, None)


async def test_step_budget() -> None:
    cm, h = await _connected()
    try:
        llm = ScriptedLlm(responder=lambda m, t: [tu("read_screen")])
        loop = make_loop(h, llm, max_steps=3, max_tool_errors=99)
        assert await loop.run_turn("loop forever") == "max_steps"
        assert_stream_ok(h)
        assert events(h, "error")[-1]["data"]["code"] == "max_steps"
    finally:
        await cm.__aexit__(None, None, None)


async def test_cancel_between_steps() -> None:
    cm, h = await _connected()
    try:
        holder = {}

        def responder(m, t):
            holder["loop"].cancel()
            return [tu("read_screen")]

        loop = make_loop(h, ScriptedLlm(responder=responder))
        holder["loop"] = loop
        assert await loop.run_turn("go") == "cancelled"
        assert_stream_ok(h)
    finally:
        await cm.__aexit__(None, None, None)


async def test_llm_unavailable() -> None:
    cm, h = await _connected()
    try:
        loop = make_loop(h, None, llm_available=False)
        assert await loop.run_turn("hi", ref="u_1") == "unavailable"
        err = events(h, "error")[0]["data"]
        assert err["code"] == "llm_unavailable" and err["ref"] == "u_1"
        assert not events(h, "turn_started")
    finally:
        await cm.__aexit__(None, None, None)


async def test_second_turn_while_busy_is_refused() -> None:
    cm, h = await _connected()
    try:
        loop = make_loop(h, ScriptedLlm([["ok"]]))
        loop.turn_id = "t_99"  # simulate a running turn
        assert await loop.run_turn("again") == "busy"
        assert events(h, "error")[0]["data"]["code"] == "turn_in_progress"
    finally:
        await cm.__aexit__(None, None, None)


async def test_keyboard_timeout_is_never_resent() -> None:
    cm, h = await _connected()
    try:
        h.app.timeout_keys = frozenset({"PF3"})
        loop = make_loop(h, ScriptedLlm([[tu("press_key", key="PF3")], ["Unsure what happened."]]))
        assert await loop.run_turn("back") == "completed"
        assert h.app.pressed.count("PF3") == 1
        assert events(h, "tool_result")[0]["data"]["error_code"] == "keyboard_timeout"
        tool_msg = next(m for m in reversed(loop.history) if m["role"] == "tool")
        assert "may or may not" in tool_msg["content"]
    finally:
        await cm.__aexit__(None, None, None)


# ---------------------------------------------------------------- found running C's client live (8.2)

from seance_agent.llm.scripted import DemoLlm, demo_responder  # noqa: E402
from seance_agent.llm.base import ToolDef  # noqa: E402

_ALL = [ToolDef(n, "", {}) for n in ("lookup_policy", "list_policies", "update_policy")]


@pytest.mark.parametrize("text,args", [
    ("Set the premium of policy P0000003 to 300", {"policy_number": "P0000003", "premium": "300"}),
    ("Change policy P0000002 premium to 450.00", {"policy_number": "P0000002", "premium": "450"}),
    ("Set the status of policy P0000004 to L", {"policy_number": "P0000004", "status": "L"}),
    ("Set the status of policy P0000004 to lapsed", {"policy_number": "P0000004", "status": "L"}),
])
def test_demo_reads_the_new_value_not_the_policy_digits(text, args) -> None:
    """The sentences in agent/README.md's run guide."""
    out = demo_responder([{"role": "user", "text": text}], _ALL)
    use = next(i for i in out if isinstance(i, ToolUse))
    assert use.input == args


async def test_lookup_then_update_in_one_session_still_needs_a_human() -> None:
    """Lookup, then update, in one session: the update reaches the modal and commits once on
    approval. (Before B-1 the update failed unknown_start and the demo recovered; with B-1's
    navigating goto it just works. Either way the commit still needs a human.)"""
    cm, h = await _connected()
    try:
        loop = make_loop(h, DemoLlm())
        assert await loop.run_turn("Look up policy P0000003") == "completed"
        await run_with_decision(h, loop, "Set the premium of policy P0000003 to 300", "approve")
        assert_stream_ok(h)
        assert [e["data"]["outcome"] for e in events(h, "confirmation_resolved")] == ["approved"]
        assert h.app.policies["P0000003"]["premium"] == "300.00" and len(h.app.mutations) == 1
    finally:
        await cm.__aexit__(None, None, None)


async def test_off_map_failure_is_recovered_with_a_read_only_key() -> None:
    """The recovery path the old test covered, now provoked without goto: the update fails
    unknown_start off the map, the demo presses CLEAR (not commit-capable) and retries once,
    and the commit still stops at the modal."""
    cm, h = await _connected()
    try:
        park_off_map(h)
        loop = make_loop(h, DemoLlm())
        await run_with_decision(h, loop, "Set the premium of policy P0000003 to 300", "approve")
        assert_stream_ok(h)
        calls = [(e["data"]["tool"], e["data"]["arguments"]) for e in events(h, "tool_call")]
        codes = [e["data"]["error_code"] for e in events(h, "tool_result")]
        assert codes[0] == "unknown_start" and calls[1] == ("press_key", {"key": "CLEAR"})
        assert [e["data"]["outcome"] for e in events(h, "confirmation_resolved")] == ["approved"]
        assert len(h.app.mutations) == 1
    finally:
        await cm.__aexit__(None, None, None)

async def test_business_error_summary_carries_the_real_message() -> None:
    cm, h = await _connected()
    try:
        park_off_map(h)
        out = await h.broker.call("update_policy", {"policy_number": "P0000003", "premium": "300"})
        assert out.status == "error" and out.error_code == "unknown_start"
        # The summary carries the tool's own message, whatever B words it as (B-1 reworded it).
        message = out.structured["error"]["message"]  # type: ignore[index]
        assert message and out.summary == f"update_policy failed: {message[:300]}"
    finally:
        await cm.__aexit__(None, None, None)
