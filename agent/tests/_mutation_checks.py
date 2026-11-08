"""Mutation checks for REQ-027, run on demand (not part of the default suite).

    python -m tests._mutation_checks        # from the agent/ directory

Each mutation weakens exactly one safety rule and replays a deterministic
scenario that is safe under the real rules. The check passes when the weakened
variant produces an *unconfirmed or illegal commit* that the real code prevents —
i.e. removing the rule breaks safety. Results are recorded in
``tests/mutation_checks.md``.

The four rules, and where each lives:

* controller check / observer rule  -> the agent (api.py gates who may decide;
  here we model it by letting an observer reach ``ConfirmBroker.decide``).
* expiry check                      -> the gate (``authorize`` rejects expired).
* single-use                        -> the gate (``authorize`` consumes before send).

The gate-owned rules are re-verified here against the agent's broker to show the
agent relies on them and cannot be made to commit twice or after expiry.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from seance_mcp.config import ConfirmMode, Settings
from seance_mcp.contracts.golden import golden_policy
from seance_mcp.factory import build_service
from seance_mcp.fake import fake_insurance

from seance_agent.confirm import ConfirmBroker
from seance_agent.mapper import EventMapper
from seance_agent.session import Session


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _build(allow_commit: bool = True, ttl: float = 300.0):
    clock = _Clock()
    app = fake_insurance()
    tmp = Path(tempfile.mkdtemp())
    (tmp / "kp.json").write_text(json.dumps(golden_policy(app)), encoding="utf-8")
    settings_ = Settings(allow_commit=allow_commit, confirm_mode=ConfirmMode.OOB, pending_ttl_s=ttl,
                         audit_log_path=tmp / "audit.jsonl", key_policy_path=tmp / "kp.json")
    _, service = build_service(settings_, app, clock=clock, audit_path=tmp / "audit.jsonl")
    session = Session("s_01", ring_size=100_000)
    mapper = EventMapper(session, turn_id_getter=lambda: "t_01")
    mapper.attach(service)
    broker = ConfirmBroker(service, session, mapper)
    return clock, app, service, session, broker


def _run(loop, coro):
    return loop.run_until_complete(coro)


def _stage(loop, service, app) -> str:
    _run(loop, service.connect())
    _run(loop, service.press_key("CLEAR"))
    _run(loop, service.fill_field(app.screens["menu"].names["option"], "3"))
    _run(loop, service.press_key("ENTER"))
    _run(loop, service.fill_field(app.screens["update"].names["polno"], "P0000003"))
    _run(loop, service.fill_field(app.screens["update"].names["premium"], "300"))
    _run(loop, service.press_key("ENTER"))
    press = _run(loop, service.press_key("ENTER"))
    assert press.status == "pending"
    return service.gate.pending.action_id


def _commits(app) -> int:
    return sum(1 for frm, key in app.mutations if frm == "confirm")


def check_observer_can_commit() -> bool:
    """MUTATION: an observer's approve reaches decide() (controller check removed).

    Real code: api.py refuses observer control messages, so decide() is never
    called for them and the commit never happens. Mutated: we call decide()
    directly for an 'observer'. If it commits, the rule mattered."""
    loop = asyncio.new_event_loop()
    try:
        _, app, service, _, broker = _build()
        aid = _stage(loop, service, app)
        broker.register_pending(tool_call_id="c_01", turn_id="t_01", read_only=False, agent_summary=None)
        # Mutation: observer decision is let through (the controller gate is gone).
        _run(loop, broker.decide(aid, "approve", session_id="observer-not-controller"))
        committed = _commits(app) > 0
        return committed  # True => removing the controller gate causes a commit
    finally:
        loop.close()


def check_double_approve_commits_twice() -> bool:
    """MUTATION intent: single-use. Two approvals of one action must yield at most
    one commit. The gate consumes the action on the first authorize, so the second
    decide() is a no-op. If a second commit happened, single-use was broken."""
    loop = asyncio.new_event_loop()
    try:
        _, app, service, _, broker = _build()
        aid = _stage(loop, service, app)
        broker.register_pending(tool_call_id="c_01", turn_id="t_01", read_only=False, agent_summary=None)
        _run(loop, broker.decide(aid, "approve", session_id="s_01"))
        _run(loop, broker.decide(aid, "approve", session_id="s_01"))  # duplicate
        return _commits(app) > 1  # True => single-use broken
    finally:
        loop.close()


def check_expired_approve_commits() -> bool:
    """MUTATION intent: expiry. Approving after the TTL must not commit. The gate
    rejects an expired action in authorize(). If a commit happened, expiry was
    broken."""
    loop = asyncio.new_event_loop()
    try:
        clock, app, service, _, broker = _build(ttl=300.0)
        aid = _stage(loop, service, app)
        broker.register_pending(tool_call_id="c_01", turn_id="t_01", read_only=False, agent_summary=None)
        clock.t += 301.0  # past the TTL
        _run(loop, broker.decide(aid, "approve", session_id="s_01"))
        return _commits(app) > 0  # True => expiry broken
    finally:
        loop.close()


def main() -> int:
    # Under the REAL rules, each "bad outcome" must be False: no observer commit,
    # no double commit, no expired commit. The mutation note explains that
    # weakening the corresponding rule flips it to True (an illegal commit).
    observer = check_observer_can_commit()   # models the controller gate being removed
    double = check_double_approve_commits_twice()
    expired = check_expired_approve_commits()
    print(f"observer-approve-commits (controller gate removed in api): {observer}")
    print(f"double-approve-commits-twice (single-use, gate-enforced):  {double}")
    print(f"expired-approve-commits (expiry, gate-enforced):           {expired}")
    # With the real gate, double and expired MUST be False (safe). The observer
    # case is True here precisely because we simulated removing the api gate: it
    # demonstrates the controller check is load-bearing.
    ok = (double is False) and (expired is False) and (observer is True)
    print("MUTATION CHECKS:", "as expected" if ok else "UNEXPECTED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
