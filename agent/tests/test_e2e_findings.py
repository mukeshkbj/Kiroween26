"""Regression tests for docs/handoff/integrator/request-d-e2e-findings.md (D-1 to D-5).

Each finding came from the integrator's full-stack browser run on 2026-11-06.
"""
from __future__ import annotations

import json
import re
from typing import Any

import pytest
from mcp import types

from seance_agent.llm.base import ToolDef, ToolUse
from seance_agent.llm.scripted import DemoLlm, ScriptedLlm, demo_responder
from seance_agent.tools import ToolBroker

from ._harness import REPO_ROOT, agent_harness, events, make_loop, run_with_decision
from ._stream import check_stream, check_summaries, check_user_facing_text

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _connected(**kw: Any):
    cm = agent_harness(real_pack=True, **kw)
    h = await cm.__aenter__()
    await h.service.connect()
    h.mapper.take_bus()
    return cm, h


# ---------------------------------------------------------------- D-1 demo phrasing

_TOOLS = [ToolDef(n, "", {}) for n in ("lookup_policy", "list_policies", "update_policy")]


@pytest.mark.parametrize("text,args", [
    # the three phrasings in the finding
    ("Set the premium of policy P0000003 to 300", {"policy_number": "P0000003", "premium": "300"}),
    ("Set the status of policy P0000002 to L", {"policy_number": "P0000002", "status": "L"}),
    ("Set premium to 300 for P0000003", {"policy_number": "P0000003", "premium": "300"}),
    # neighbours
    ("Change the premium for P0000005 = 125", {"policy_number": "P0000005", "premium": "125"}),
    ("Update policy P0000006: premium to 99.50", {"policy_number": "P0000006", "premium": "99"}),
    ("Set status of P0000007 to C", {"policy_number": "P0000007", "status": "C"}),
    ("Mark policy P0000008 as cancelled", {"policy_number": "P0000008", "status": "C"}),
])
def test_d1_demo_model_proposes_the_value_the_person_asked_for(text: str, args: dict[str, str]) -> None:
    out = demo_responder([{"role": "user", "text": text}], _TOOLS)
    use = next(i for i in out if isinstance(i, ToolUse))
    assert use.name == "update_policy" and use.input == args
    # The policy number's digits never become the premium.
    assert use.input.get("premium") != args["policy_number"][1:]


# ---------------------------------------------------------------- D-2 "ok" for a failure


def _text_result(envelope: dict[str, Any]) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(envelope))])


@pytest.mark.parametrize("envelope", [
    {"status": "error", "error": {"code": "unknown_start", "message": "expected to start on n_ba02cc6364"}},
    {"status": "error", "error": {"code": "screen_mismatch"}},
    {"status": "error", "error": None},
    {"status": "error"},
    {"status": "weird"},          # not ok, not pending, not error: must fail closed
    {"status": None},
])
def test_d2_error_envelopes_are_never_summarised_as_ok(envelope: dict[str, Any]) -> None:
    out = ToolBroker(None)._classify("lookup_policy", "business", _text_result(envelope))  # type: ignore[arg-type]
    assert out.status == "error"
    assert out.error_code
    assert not re.search(r"\bok\b", out.summary.lower()), out.summary


async def test_d2_a_failing_business_tool_reaches_the_ui_as_failed() -> None:
    cm, h = await _connected()
    try:
        # The real pack refuses to start update_policy off the main menu (unknown_start).
        await h.broker.call("lookup_policy", {"policy_number": "P0000003"})
        h.mapper.take_bus()
        loop = make_loop(h, ScriptedLlm([[ToolUse("u1", "update_policy", {"policy_number": "P0000003", "premium": "300"})],
                                         ["Sorry."]]))
        await loop.run_turn("x")
        res = events(h, "tool_result")[0]["data"]
        assert res["status"] == "error" and res["error_code"] == "unknown_start"
        assert "failed" in res["summary"] and not res["summary"].endswith(" ok")
        check_summaries(events(h))
    finally:
        await cm.__aexit__(None, None, None)


# ---------------------------------------------------------------- D-3 event order (contracts 4.3)


async def test_d3_a_call_starting_with_a_read_gets_before_first_and_a_real_focus_screen() -> None:
    cm, h = await _connected()
    try:
        loop = make_loop(h, ScriptedLlm([[ToolUse("r1", "read_screen", {})], ["Read it."]]))
        await loop.run_turn("what is on screen")
        evs = events(h)
        check_stream(evs)  # includes the 4.3 screen/focus rules
        cid = events(h, "tool_call")[0]["data"]["tool_call_id"]
        mine = [e for e in evs if e["type"] in ("screen", "field_focus") and e["data"].get("tool_call_id") == cid]
        assert [e["type"] for e in mine][:2] == ["screen", "field_focus"]
        before, focus = mine[0]["data"], mine[1]["data"]
        assert before["phase"] == "before" and focus["mode"] == "read"
        assert focus["screen_id"] == before["screen"]["screen_id"] != ""
    finally:
        await cm.__aexit__(None, None, None)


async def test_d3_business_lookup_obeys_the_order_rules() -> None:
    cm, h = await _connected()
    try:
        loop = make_loop(h, DemoLlm())
        await loop.run_turn("Look up policy P0000003")
        await run_with_decision(h, loop, "Set the premium of policy P0000003 to 300", "approve")
        check_stream(events(h))
        for f in events(h, "field_focus"):
            assert f["data"]["screen_id"], f
    finally:
        await cm.__aexit__(None, None, None)


def test_d3_the_checker_rejects_the_deviations_it_was_written_for() -> None:
    """The stricter rules must actually bite (both deviations from the finding)."""
    from ._stream import ContractError

    base = [
        {"seq": 1, "type": "turn_started", "turn_id": "t", "data": {"user_message_id": "m"}},
        {"seq": 2, "type": "tool_call", "turn_id": "t", "data": {"tool_call_id": "c"}},
    ]
    after_first = base + [{"seq": 3, "type": "screen", "turn_id": "t",
                           "data": {"phase": "after", "tool_call_id": "c", "screen": {}}}]
    empty_focus = base + [{"seq": 3, "type": "field_focus", "turn_id": "t",
                           "data": {"tool_call_id": "c", "screen_id": ""}}]
    for bad in (after_first, empty_focus):
        with pytest.raises(ContractError):
            check_stream(bad)


# ---------------------------------------------------------------- D-4 apps.json vs contracts section 8


def _contract_apps() -> dict[str, Any]:
    text = (REPO_ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    section = text[text.index("## 8."):text.index("## 9.")]
    block = re.search(r"```json\s*(\{.*?\})\s*```", section, re.DOTALL)
    assert block, "contracts section 8 has no json block"
    return json.loads(block.group(1))


def test_d4_apps_json_matches_contracts_section_8() -> None:
    ours = json.loads((REPO_ROOT / "agent" / "apps.json").read_text(encoding="utf-8"))
    assert ours == _contract_apps()
    assert "KICKS" not in json.dumps(ours)


def test_d4_live_apps_use_their_own_port_variable(tmp_path) -> None:
    from seance_agent.apps import AppRegistry, build_runtime
    from seance_agent.config import Settings

    reg = AppRegistry.load()
    env = {"GSS_LIVE_OK": "1", "TN3270_HOST": "127.0.0.1", "TN3270_PORT": "3270", "STANDIN_PORT": "3271"}
    for app_id, port in (("tk4-builtins", 3270), ("seance-insurance", 3271)):
        rt = build_runtime(reg.get(app_id), reg, Settings(), env=env, audit_path=tmp_path / "a.jsonl")  # no connect
        assert rt.service.settings.port == port, app_id
    # With STANDIN_PORT unset, the stand-in falls back to its documented default, never to TK4-'s port.
    env.pop("STANDIN_PORT")
    rt = build_runtime(reg.get("seance-insurance"), reg, Settings(), env=env, audit_path=tmp_path / "b.jsonl")
    assert rt.service.settings.port == 3271


# ---------------------------------------------------------------- D-5 model-only text never shown to the person

UPDATE = [[ToolUse("u1", "update_policy", {"policy_number": "P0000003", "premium": "300"})], ["Understood."]]


@pytest.mark.parametrize("decision,kw", [("deny", {}), (None, {"ttl": 0.2}), ("approve", {"allow_commit": False})])
async def test_d5_after_a_decision_the_person_sees_a_human_sentence(decision: str | None, kw: dict[str, Any]) -> None:
    cm, h = await _connected(**kw)
    try:
        llm = ScriptedLlm([list(x) for x in UPDATE])
        loop = make_loop(h, llm)
        await run_with_decision(h, loop, "set premium", decision)
        check_user_facing_text(events(h))
        res = events(h, "tool_result")[0]["data"]
        assert res["summary"].endswith(".") and "nothing was changed" in res["summary"].lower()
        # ...while the model still gets the full instruction.
        tool_msg = llm.calls[1]["messages"][-1]["content"].lower()
        assert "do not retry" in tool_msg or "this is final" in tool_msg
    finally:
        await cm.__aexit__(None, None, None)


async def test_d5_the_demo_model_does_not_echo_model_instructions() -> None:
    cm, h = await _connected()
    try:
        loop = make_loop(h, DemoLlm())
        await run_with_decision(h, loop, "Set the premium of policy P0000003 to 300", "deny")
        check_user_facing_text(events(h))
        said = " ".join(e["data"]["text"] for e in events(h, "assistant_message"))
        assert "declined" in said.lower() and "nothing was changed" in said.lower()
    finally:
        await cm.__aexit__(None, None, None)
