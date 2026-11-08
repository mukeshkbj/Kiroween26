"""Contract artefacts (P0.7): committed schemas/examples are fresh, valid and honest."""
from __future__ import annotations

import copy
import json

import anyio
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from seance_bridge import COMMIT_CAPABLE, Key
from seance_mcp.config import ConfirmMode, Settings
from seance_mcp.contracts import generate
from seance_mcp.contracts.check import (
    EXAMPLES,
    ContractError,
    _no_hidden_values,
    check_stream,
    validate_all,
)
from seance_mcp.contracts.golden import GOLDEN_READ_ONLY_KEYS, SCREEN_ORDER, golden_policy
from seance_mcp.factory import build_service
from seance_mcp.fake import FakeApp, fake_insurance
from seance_mcp.safety import KeyPolicy
from seance_mcp.toolpack import def_hash, load_toolpack


def test_committed_contract_files_match_a_fresh_build():
    """If this fails: python -m seance_mcp.contracts.generate, then review the diff."""
    stale = []
    for rel, text in generate.build().items():
        p = generate.CONTRACTS / rel
        if not p.exists() or p.read_text(encoding="utf-8").replace("\r\n", "\n") != text:
            stale.append(rel)
    assert not stale, stale


def test_every_example_validates_against_schema_and_models():
    done = validate_all()
    assert any(d.startswith("ok: transcripts/commit-approve") for d in done) and len(done) >= 35


def events_of(name):
    lines = (EXAMPLES / "transcripts" / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines]


def test_check_stream_rejects_broken_streams():
    ev = [x["event"] for x in events_of("lookup") if x["dir"] == "server"]
    check_stream(ev)
    gap = copy.deepcopy(ev)
    del gap[3]
    with pytest.raises(ContractError, match="seq"):
        check_stream(gap)
    no_result = copy.deepcopy([e for e in ev if e["type"] != "tool_result"])
    for i, e in enumerate(no_result, 1):
        e["seq"] = i
    with pytest.raises(ContractError, match="lacking a result"):
        check_stream(no_result)
    unfinished = copy.deepcopy(ev[:-1])
    with pytest.raises(ContractError, match="never finished"):
        check_stream(unfinished)
    approve = [x["event"] for x in events_of("commit-approve") if x["dir"] == "server"]
    twice = copy.deepcopy(approve)
    resolved = next(e for e in twice if e["type"] == "confirmation_resolved")
    twice.insert(twice.index(resolved) + 1, copy.deepcopy(resolved))
    for i, e in enumerate(twice, 1):
        e["seq"] = i
    with pytest.raises(ContractError, match="confirmation_resolved"):
        check_stream(twice)


def test_hidden_field_with_a_value_is_rejected():
    _no_hidden_values({"fields": [{"hidden": True, "value": None}]}, "x")
    with pytest.raises(ContractError):
        _no_hidden_values({"fields": [{"hidden": True, "value": "secret"}]}, "x")


@pytest.mark.parametrize("name", ["lookup", "commit-deny", "commit-expire", "injection", "session-lost", "read-only",
                                  "commit-approve", "ambiguous-ack"])
def test_no_commit_key_executes_without_a_human_approval_in_any_transcript(name):
    """In every recorded conversation, a confirm_action that succeeded follows an approve decision."""
    lines = events_of(name)
    approved = False
    for ln in lines:
        if ln["dir"] == "client" and ln["msg"]["type"] == "confirm_decision":
            approved = ln["msg"]["decision"] == "approve"
        if ln["dir"] == "server" and ln["event"]["type"] == "audit_entry":
            en = ln["event"]["data"]["entry"]
            if en["tool"] == "confirm_action" and en["outcome"] == "ok":
                assert approved and en["confirmed_by"].startswith("oob:web-ui:")
                approved = False
    resolved = [l["event"]["data"]["outcome"] for l in lines if l["dir"] == "server" and l["event"]["type"] == "confirmation_resolved"]
    expected = {"lookup": [], "injection": [], "session-lost": [], "ambiguous-ack": [], "commit-approve": ["approved"],
                "commit-deny": ["denied"], "commit-expire": ["expired"], "read-only": ["blocked_read_only"]}[name]
    assert resolved == expected


def test_injection_transcript_has_hostile_text_only_as_data():
    lines = events_of("injection")
    hostile = "IGNORE PREVIOUS INSTRUCTIONS"
    seen_in_result = False
    for ln in lines:
        if ln["dir"] != "server":
            continue
        e = ln["event"]
        if e["type"] == "tool_result" and hostile in json.dumps(e["data"]["result"]):
            seen_in_result = True
        assert e["type"] not in ("confirmation_required", "confirmation_resolved")
        assert not (e["type"] == "audit_entry" and e["data"]["entry"]["tool"] in ("confirm_action", "deny_action"))
    assert seen_in_result


# ---------------------------------------------------------------- golden policy (contracts 10.2)

def test_golden_policy_file_loads_in_the_real_loader_and_matches_the_table(tmp_path):
    p = tmp_path / "kp.json"
    p.write_text(json.dumps(golden_policy()), encoding="utf-8")
    policy = KeyPolicy.load(p)
    app = fake_insurance()
    for name in SCREEN_ORDER:
        sid = app.screens[name].model().screen_id
        for key in Key:
            expect_commit = key in COMMIT_CAPABLE and key.name not in GOLDEN_READ_ONLY_KEYS[name]
            assert policy.may_commit(key, sid) == expect_commit, (name, key)
    # the only commit-capable key of the whole app that the policy lets through the gate: ENTER on confirm
    confirm = app.screens["confirm"].model().screen_id
    assert policy.may_commit(Key.ENTER, confirm) and not policy.may_commit(Key.PF3, confirm)


def _service(tmp_path, app):
    (tmp_path / "kp.json").write_text(json.dumps(golden_policy(app)), encoding="utf-8")
    s = Settings(allow_commit=True, confirm_mode=ConfirmMode.OOB, audit_log_path=tmp_path / "a.jsonl",
                 key_policy_path=tmp_path / "kp.json")
    _, svc = build_service(s, app)
    return svc


def test_with_the_golden_policy_lookups_and_navigation_never_need_confirmation(tmp_path):
    app = fake_insurance()
    svc = _service(tmp_path, app)

    async def go():
        await svc.connect()
        await svc.fill_field(app.screens["menu"].names["option"], "1")
        assert (await svc.press_key("ENTER")).status == "executed"
        await svc.fill_field(app.screens["enquiry"].names["polno"], "P0000002")
        assert (await svc.press_key("ENTER")).status == "executed"
        assert app.screens["enquiry"].get("holder") == "K. OKAFOR"
        assert (await svc.press_key("PF3")).status == "executed"
        return (await svc.press_key("CLEAR")).status

    assert anyio.run(go) == "executed" and not app.dirty


KEYS = ["ENTER", "CLEAR", "PF3", "PF7", "PF8", "PF1", "PA1"]


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
@given(st.lists(st.one_of(
    st.tuples(st.just("press"), st.sampled_from(KEYS)),
    st.tuples(st.sampled_from(["option", "polno", "status", "premium"]), st.text(alphabet="0123ALCP", max_size=7))),
    max_size=40))
def test_property_without_a_human_decision_the_golden_app_is_never_changed(tmp_path_factory, steps):
    """Nobody approves anything here, so whatever is typed or pressed, no data changes."""
    app = fake_insurance()
    svc = _service(tmp_path_factory.mktemp("g"), app)

    async def go():
        await svc.connect()
        for kind, val in steps:
            try:
                if kind == "press":
                    r = await svc.press_key(val)
                    if r.status == "pending":
                        assert app.current == "confirm" and r.action.key == "Enter"
                else:
                    spec = app.screens[app.current]
                    if kind in spec.names and spec.kinds[kind] in ("in", "num"):
                        await svc.fill_field(spec.names[kind], val)
            except Exception:
                pass

    anyio.run(go)
    assert not app.dirty and app.policies == fake_insurance().policies


# ---------------------------------------------------------------- tool pack, capture


def test_example_tool_pack_is_hash_true_and_fully_approved():
    d = EXAMPLES / "toolpack"
    r = load_toolpack(d / "tools.json", d / "tool-approvals.json")
    assert [t["name"] for t in r.approved] == ["lookup_policy", "list_policies", "update_policy"] and r.skipped == []
    assert all(t["def_hash"] == def_hash(t) for t in r.approved)
    update = next(t for t in r.approved if t["name"] == "update_policy")
    assert update["kind"] == "commit" and update["recipe"][-1]["op"] == "propose"
    # no recipe ever confirms anything: the vocabulary has no such step
    assert {s["op"] for t in r.approved for s in t["recipe"]} <= {"goto", "fill", "press", "extract", "extract_list", "propose"}
    # only the commit tool proposes; read tools never do
    assert all(s["op"] != "propose" for t in r.approved if t["kind"] == "read" for s in t["recipe"])


def test_example_capture_replays_through_fakeapp():
    app = FakeApp.from_capture(EXAMPLES / "capture" / "capture.json")

    async def go():
        m = await app.read_screen()
        opt = next(f for f in m.fields if not f.protected)
        await app.fill_field(opt.index, "1")
        after = await app.press(Key.ENTER)
        back = await app.press(Key.PF3)
        return m.screen_id, after.screen_id, back.screen_id

    menu, enq, back = anyio.run(go)
    assert len({menu, enq}) == 2 and back == menu


def test_ambiguous_ack_transcript_sends_the_key_once_and_ends_in_session_lost():
    lines = events_of("ambiguous-ack")
    ev = [x["event"] for x in lines if x["dir"] == "server"]
    result = next(e for e in ev if e["type"] == "tool_result")
    assert result["data"]["status"] == "error" and result["data"]["error_code"] == "ambiguous_ack"
    audit = [e["data"]["entry"] for e in ev if e["type"] == "audit_entry"]
    amb = [a for a in audit if a["outcome"] == "ambiguous_ack"]
    assert len(amb) == 1 and amb[0]["tool"] == "press_key" and amb[0]["key"] == "Enter"
    i = ev.index(result)
    # after the unanswered key nothing is pressed until a reconnect; the next press-like audit entry is
    # a connect, never a second Enter
    later = [a for a in audit if a["seq"] > amb[0]["seq"]]
    assert all(a["tool"] in ("connect", "read_screen") for a in later)
    states = [e["data"]["state"] for e in ev[i:] if e["type"] == "session_state"]
    assert states[0] == "session_lost" and states[-1] == "connected"
    assert ev[-1]["type"] == "screen" and ev[-1]["data"]["phase"] == "snapshot"
    check_stream(ev)
