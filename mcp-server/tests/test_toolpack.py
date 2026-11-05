"""Tool-pack hook (P0.5): only hash-verified, human-approved tools get registered."""
from __future__ import annotations

import copy
import json

import anyio
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from mcp import Client

from seance_mcp.config import ConfirmMode, Settings
from seance_mcp.factory import build_service
from seance_mcp.fake import fake_insurance
from seance_mcp.toolpack import (
    GENERIC_TOOLS,
    RecipeService,
    ToolPackError,
    def_hash,
    load_toolpack,
)


def tool(name="lookup_policy", kind="read", **extra):
    t = {
        "name": name, "kind": kind, "title": "T", "description": "d",
        "input_schema": {"type": "object", "additionalProperties": False, "properties": {}},
        "output_schema": {"type": "object"}, "recipe": [{"op": "goto", "node": "n_menu"}],
        "limits": {"max_steps": 25}, "provenance": {"needs_review": False},
    }
    t.update(extra)
    t["def_hash"] = def_hash(t)
    return t


def write_pack(tmp_path, tools, approve=(), schema="gss.toolpack/1"):
    pack = {"schema": schema, "app_id": "fake-insurance", "tools": tools}
    (tmp_path / "tools.json").write_text(json.dumps(pack), encoding="utf-8")
    appr = {"approved": [{"name": t["name"], "def_hash": t["def_hash"], "approved_by": "me",
                          "approved_at": "2026-11-04T00:00:00Z"} for t in approve]}
    (tmp_path / "tool-approvals.json").write_text(json.dumps(appr), encoding="utf-8")
    return tmp_path / "tools.json", tmp_path / "tool-approvals.json"


def test_hash_ignores_provenance_and_def_hash_but_not_content():
    t = tool()
    t2 = copy.deepcopy(t)
    t2["provenance"] = {"anything": 1}
    assert def_hash(t) == def_hash(t2) == t["def_hash"]
    t3 = copy.deepcopy(t)
    t3["description"] = "changed"
    assert def_hash(t3) != t["def_hash"]


def test_only_approved_matching_hash_loads(tmp_path):
    a, b = tool("lookup_policy"), tool("list_policies")
    pack, appr = write_pack(tmp_path, [a, b], approve=[a])
    r = load_toolpack(pack, appr)
    assert [t["name"] for t in r.approved] == ["lookup_policy"]
    assert r.skipped == [("list_policies", "not_approved")]


def test_editing_an_approved_tool_unapproves_it(tmp_path):
    a = tool("lookup_policy")
    pack, appr = write_pack(tmp_path, [a], approve=[a])
    assert len(load_toolpack(pack, appr).approved) == 1
    edited = copy.deepcopy(a)
    edited["recipe"] = [{"op": "goto", "node": "n_other"}]
    edited["def_hash"] = def_hash(edited)         # a careful editor recomputes the hash...
    write_pack(tmp_path, [edited])                # ...but the approval file still has the old one
    (tmp_path / "tool-approvals.json").write_text(json.dumps({"approved": [{"name": "lookup_policy", "def_hash": a["def_hash"]}]}))
    r = load_toolpack(pack, appr)
    assert r.approved == [] and r.skipped == [("lookup_policy", "not_approved")]
    stale = copy.deepcopy(a)
    stale["recipe"] = [{"op": "goto", "node": "n_other"}]   # ...a careless one keeps the old hash
    write_pack(tmp_path, [stale], approve=[a])
    assert load_toolpack(pack, appr).skipped == [("lookup_policy", "hash_mismatch")]


@pytest.mark.parametrize("bad,reason", [
    (tool(name="Bad-Name"), "bad_name"),
    (tool(name="ab"), "bad_name"),
    (tool(name="read_screen"), "name_collision"),
    (tool(name="confirm_action"), "name_collision"),
    (tool(kind="exec"), "bad_kind"),
])
def test_illegal_tools_are_skipped_even_when_unreviewed_allowed(tmp_path, bad, reason):
    pack, appr = write_pack(tmp_path, [bad], approve=[bad])
    r = load_toolpack(pack, appr, allow_unreviewed=True)
    assert r.approved == [] and r.skipped[0][1] == reason


def test_duplicate_names_second_is_skipped(tmp_path):
    a = tool()
    b = tool(description="other")
    pack, appr = write_pack(tmp_path, [a, b], approve=[a])
    r = load_toolpack(pack, appr)
    assert [t["description"] for t in r.approved] == ["d"] and r.skipped == [("lookup_policy", "duplicate")]


def test_unusable_packs_raise(tmp_path):
    with pytest.raises(ToolPackError):
        load_toolpack(tmp_path / "missing.json", None)
    pack, appr = write_pack(tmp_path, [], schema="other/1")
    with pytest.raises(ToolPackError):
        load_toolpack(pack, appr)
    pack.write_text("{not json", encoding="utf-8")
    with pytest.raises(ToolPackError):
        load_toolpack(pack, appr)
    pack, _ = write_pack(tmp_path, [])
    (tmp_path / "tool-approvals.json").write_text('{"approved": 5}')
    with pytest.raises(ToolPackError):
        load_toolpack(pack, tmp_path / "tool-approvals.json")


def rig(tmp_path, pack, approvals, *, unreviewed=False, registrar=None):
    s = Settings(allow_commit=True, confirm_mode=ConfirmMode.OOB, audit_log_path=tmp_path / "audit.jsonl",
                 generated_tools_path=pack, tool_approvals_path=approvals, allow_unreviewed_tools=unreviewed)
    return build_service(s, fake_insurance(), registrar=registrar)


def test_server_passes_only_approved_tools_and_a_narrow_service(tmp_path):
    a, b = tool("lookup_policy"), tool("update_policy", "commit")
    pack, appr = write_pack(tmp_path, [a, b], approve=[a])
    seen = {}

    def registrar(mcp, svc, tools, pack_):
        seen.update(svc=svc, tools=[t["name"] for t in tools], app=pack_["app_id"])
        return [t["name"] for t in tools]

    server, service = rig(tmp_path, pack, appr, registrar=registrar)
    assert seen["tools"] == ["lookup_policy"] and seen["app"] == "fake-insurance"
    svc = seen["svc"]
    assert isinstance(svc, RecipeService)
    # A generated tool cannot confirm, deny, reach the gate or the audit log.
    for attr in ("confirm_action", "deny_action", "gate", "audit", "_lock", "port", "settings"):
        assert not hasattr(svc, attr)
    e = [x for x in service.audit.read() if x.tool == "toolpack"]
    assert len(e) == 1 and e[0].outcome == "loaded" and "registered=1" in e[0].detail and "update_policy:not_approved" in e[0].detail


def test_recipe_service_forwards_through_the_real_service(tmp_path):
    a = tool()
    pack, appr = write_pack(tmp_path, [a], approve=[a])
    captured = {}
    server, service = rig(tmp_path, pack, appr, registrar=lambda m, s, t, p: captured.setdefault("s", s) and [])

    async def go():
        await service.connect()
        svc = captured["s"]
        await svc.read_screen()
        # ENTER on 'confirm' style commit-capable key still goes through the gate: pending, not sent.
        out = await svc.press_key("ENTER")
        return out.status

    assert anyio.run(go) == "pending"
    assert service.port.pressed == []


def test_unreviewed_flag_registers_unapproved_and_is_audited(tmp_path):
    a = tool()
    pack, appr = write_pack(tmp_path, [a], approve=[])
    got = []
    server, service = rig(tmp_path, pack, appr, unreviewed=True, registrar=lambda m, s, t, p: got.extend(t) or [x["name"] for x in t])
    assert [t["name"] for t in got] == ["lookup_policy"]
    outcomes = [e.outcome for e in service.audit.read() if e.tool == "toolpack"]
    assert outcomes == ["unreviewed_allowed", "loaded"]


def test_nothing_configured_means_no_hook_and_no_audit(tmp_path):
    s = Settings(audit_log_path=tmp_path / "a.jsonl")
    server, service = build_service(s, fake_insurance())
    assert [e for e in service.audit.read() if e.tool == "toolpack"] == []


def test_configured_pack_without_spirit_package_fails_loudly(tmp_path):
    import importlib.util

    if importlib.util.find_spec("seance_spirit") is not None:
        pytest.skip("seance_spirit is installed in this env; the no-package path is covered where it is absent")
    a = tool()
    pack, appr = write_pack(tmp_path, [a], approve=[a])
    with pytest.raises(ToolPackError, match="seance_spirit"):
        rig(tmp_path, pack, appr)


def test_configured_pack_with_spirit_package_registers_through_the_real_register(tmp_path):
    """When seance_spirit IS installed (as in the agent/integration envs), the default
    registrar loads it and registers the approved tools."""
    import importlib.util

    if importlib.util.find_spec("seance_spirit") is None:
        pytest.skip("seance_spirit not installed in this env")
    from pathlib import Path

    from seance_mcp.paths import REPO_ROOT

    pack = REPO_ROOT / "docs/spirit-map/fake-insurance/tools.json"
    pol = REPO_ROOT / "docs/spirit-map/fake-insurance/key-policy.json"
    if not pack.exists():
        pytest.skip("fake-insurance pack not present in this checkout")
    s = Settings(allow_commit=True, confirm_mode=ConfirmMode.OOB, audit_log_path=tmp_path / "a.jsonl",
                 generated_tools_path=pack, key_policy_path=pol)
    server, service = build_service(s, fake_insurance())

    async def go():
        async with __import__("mcp").Client(server) as c:
            return sorted(t.name for t in (await c.list_tools()).tools
                          if t.name in ("lookup_policy", "list_policies", "update_policy"))

    assert anyio.run(go) == ["list_policies", "lookup_policy", "update_policy"]


def test_configured_but_missing_pack_fails_loudly(tmp_path):
    with pytest.raises(ToolPackError):
        rig(tmp_path, tmp_path / "nope.json", None)


def test_screenout_exposes_volatile_runs_from_the_fake_app():
    from seance_mcp.fake import DEMO_VOLATILE_REGIONS, fake_insurance
    from seance_mcp.screens import screen_out, volatile_runs

    assert volatile_runs(()) == []
    assert volatile_runs((0, 1, 2, 5, 6)) == [(0, 0, 3), (0, 5, 2)]
    assert volatile_runs((79, 80)) == [(0, 79, 1), (1, 0, 1)]  # a run never crosses a row boundary
    out = screen_out(fake_insurance().screens["enquiry"].model())
    assert out.volatile  # the enquiry output fields are masked
    assert all(0 <= r < 24 and 0 <= c < 80 and n >= 1 for r, c, n in out.volatile)
    # every run is a subset of the app's declared regions
    declared = {(r, c + i) for r, c, n in DEMO_VOLATILE_REGIONS for i in range(n)}
    covered = {(r, c + i) for r, c, n in out.volatile for i in range(n)}
    assert covered <= declared


def test_env_parsing():
    s = Settings.from_env({"GENERATED_TOOLS_PATH": "docs/x/tools.json", "SEANCE_ALLOW_UNREVIEWED_TOOLS": "1"})
    assert str(s.generated_tools_path).endswith("tools.json") and s.allow_unreviewed_tools
    assert not Settings.from_env({}).allow_unreviewed_tools
    with pytest.raises(ValueError):
        Settings.from_env({"SEANCE_ALLOW_UNREVIEWED_TOOLS": "yes"})


def test_seance_app_selects_a_fake_port_not_the_live_bridge(tmp_path):
    from seance_mcp.fake import FakeApp

    s = Settings.from_env({"SEANCE_APP": "fake-insurance", "AUDIT_LOG_PATH": str(tmp_path / "a.jsonl")})
    assert s.app == "fake-insurance"
    _, service = build_service(s)
    assert isinstance(service.port, FakeApp)
    assert getattr(service.port, "is_live", False) is False  # never subject to the live guard

    async def go():
        return (await service.connect()).screen_id

    assert anyio.run(go)  # connects with no container, no live marker


def test_unknown_seance_app_is_a_clear_error(tmp_path):
    s = Settings(app="nope", audit_log_path=tmp_path / "a.jsonl")
    with pytest.raises(ValueError, match="not a known fake app"):
        build_service(s)


@settings(max_examples=60, deadline=None)
@given(st.lists(st.tuples(st.sampled_from(["lookup_policy", "list_policies", "update_policy", "read_screen", "x"]),
                          st.booleans(), st.booleans()), max_size=6))
def test_property_registered_implies_valid_and_approved(items):
    """For any pack, every registered tool is well formed, hash-true and approved."""
    import tempfile
    from pathlib import Path

    d = Path(tempfile.mkdtemp())
    tools, approve = [], []
    for name, tamper, approved in items:
        t = tool(name)
        if tamper:
            t["description"] = "tampered"           # content changed, hash not recomputed
        tools.append(t)
        if approved:
            approve.append(t)
    pack, appr = write_pack(d, tools, approve=approve)
    r = load_toolpack(pack, appr)
    approvals = {t["name"]: t["def_hash"] for t in approve}
    names = [t["name"] for t in r.approved]
    assert len(names) == len(set(names))
    for t in r.approved:
        assert t["name"] not in GENERIC_TOOLS and t["def_hash"] == def_hash(t) and approvals.get(t["name"]) == t["def_hash"]
