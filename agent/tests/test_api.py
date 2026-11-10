"""REQ-001/002/003/031: REST + websocket behaviour through Starlette's TestClient.

Real hub, real service over FakeApp with B's tool pack, scripted demo model.
"""
from __future__ import annotations

import json
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from seance_agent.api import create_app
from seance_agent.apps import AppRegistry
from seance_agent.config import Settings
from seance_agent.events import server_event_adapter
from seance_agent.hub import SeanceHub
from seance_mcp.contracts.models import SpiritMapView

from ._stream import check_stream

ORIGIN = "http://localhost:5173"
URL = "/ws/seance"


@contextmanager
def make_client(*, llm=None, env=None, registry=None, **settings_kw):
    tmp = Path(tempfile.mkdtemp())
    kw = dict(audit_log_path=tmp / "audit.jsonl", allow_commit=True, pending_ttl_s=300.0)
    kw.update(settings_kw)
    settings = Settings(**kw)
    hub = SeanceHub(settings, registry or AppRegistry.load(), session_id="s_test", env=env if env is not None else {},
                    llm=llm)
    with TestClient(create_app(settings, hub=hub), base_url="http://127.0.0.1:8000") as client:
        client.hub = hub  # type: ignore[attr-defined]
        yield client


def token(client) -> str:
    return client.get("/api/session", headers={"origin": ORIGIN}).json()["token"]


class Sock:
    """A websocket plus the events it has seen (for stream checks)."""

    def __init__(self, ws):
        self.ws, self.seen = ws, []

    def send(self, **msg) -> None:
        self.ws.send_text(json.dumps(msg))

    def recv(self) -> dict:
        ev = self.ws.receive_json()
        self.seen.append(ev)
        return ev

    def until(self, type_: str, pred=lambda e: True, limit: int = 400) -> dict:
        for _ in range(limit):
            ev = self.recv()
            if ev["type"] == type_ and pred(ev):
                return ev
        raise AssertionError(f"no {type_} within {limit} events")


@contextmanager
def open_ws(client, *, tok=None, origin=ORIGIN, resume_from=None, hello=True):
    headers = {"origin": origin} if origin else {}
    with client.websocket_connect(URL, headers=headers) as ws:
        timer = threading.Timer(20, lambda: ws.close())  # a failing test must not hang the run
        timer.daemon = True
        timer.start()
        s = Sock(ws)
        if hello:
            s.send(id="h1", type="hello", v=1, client="test/0", token=tok or token(client), resume_from=resume_from)
        try:
            yield s
        finally:
            timer.cancel()


def connect_fake(s: Sock) -> None:
    if not any(e["type"] == "session_state" for e in s.seen):
        s.until("session_state")
    s.send(id="c1", type="connect_system", app_id="fake-insurance")
    s.until("session_state", lambda e: e["data"]["state"] == "connected")
    s.until("screen", lambda e: e["data"]["phase"] == "snapshot")


# ---------------------------------------------------------------- REST / origin


def test_rest_origin_and_cors() -> None:
    with make_client() as c:
        assert c.get("/api/health").json()["ok"] is True
        assert c.get("/api/health", headers={"origin": "http://evil.example"}).status_code == 403
        r = c.get("/api/session", headers={"origin": ORIGIN})
        assert r.status_code == 200 and r.headers["access-control-allow-origin"] == ORIGIN
        assert c.get("/api/session", headers={"origin": "http://evil.example"}).status_code == 403
        assert "access-control-allow-origin" not in c.get("/api/health", headers={"origin": "http://evil.example"}).headers


def test_apps_and_spirit_map_view_match_the_contract() -> None:
    with make_client() as c:
        apps = {a["app_id"]: a for a in c.get("/api/apps").json()["apps"]}
        assert apps["fake-insurance"]["has_map"] and apps["fake-insurance"]["tools"] == {"business": 3, "approved": 3}
        assert apps["tk4-builtins"]["reachable"] is None  # never probed
        view = c.get("/api/apps/fake-insurance/spirit-map")
        assert view.status_code == 200
        SpiritMapView.model_validate(view.json())
        assert c.get("/api/apps/..%2F..%2Fetc/spirit-map").status_code == 404
        assert c.get("/api/apps/nope/spirit-map").json() == {"error": "no_map"}
        # seance-insurance has a map once B promotes A's live exploration; valid either way.
        live = c.get("/api/apps/seance-insurance/spirit-map")
        assert live.status_code in (200, 404)
        if live.status_code == 200:
            SpiritMapView.model_validate(live.json())


def test_a_registered_app_without_a_map_is_404(tmp_path) -> None:
    """Known app, no spirit-map.json: 404 no_map. Uses its own artefact dir, not repo data."""
    from seance_agent.apps import AppEntry

    entry = AppEntry(app_id="no-map-app", name="No map", kind="fake", fake="fake_insurance", description="test")
    registry = AppRegistry(AppRegistry.load().all() + [entry], root=tmp_path)  # tmp root: no artefacts at all
    with make_client(registry=registry) as c:
        r = c.get("/api/apps/no-map-app/spirit-map")
        assert r.status_code == 404 and r.json() == {"error": "no_map"}
        info = {a["app_id"]: a for a in c.get("/api/apps").json()["apps"]}["no-map-app"]
        assert info["has_map"] is False and info["tools"] == {"business": 0, "approved": 0}


def test_audit_endpoint() -> None:
    with make_client() as c:
        body = c.get("/api/audit?limit=5").json()
        assert body["chain_ok"] is True and body["broken_seq"] is None


# ---------------------------------------------------------------- websocket access


@pytest.mark.parametrize("origin", ["http://evil.example", None])
def test_websocket_refuses_bad_or_missing_origin(origin) -> None:
    with make_client() as c:
        with pytest.raises(WebSocketDisconnect) as exc:
            with open_ws(c, origin=origin, hello=False) as s:
                s.ws.receive_json()
        assert exc.value.code == 4403


def test_websocket_requires_a_valid_token() -> None:
    with make_client() as c:
        with pytest.raises(WebSocketDisconnect) as exc:
            with open_ws(c, tok="not-a-token") as s:
                s.ws.receive_json()
        assert exc.value.code == 4401


def test_first_message_must_be_hello() -> None:
    with make_client() as c:
        with pytest.raises(WebSocketDisconnect) as exc:
            with open_ws(c, hello=False) as s:
                s.send(id="p", type="ping")
                s.ws.receive_json()
        assert exc.value.code == 4400


# ---------------------------------------------------------------- happy path


def test_lookup_turn_streams_a_valid_ordered_stream() -> None:
    with make_client() as c, open_ws(c) as s:
        first = s.until("session_state")
        assert first["data"]["controller"] is True and first["data"]["state"] == "disconnected"
        connect_fake(s)
        s.send(id="u1", type="user_message", text="Look up policy P0000003")
        s.until("turn_finished")
        msg = [e for e in s.seen if e["type"] == "assistant_message"][-1]["data"]["text"]
        assert "A. ROSE" in msg
        assert any(e["type"] == "field_focus" for e in s.seen)
        for e in s.seen:
            server_event_adapter.validate_python(e)
        check_stream(s.seen)


def test_commit_needs_the_controller_to_approve() -> None:
    with make_client() as c, open_ws(c) as ctl:
        connect_fake(ctl)
        with open_ws(c) as obs:
            st = obs.until("session_state")
            assert st["data"]["controller"] is False
            ctl.send(id="u1", type="user_message", text="Set the premium of policy P0000003 to 300")
            req = ctl.until("confirmation_required")["data"]
            app = c.hub.live.rt.service.port  # the FakeApp
            # An observer cannot approve.
            obs.send(id="o1", type="confirm_decision", action_id=req["action_id"], decision="approve")
            err = obs.until("error", lambda e: e["data"]["ref"] == "o1")
            assert err["data"]["code"] == "observer_only"
            assert not app.dirty
            # The controller can.
            ctl.send(id="d1", type="confirm_decision", action_id=req["action_id"], decision="approve")
            res = ctl.until("confirmation_resolved")["data"]
            assert res["outcome"] == "approved" and res["confirmed_by"] == "oob:web-ui:s_test"
            ctl.until("turn_finished")
            assert app.dirty and len(app.mutations) == 1
        check_stream(ctl.seen)


def test_deny_and_unknown_action() -> None:
    with make_client() as c, open_ws(c) as s:
        connect_fake(s)
        s.send(id="u1", type="user_message", text="Set the premium of policy P0000003 to 300")
        req = s.until("confirmation_required")["data"]
        s.send(id="bad", type="confirm_decision", action_id="00000000-0000-0000-0000-000000000000", decision="approve")
        assert s.until("error", lambda e: e["data"]["ref"] == "bad")["data"]["code"] == "unknown_action"
        s.send(id="d1", type="confirm_decision", action_id=req["action_id"], decision="deny")
        assert s.until("confirmation_resolved")["data"]["outcome"] == "denied"
        s.until("turn_finished")
        assert not c.hub.live.rt.service.port.dirty
        # A resolved id cannot be decided again.
        s.send(id="again", type="confirm_decision", action_id=req["action_id"], decision="approve")
        assert s.until("error", lambda e: e["data"]["ref"] == "again")["data"]["code"] == "unknown_action"
        assert not c.hub.live.rt.service.port.dirty
        check_stream(s.seen)


def test_read_only_server_shows_blocked_not_silent() -> None:
    with make_client(allow_commit=False) as c, open_ws(c) as s:
        assert s.until("session_state")["data"]["read_only"] is True
        connect_fake(s)
        s.send(id="u1", type="user_message", text="Set the premium of policy P0000003 to 300")
        req = s.until("confirmation_required")["data"]
        assert req["read_only"] is True
        s.send(id="d1", type="confirm_decision", action_id=req["action_id"], decision="approve")
        assert s.until("confirmation_resolved")["data"]["outcome"] == "blocked_read_only"
        s.until("turn_finished")
        assert not c.hub.live.rt.service.port.dirty


def test_live_app_refused_without_permission() -> None:
    with make_client() as c, open_ws(c) as s:
        s.until("session_state")
        s.send(id="c1", type="connect_system", app_id="tk4-builtins")
        assert s.until("error")["data"]["code"] == "live_not_allowed"
        assert c.hub.live is None and c.hub.state == "disconnected"
        s.send(id="c2", type="connect_system", app_id="nope")
        assert s.until("error", lambda e: e["data"]["ref"] == "c2")["data"]["code"] == "unknown_app"


def test_llm_unavailable_is_an_event_not_a_crash() -> None:
    with make_client(llm=(None, False)) as c, open_ws(c) as s:
        assert s.until("session_state")["data"]["llm"]["available"] is False
        connect_fake(s)
        s.send(id="u1", type="user_message", text="hello")
        assert s.until("error")["data"]["code"] == "llm_unavailable"


def test_message_before_connect_and_bad_message() -> None:
    with make_client() as c, open_ws(c) as s:
        s.until("session_state")
        s.send(id="u1", type="user_message", text="hi")
        assert s.until("error")["data"]["code"] == "not_connected"
        s.ws.send_text("{not json")
        assert s.until("error")["data"]["code"] == "bad_message"


# ---------------------------------------------------------------- resume


def _controller_then_watcher(c, tok):
    """Open the controller first, then an observer tab, then drop the controller."""
    ctl_cm = open_ws(c, tok=tok)
    ctl = ctl_cm.__enter__()
    connect_fake(ctl)
    watcher_cm = open_ws(c)
    watcher = watcher_cm.__enter__()
    assert watcher.until("session_state")["data"]["controller"] is False
    last = ctl.seen[-1]["seq"]
    ctl_cm.__exit__(None, None, None)
    return watcher_cm, last


def test_dropped_controller_keeps_its_slot_while_another_tab_is_open() -> None:
    with make_client() as c:
        tok = token(c)
        watcher_cm, last = _controller_then_watcher(c, tok)
        try:
            with open_ws(c) as other:  # a new tab while another tab is open: observer
                assert other.until("session_state")["data"]["controller"] is False
            with open_ws(c, tok=tok, resume_from=last) as s2:  # same token, resuming: controller
                st = s2.until("session_state")
                assert st["data"]["controller"] is True and st["seq"] > last
                assert all(e["seq"] > last for e in s2.seen)
        finally:
            watcher_cm.__exit__(None, None, None)


def test_reconnect_with_a_fresh_token_still_reclaims_the_slot_when_resuming() -> None:
    """The web client fetches a NEW token on every reconnect (found by reading its transport)."""
    with make_client() as c:
        watcher_cm, last = _controller_then_watcher(c, token(c))
        try:
            with open_ws(c, tok=token(c), resume_from=last) as back:
                assert back.until("session_state")["data"]["controller"] is True
        finally:
            watcher_cm.__exit__(None, None, None)

def test_ids_stay_unique_across_a_reconnect_of_the_system() -> None:
    """Found running C's reducer live: turn/message/call ids restarted per connect_system,
    so a client keyed on them attached a new confirmation to an old, finished turn."""
    with make_client() as c, open_ws(c) as s:
        connect_fake(s)
        s.send(id="u1", type="user_message", text="Look up policy P0000003")
        s.until("turn_finished")
        s.send(id="c2", type="connect_system", app_id="fake-insurance")
        s.until("session_state", lambda e: e["data"]["state"] == "connected" and e["seq"] > s.seen[-1]["seq"] - 1)
        s.until("screen", lambda e: e["data"]["phase"] == "snapshot")
        s.send(id="u2", type="user_message", text="Look up policy P0000004")
        s.until("turn_finished", lambda e: e["data"]["reason"] and e["turn_id"] != s.seen[0].get("turn_id"))
        turns = [e["turn_id"] for e in s.seen if e["type"] == "turn_started"]
        calls = [e["data"]["tool_call_id"] for e in s.seen if e["type"] == "tool_call"]
        msgs = [e["data"]["message_id"] for e in s.seen if e["type"] == "assistant_message"]
        assert len(turns) == 2 and len(set(turns)) == 2
        assert len(set(calls)) == len(calls) and len(set(msgs)) == len(msgs)
        check_stream(s.seen)


def test_page_reload_with_nothing_else_open_is_controller_at_once() -> None:
    """Found running C's client live: a reload sends no resume_from and must not wait 60 s."""
    with make_client() as c:
        with open_ws(c) as s:
            connect_fake(s)
        with open_ws(c) as reloaded:
            assert reloaded.until("session_state")["data"]["controller"] is True


def test_a_late_fresh_client_gets_a_baseline_from_seq_1() -> None:
    """Found running C's reducer live: a client with no history must start at seq 1 or a resync."""
    with make_client() as c:
        with open_ws(c) as s:
            connect_fake(s)
        with open_ws(c) as late:
            first = late.recv()
            assert first["seq"] == 1
            late.until("screen", lambda e: e["data"]["phase"] == "snapshot")
            check_stream(late.seen)

def test_resume_outside_the_ring_resyncs_with_a_snapshot() -> None:
    with make_client() as c:
        with open_ws(c) as s:
            connect_fake(s)
        with open_ws(c, resume_from=999_999) as s2:
            st = s2.until("session_state")
            assert st["data"]["resync"] is True
            assert s2.until("screen")["data"]["phase"] == "snapshot"
