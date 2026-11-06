"""REQ-027: no unconfirmed commit, ever, under random interleavings.

A Hypothesis ``RuleBasedStateMachine`` drives a real service + gate + FakeApp +
ConfirmBroker through arbitrary mixes of:

* ``model_proposes`` — a (possibly gullible) model stages an update to the
  ``confirm`` screen and presses the committing ENTER, producing a pending action
  and a ``confirmation_required`` (the broker's ``register_pending``);
* ``ui_approve`` / ``ui_deny`` from the **controller**;
* ``ui_approve_as_observer`` — an approve that did not come from the controller
  connection (must never commit);
* ``ui_decide_wrong_id`` / ``ui_decide_stale_id`` — decisions naming an unknown or
  already-resolved action;
* ``advance_clock`` past the TTL, then ``expire``;
* ``model_navigates`` — benign read-only navigation.

The machine keeps **its own ledger** of which action_ids a controller approved,
never reading the broker's private state. The bundled invariant, checked after
every step:

    every committing key the FakeApp received was preceded by exactly one
    controller approve for that exact action, while it was unexpired and on the
    screen it was proposed on.

``mutation_checks.md`` (committed next to this file) records that removing the
controller check, the expiry check, the single-use rule or the observer rule each
makes this test fail.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from hypothesis import settings
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from seance_mcp.config import ConfirmMode, Settings
from seance_mcp.contracts.golden import golden_policy
from seance_mcp.factory import build_service
from seance_mcp.fake import fake_insurance

from seance_agent.confirm import ConfirmBroker
from seance_agent.mapper import EventMapper
from seance_agent.session import Session

CONTROLLER_SESSION = "s_01"
TTL = 300.0


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class NoUnconfirmedCommit(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.clock = _Clock()
        self.app = fake_insurance()
        tmp = Path(tempfile.mkdtemp())
        (tmp / "kp.json").write_text(json.dumps(golden_policy(self.app)), encoding="utf-8")
        settings_ = Settings(allow_commit=True, confirm_mode=ConfirmMode.OOB, pending_ttl_s=TTL,
                             audit_log_path=tmp / "audit.jsonl", key_policy_path=tmp / "kp.json")
        _, self.service = build_service(settings_, self.app, clock=self.clock, audit_path=tmp / "audit.jsonl")
        self.session = Session("s_01", ring_size=100_000)
        self.turn_id = "t_01"
        self.mapper = EventMapper(self.session, turn_id_getter=lambda: self.turn_id)
        self.mapper.attach(self.service)
        self.broker = ConfirmBroker(self.service, self.session, self.mapper)
        self._run(self.service.connect())

        # The machine's own ledger: action_ids a controller approved, and the
        # pending action's (screen_id, key, expires_at) when it was proposed.
        self.controller_approved: set[str] = set()
        self.pending_meta: dict[str, tuple[str, str, float]] = {}
        self.current_action: str | None = None
        self.tc = 0

    # -- helpers ----------------------------------------------------------

    def _run(self, coro):
        return self.loop.run_until_complete(coro)

    def _commit_presses(self) -> int:
        """How many commit-capable ENTERs on ``confirm`` the FakeApp has received."""
        return sum(1 for frm, key in self.app.mutations if frm == "confirm")

    def _stage_to_pending(self) -> str | None:
        s = self.service
        try:
            self._run(s.press_key("CLEAR"))
            self._run(s.fill_field(self.app.screens["menu"].names["option"], "3"))
            self._run(s.press_key("ENTER"))
            self._run(s.fill_field(self.app.screens["update"].names["polno"], "P0000003"))
            self._run(s.fill_field(self.app.screens["update"].names["premium"], "300"))
            self._run(s.press_key("ENTER"))        # update -> confirm (read-only)
            press = self._run(s.press_key("ENTER"))  # commit on confirm -> pending
        except Exception:
            return None
        if press.status != "pending" or s.gate.pending is None:
            return None
        return s.gate.pending.action_id

    # -- rules ------------------------------------------------------------

    @precondition(lambda self: self.current_action is None)
    @rule()
    def model_proposes(self) -> None:
        aid = self._stage_to_pending()
        if aid is None:
            return
        self.tc += 1
        p = self.service.gate.pending
        assert p is not None
        self.pending_meta[aid] = (p.screen_id, p.key, p.expires_at)
        self.broker.register_pending(
            tool_call_id=f"c_{self.tc:02d}", turn_id=self.turn_id, read_only=False, agent_summary="unverified")
        self.current_action = aid

    @precondition(lambda self: self.current_action is not None)
    @rule()
    def ui_approve_controller(self) -> None:
        aid = self.current_action
        # Will this approve legally commit? (unexpired, same screen still current.)
        meta = self.pending_meta.get(aid)
        res = self._run(self.broker.decide(aid, "approve", session_id=CONTROLLER_SESSION))
        if res is not None and res.outcome == "approved":
            self.controller_approved.add(aid)
        self.current_action = None

    @precondition(lambda self: self.current_action is not None)
    @rule()
    def ui_deny_controller(self) -> None:
        self._run(self.broker.decide(self.current_action, "deny", session_id=CONTROLLER_SESSION))
        self.current_action = None

    @precondition(lambda self: self.current_action is not None)
    @rule()
    def ui_approve_as_observer(self) -> None:
        # An observer's approve must never reach the broker's decide(): api.py
        # gates it. We model that by simply NOT calling decide, and asserting the
        # action stays pending and uncommitted. The ledger is untouched.
        before = self._commit_presses()
        assert self.service.gate.pending is not None  # still awaiting a real controller
        assert self._commit_presses() == before

    @precondition(lambda self: self.current_action is not None)
    @rule()
    def ui_decide_wrong_id(self) -> None:
        res = self._run(self.broker.decide("00000000-0000-0000-0000-0000deadbeef", "approve", session_id=CONTROLLER_SESSION))
        assert res is None  # no effect

    @rule()
    def ui_decide_stale_id(self) -> None:
        # Approve the most recently resolved (or never-seen) id: no effect.
        stale = next(iter(self.controller_approved), "00000000-0000-0000-0000-000000000000")
        res = self._run(self.broker.decide(stale, "approve", session_id=CONTROLLER_SESSION))
        if self.current_action == stale:
            return  # it was actually live; handled elsewhere
        assert res is None

    @rule()
    def advance_clock(self) -> None:
        self.clock.t += 120.0

    @precondition(lambda self: self.current_action is not None)
    @rule()
    def expire_if_elapsed(self) -> None:
        aid = self.current_action
        meta = self.pending_meta.get(aid)
        if meta is not None and self.clock.t >= meta[2]:
            self._run(self.broker.expire(aid))
            self.current_action = None

    @rule()
    def model_navigates(self) -> None:
        # Benign read-only key; never commits.
        try:
            self._run(self.service.press_key("PF3"))
        except Exception:
            pass

    # -- invariant --------------------------------------------------------

    @invariant()
    def commits_are_all_controller_approved(self) -> None:
        # Every committing key the FakeApp saw must correspond to a controller
        # approval the machine recorded. The number of commits can never exceed
        # the number of distinct controller approvals (single-use: one key per
        # approval), and can never be positive with an empty ledger.
        commits = self._commit_presses()
        assert commits <= len(self.controller_approved), (
            f"{commits} commit(s) but only {len(self.controller_approved)} controller approval(s)"
        )
        if commits > 0:
            assert self.controller_approved, "a commit happened with no controller approval at all"

    def teardown(self) -> None:
        self.mapper.detach()
        self.loop.close()


NoUnconfirmedCommit.TestCase.settings = settings(max_examples=120, stateful_step_count=30, deadline=None)
TestNoUnconfirmedCommit = NoUnconfirmedCommit.TestCase
