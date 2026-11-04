"""build_service: the in-process wiring the agent uses (docs/contracts.md)."""
import json

import anyio
from mcp import Client

from seance_mcp.config import ConfirmMode, Settings
from seance_mcp.factory import build_service, resolve_path
from seance_mcp.fake import fake_insurance


def test_resolve_path_is_relative_to_root(tmp_path):
    assert resolve_path(None) is None
    assert resolve_path(tmp_path / "a", tmp_path / "x") == tmp_path / "a"
    from pathlib import Path

    assert resolve_path(Path("docs/a.jsonl"), tmp_path) == tmp_path / "docs/a.jsonl"


def test_build_service_shares_one_gate_audit_and_port(tmp_path):
    app = fake_insurance()
    s = Settings(allow_commit=True, confirm_mode=ConfirmMode.OOB, audit_log_path=tmp_path / "a.jsonl")
    server, service = build_service(s, app)
    assert service.port is app and service.gate.allow_commit and service.audit.path == tmp_path / "a.jsonl"

    async def go():
        async with Client(server) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            await c.call_tool("connect", {})
            r = await c.call_tool("read_screen", {})
            return names, r.structured_content

    names, screen = anyio.run(go)
    assert {"connect", "read_screen", "press_key", "confirm_action"} <= names
    assert screen["screen_id"] == app.screens["menu"].model().screen_id


def test_oob_flow_in_process_needs_gate_approval(tmp_path):
    """The agent's path: pending -> approve_oob on the gate handle -> confirm_action."""
    app = fake_insurance()
    s = Settings(allow_commit=True, confirm_mode=ConfirmMode.OOB, audit_log_path=tmp_path / "a.jsonl")
    server, service = build_service(s, app)
    app.state["pending"] = {"polno": "P0000001", "status": "LAPSED", "premium": "180.00"}
    app.current = "confirm"

    async def go():
        async with Client(server) as c:
            await c.call_tool("connect", {})
            p = (await c.call_tool("press_key", {"key": "ENTER"})).structured_content
            aid = p["action"]["action_id"]
            denied = await c.call_tool("confirm_action", {"action_id": aid})
            assert denied.is_error and "awaiting_oob" in json.dumps([x.text for x in denied.content])
            assert not app.dirty
            service.gate.approve_oob(aid, "web-ui:s_test")
            ok = await c.call_tool("confirm_action", {"action_id": aid})
            assert not ok.is_error

    anyio.run(go)
    assert app.dirty and app.policies["P0000001"]["status"] == "LAPSED"
    assert any(e.confirmed_by == "oob:web-ui:s_test" for e in service.audit.read())
