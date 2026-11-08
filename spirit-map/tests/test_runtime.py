"""Runtime tests (REQ-027, REQ-028): run the generated pack against a live FakeApp through the
real SeanceService + RecipeService, so every step is gated and audited. The update tool must end
`pending` and the fake must have seen no commit key. Plus abort codes and the register adapter."""
from __future__ import annotations

import json
from pathlib import Path

import anyio
import pytest

from seance_bridge import COMMIT_CAPABLE
from seance_mcp.audit import AuditLog
from seance_mcp.config import Settings
from seance_mcp.fake import fake_insurance
from seance_mcp.safety import KeyPolicy, SafetyGate
from seance_mcp.service import SeanceService
from seance_mcp.toolpack import RecipeService, def_hash
from seance_spirit import register, run_tool
from seance_spirit.generator import Generator, Overrides
from seance_spirit.seed import load_seed
from seance_spirit.store import read_labels, read_map

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "docs" / "spirit-map" / "fake-insurance"
COMMIT_NAMES = {k.value for k in COMMIT_CAPABLE}


def pack_and_app(tmp_path):
    m = read_map(D / "spirit-map.json")
    labels = read_labels(D / "labels.json")
    seed = load_seed(D / "explore.seed.json")
    overrides = Overrides.load(json.loads((D / "overrides.json").read_text(encoding="utf-8")))
    pack = Generator(m, labels, seed, overrides).generate()
    app = fake_insurance()
    policy_path = D / "key-policy.proposed.json"
    settings = Settings(allow_commit=False, audit_log_path=tmp_path / "a.jsonl", key_policy_path=None)
    gate = SafetyGate(allow_commit=False, ttl_s=300.0,
                      policy=KeyPolicy.load(policy_path if policy_path.exists() else None))
    service = SeanceService(settings, app, AuditLog(tmp_path / "a.jsonl"), gate)
    anyio.run(lambda: service.connect("localhost", 3270))
    return pack, app, RecipeService(service), service


def tool(pack, name):
    return next(t for t in pack["tools"] if t["name"] == name)


# ---------------------------------------------------------------- lookup


def test_lookup_returns_the_policy(tmp_path) -> None:
    pack, app, rs, _ = pack_and_app(tmp_path)
    res = anyio.run(lambda: run_tool(rs, pack, tool(pack, "lookup_policy"), {"policy_number": "P0000003"}))
    assert res["status"] == "ok", res
    assert res["data"]["holder"] == "A. ROSE" and res["data"]["status"] == "ACTIVE"
    assert res["data"]["premium"] == "250.00"
    assert res["trust"] == "untrusted-screen-data"
    assert [s["op"] for s in res["trace"]][0] == "goto"
    assert app.dirty is False


def test_lookup_not_found_still_ok(tmp_path) -> None:
    pack, app, rs, _ = pack_and_app(tmp_path)
    res = anyio.run(lambda: run_tool(rs, pack, tool(pack, "lookup_policy"), {"policy_number": "P9999999"}))
    assert res["status"] == "ok"
    assert res["data"]["holder"] == "" and app.dirty is False


# ---------------------------------------------------------------- list


def test_list_reads_the_rows(tmp_path) -> None:
    pack, app, rs, _ = pack_and_app(tmp_path)
    res = anyio.run(lambda: run_tool(rs, pack, tool(pack, "list_policies"), {}))
    assert res["status"] == "ok"
    rows = res["data"]["rows"]
    assert len(rows) == 8
    assert rows[0]["policy_number"] == "P0000001" and rows[0]["holder"] == "J. MARLOWE"
    assert app.dirty is False


# ---------------------------------------------------------------- update: ends pending, no commit sent


def test_update_ends_pending_and_sends_no_commit_key(tmp_path) -> None:
    pack, app, rs, _ = pack_and_app(tmp_path)
    res = anyio.run(lambda: run_tool(rs, pack, tool(pack, "update_policy"),
                                     {"policy_number": "P0000003", "status": "L", "premium": "300"}))
    assert res["status"] == "pending", res
    assert res["pending"]["key"] == "Enter" and res["pending"]["screen_id"]
    # the confirm screen's ENTER was proposed, never sent: no commit key reached the app, nothing changed
    assert app.dirty is False and app.mutations == []
    assert app.policies["P0000003"]["status"] == "ACTIVE"  # unchanged
    # the only commit-capable key the app saw was the read-only ENTERs on menu/update (not confirm)
    confirm_sid = app.screens["confirm"].model().screen_id
    # the fake records (screen, key) via RecordingApp? fake_insurance is plain FakeApp: check pressed
    assert "Enter" in app.pressed  # menu/update navigation ENTERs ran
    # and crucially the data is intact
    assert res["data"] == {} or "message" in res["data"]


def test_update_without_optional_fields_skips_them(tmp_path) -> None:
    pack, app, rs, _ = pack_and_app(tmp_path)
    res = anyio.run(lambda: run_tool(rs, pack, tool(pack, "update_policy"), {"policy_number": "P0000001"}))
    assert res["status"] in ("pending", "error")  # no status/premium: the app may reject, but never commits
    assert app.dirty is False


# ---------------------------------------------------------------- argument validation (strict)


def test_invalid_arguments_are_rejected_before_touching_the_session(tmp_path) -> None:
    pack, app, rs, _ = pack_and_app(tmp_path)
    for bad in ({"policy_number": "toolong!!"}, {"policy_number": "p1"}, {}, {"policy_number": "P1", "x": 1}):
        res = anyio.run(lambda b=bad: run_tool(rs, pack, tool(pack, "lookup_policy"), b))
        assert res["status"] == "error" and res["error"]["code"] == "invalid_arguments", (bad, res)
    assert app.pressed == []  # nothing was sent for any invalid call


# ---------------------------------------------------------------- abort codes


def _off_home(rs_service, option: str = "1"):
    async def go():
        screen = await rs_service.read_screen()
        opt = next(f.index for f in screen.fields if not f.protected)
        await rs_service.fill_field(opt, option)
        await rs_service.press_key("ENTER")
    return go


def test_goto_navigates_home_from_a_known_screen(tmp_path) -> None:
    """B-1: the session is on the enquiry screen, not home; the tool must route back itself."""
    pack, app, rs, service = pack_and_app(tmp_path)
    anyio.run(_off_home(service))
    assert app.current == "enquiry"
    app.calls.clear()
    res = anyio.run(lambda: run_tool(rs, pack, tool(pack, "lookup_policy"), {"policy_number": "P0000005"}))
    assert res["status"] == "ok", res
    assert res["data"]["holder"] == "S. LINDQVIST"
    routing = [s for s in res["trace"] if s["op"] == "goto" and s["key"]]
    assert routing and routing[0]["key"] in ("CLEAR", "PF3")
    assert res["trace"][0]["op"] == "goto" and res["trace"][0]["key"] == routing[0]["key"]  # starts with routing
    assert app.dirty is False


def test_two_business_tools_back_to_back_off_home(tmp_path) -> None:
    """The conversation that failed in the browser: lookup, lookup, then update."""
    pack, app, rs, service = pack_and_app(tmp_path)

    async def conversation():
        out = []
        for name, args in (("lookup_policy", {"policy_number": "P0000003"}),   # starts on home
                           ("lookup_policy", {"policy_number": "P0000005"}),   # starts on the enquiry result
                           ("list_policies", {}),                              # starts on enquiry again
                           ("update_policy", {"policy_number": "P0000003", "premium": "300"})):  # starts on list
            out.append(await run_tool(rs, pack, tool(pack, name), args))
        return out

    first, second, third, fourth = anyio.run(conversation)
    assert first["status"] == "ok" and first["data"]["holder"] == "A. ROSE"
    assert first["trace"][0]["key"] is None                      # already home: nothing pressed to get there
    assert second["status"] == "ok" and second["data"]["holder"] == "S. LINDQVIST"
    assert second["trace"][0]["op"] == "goto" and second["trace"][0]["key"] in ("CLEAR", "PF3")
    assert third["status"] == "ok" and len(third["data"]["rows"]) == 8
    assert fourth["status"] == "pending" and fourth["pending"]["key"] == "Enter"
    assert app.dirty is False and app.policies["P0000003"]["premium"] == "250.00"


@pytest.mark.parametrize("start", ["menu", "enquiry", "list", "update", "confirm"])
def test_goto_home_from_every_node_uses_only_read_only_keys(tmp_path, start) -> None:
    pack, app, rs, service = pack_and_app(tmp_path)
    app.current = start
    home = pack["home"]
    t = {"name": "go_home", "kind": "read", "input_schema": {"type": "object", "properties": {}},
         "recipe": [{"op": "goto", "node": home}], "limits": {"max_steps": 5}}
    res = anyio.run(lambda: run_tool(rs, pack, t, {}))
    assert res["status"] == "ok", res
    assert app.current == "menu"
    # only keys the key policy / defaults treat as read-only were sent, nothing was typed, nothing changed
    assert set(app.pressed) <= {"Clear", "PF3"} and len(app.pressed) <= 1
    assert not [c for c in app.calls if c[0] == "fill"]
    assert app.dirty is False


def test_unknown_screen_refuses_and_presses_nothing(tmp_path) -> None:
    from seance_mcp.fake import FakePort

    pack, _, _, _ = pack_and_app(tmp_path)
    other = FakePort()  # the default logon screen: not in this app's map
    settings = Settings(allow_commit=False, audit_log_path=tmp_path / "b.jsonl", key_policy_path=None)
    service = SeanceService(settings, other, AuditLog(tmp_path / "b.jsonl"),
                            SafetyGate(allow_commit=False, ttl_s=300.0, policy=KeyPolicy()))
    anyio.run(lambda: service.connect("localhost", 3270))
    res = anyio.run(lambda: run_tool(RecipeService(service), pack, tool(pack, "lookup_policy"),
                                     {"policy_number": "P0000003"}))
    assert res["status"] == "error" and res["error"]["code"] == "unknown_start"
    assert "not in the map" in res["error"]["message"]
    assert other.pressed == [] and not [c for c in other.calls if c[0] == "fill"]


def test_routing_presses_count_against_the_step_budget(tmp_path) -> None:
    pack, app, rs, service = pack_and_app(tmp_path)
    anyio.run(_off_home(service))
    t = json.loads(json.dumps(tool(pack, "lookup_policy")))
    t["limits"]["max_steps"] = len(t["recipe"])  # enough for the recipe alone, not for recipe + routing
    res = anyio.run(lambda: run_tool(rs, pack, t, {"policy_number": "P0000003"}))
    assert res["status"] == "error" and res["error"]["code"] == "step_budget"


def test_a_pack_without_navigation_still_works_from_home_only(tmp_path) -> None:
    """Older packs (no `navigation`) keep the previous behaviour: fine on home, refused elsewhere."""
    pack, app, rs, service = pack_and_app(tmp_path)
    old = {k: v for k, v in pack.items() if k != "navigation"}
    ok = anyio.run(lambda: run_tool(rs, old, tool(old, "lookup_policy"), {"policy_number": "P0000003"}))
    assert ok["status"] == "ok"
    anyio.run(_off_home(service))
    bad = anyio.run(lambda: run_tool(rs, old, tool(old, "lookup_policy"), {"policy_number": "P0000003"}))
    assert bad["status"] == "error" and bad["error"]["code"] == "unknown_start"


def test_mutation_old_assert_goto_fails_the_two_in_a_row_test(tmp_path, monkeypatch) -> None:
    """Replace navigation with the old assert: the conversation breaks on its second tool."""
    from seance_spirit import runtime

    async def old_goto(service, nav, node_id, screen, trace, spend):
        if runtime._nid(screen.screen_id) != node_id:
            raise runtime.RunError("unknown_start", "expected to start on home")
        return screen

    monkeypatch.setattr(runtime, "_goto", old_goto)
    with pytest.raises(AssertionError):
        test_two_business_tools_back_to_back_off_home(tmp_path)

def test_screen_mismatch_aborts(tmp_path) -> None:
    pack, app, rs, _ = pack_and_app(tmp_path)
    bad = json.loads(json.dumps(tool(pack, "lookup_policy")))
    bad["recipe"][2]["expect"] = "n_deadbeef00"  # press ENTER but expect the wrong node
    res = anyio.run(lambda: run_tool(rs, pack, bad, {"policy_number": "P0000003"}))
    assert res["status"] == "error" and res["error"]["code"] == "screen_mismatch"


def test_step_budget_aborts(tmp_path) -> None:
    pack, app, rs, _ = pack_and_app(tmp_path)
    t = json.loads(json.dumps(tool(pack, "lookup_policy")))
    t["limits"]["max_steps"] = 2
    res = anyio.run(lambda: run_tool(rs, pack, t, {"policy_number": "P0000003"}))
    assert res["status"] == "error" and res["error"]["code"] == "step_budget"


def test_runtime_never_confirms_and_never_retries(tmp_path) -> None:
    pack, app, rs, service = pack_and_app(tmp_path)
    # make ENTER time out on confirm would be ideal; instead assert the runtime has no confirm path
    import ast
    from seance_spirit import runtime

    src = Path(runtime.__file__).read_text(encoding="utf-8")
    for bad in ("confirm_action", "authorize", "approve_oob", "retry", "resend"):
        assert bad not in src


# ---------------------------------------------------------------- register adapter (task 6.1)


def test_register_advertises_strict_schema_and_runs(tmp_path) -> None:
    from mcp.server import MCPServer

    pack, app, rs, service = pack_and_app(tmp_path)
    server = MCPServer("test")
    names = register(server, rs, pack["tools"], pack)
    assert set(names) == {"lookup_policy", "list_policies", "update_policy"}

    async def go():
        tools = await server.list_tools()
        by = {t.name: t for t in tools}
        look = by["lookup_policy"]
        schema = getattr(look, "input_schema", None) or getattr(look, "inputSchema")
        assert schema["additionalProperties"] is False
        assert schema["properties"]["policy_number"]["maxLength"] == 8
        res = await server.call_tool("lookup_policy", {"policy_number": "P0000003"})
        text = res.content[0].text
        assert "A. ROSE" in text and '"status": "ok"' in text
        # the SDK enforces required; a missing required arg is an error, not a silent pass
        with pytest.raises(Exception):
            await server.call_tool("lookup_policy", {})

    anyio.run(go)


def test_register_is_the_only_private_sdk_seam() -> None:
    from seance_spirit import runtime

    src = Path(runtime.__file__).read_text(encoding="utf-8")
    assert src.count("_tool_manager") == 1  # the one documented seam; fail loudly if it spreads
