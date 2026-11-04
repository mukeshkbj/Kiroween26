"""Safety gate: unit tests + a stateful Hypothesis model of the commit protocol."""
import pytest
from hypothesis import event, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule
from mcp.server.mcpserver import AcceptedElicitation, CancelledElicitation, DeclinedElicitation

from seance_bridge import COMMIT_CAPABLE, Key
from seance_mcp.config import ConfirmMode
from seance_mcp.safety import (
    Confirm,
    ConfirmationUnavailable,
    Decision,
    GateError,
    KeyPolicy,
    SafetyGate,
    SkipElicitation,
    decide,
    decide_elicit,
)

TTL = 30.0
YES = Decision(True, "elicit")
NO = Decision(False, "elicit", "declined", "no")


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def gate(allow=True, ttl=300.0, policy=None):
    c = Clock()
    return SafetyGate(allow_commit=allow, ttl_s=ttl, policy=policy or KeyPolicy(), clock=c), c


# ---------------------------------------------------------------- policy


def test_default_policy_is_bridge_commit_capable():
    p = KeyPolicy()
    assert all(p.may_commit(k, "s") for k in COMMIT_CAPABLE)
    assert not p.may_commit(Key.CLEAR, "s")
    assert not p.may_commit(Key.PF13, "s")


def test_override_marks_keys_read_only_on_that_screen_only():
    p = KeyPolicy({"menu": frozenset({"PF3", "Enter"})})
    assert not p.may_commit(Key.PF3, "menu")
    assert not p.may_commit(Key.ENTER, "menu")
    assert p.may_commit(Key.ENTER, "update-screen")
    assert p.may_commit(Key.PF3, None)


def test_policy_loads_from_json(tmp_path):
    f = tmp_path / "policy.json"
    f.write_text('{"abc": {"read_only_keys": ["pf7", "PF8"]}}', encoding="utf-8")
    p = KeyPolicy.load(f)
    assert not p.may_commit(Key.PF7, "abc") and not p.may_commit(Key.PF8, "abc")


# ---------------------------------------------------------------- gate


def test_happy_path_consumes_the_action():
    g, _ = gate()
    a, old = g.propose(Key.ENTER, "s1", [])
    assert old is None
    assert g.authorize(a.action_id, "s1", YES).action_id == a.action_id
    with pytest.raises(GateError) as e:
        g.authorize(a.action_id, "s1", YES)
    assert e.value.code == "unknown_action"


def test_expiry():
    g, c = gate(ttl=10)
    a, _ = g.propose(Key.ENTER, "s1", [])
    c.t += 10
    with pytest.raises(GateError) as e:
        g.authorize(a.action_id, "s1", YES)
    assert e.value.code == "action_expired"
    assert g.pending is None


def test_stale_screen_refused_and_dropped():
    g, _ = gate()
    a, _ = g.propose(Key.ENTER, "s1", [])
    with pytest.raises(GateError) as e:
        g.authorize(a.action_id, "s2", YES)
    assert e.value.code == "stale_screen" and g.pending is None


def test_read_only_blocks_but_keeps_pending():
    g, _ = gate(allow=False)
    a, _ = g.propose(Key.ENTER, "s1", [])
    with pytest.raises(GateError) as e:
        g.authorize(a.action_id, "s1", YES)
    assert e.value.code == "read_only" and g.pending == a


def test_declined_drops_the_action():
    g, _ = gate()
    a, _ = g.propose(Key.ENTER, "s1", [])
    with pytest.raises(GateError) as e:
        g.authorize(a.action_id, "s1", NO)
    assert e.value.code == "declined" and g.pending is None


def test_unavailable_keeps_pending_for_another_channel():
    g, _ = gate()
    a, _ = g.propose(Key.ENTER, "s1", [])
    d = Decision(False, "elicit", "confirmation_unavailable", "x")
    with pytest.raises(GateError) as e:
        g.authorize(a.action_id, "s1", d)
    assert e.value.code == "confirmation_unavailable" and g.pending == a


def test_new_proposal_supersedes_old():
    g, _ = gate()
    a, _ = g.propose(Key.ENTER, "s1", [])
    b, old = g.propose(Key.PF5, "s1", [])
    assert old == a
    with pytest.raises(GateError):
        g.authorize(a.action_id, "s1", YES)
    g.authorize(b.action_id, "s1", YES)


def test_ambiguous_ack_requires_resync():
    g, _ = gate()
    g.mark_ambiguous()
    with pytest.raises(GateError) as e:
        g.propose(Key.ENTER, "s1", [])
    assert e.value.code == "needs_resync"
    g.resynced()
    g.propose(Key.ENTER, "s1", [])


def test_peek_never_mutates():
    g, c = gate(ttl=5)
    a, _ = g.propose(Key.ENTER, "s1", [])
    assert g.peek(a.action_id) == a
    c.t += 5
    assert g.peek(a.action_id) is None
    assert g.pending == a  # expiry is only applied by authorize


def test_oob_approval_then_authorize():
    g, _ = gate()
    a, _ = g.propose(Key.ENTER, "s1", [])
    assert decide(ConfirmMode.OOB, None, "kiro", g.peek(a.action_id)).approved is False
    g.approve_oob(a.action_id, "web-ui")
    d = decide(ConfirmMode.OOB, None, "kiro", g.peek(a.action_id))
    assert d.approved and d.confirmed_by == "oob:web-ui"
    g.authorize(a.action_id, "s1", d)


def test_deny_oob_drops_the_action_for_good():
    g, c = gate(ttl=5)
    a, _ = g.propose(Key.ENTER, "s1", [])
    g.approve_oob(a.action_id, "web-ui")           # even an approved action can still be denied
    assert g.deny_oob(a.action_id, "web-ui") == g.pending or g.pending is None
    assert g.pending is None
    with pytest.raises(GateError) as e:
        g.authorize(a.action_id, "s1", YES)
    assert e.value.code == "unknown_action"
    with pytest.raises(GateError) as e:
        g.deny_oob(a.action_id, "web-ui")          # twice
    assert e.value.code == "unknown_action"
    with pytest.raises(GateError) as e:
        g.deny_oob("nope", "web-ui")
    assert e.value.code == "unknown_action"


def test_deny_oob_of_expired_action_reports_expiry_and_drops_it():
    g, c = gate(ttl=5)
    a, _ = g.propose(Key.ENTER, "s1", [])
    c.t += 5
    with pytest.raises(GateError) as e:
        g.deny_oob(a.action_id, "web-ui")
    assert e.value.code == "action_expired" and g.pending is None


def test_client_approval_is_flagged_weakest():
    d = decide(ConfirmMode.CLIENT_APPROVAL, None, "kiro", None)
    assert d.approved and d.confirmed_by.startswith("client-approval(weakest):")


# ---------------------------------------------------------------- the spike trap


def test_only_accepted_confirm_true_approves():
    assert decide_elicit(AcceptedElicitation(data=Confirm(confirm=True))).approved


@pytest.mark.parametrize(
    "answer, code",
    [
        (AcceptedElicitation(data=Confirm(confirm=False)), "declined"),
        # A resolver's direct return value arrives wrapped as AcceptedElicitation.
        (AcceptedElicitation(data=ConfirmationUnavailable(reason="no cap")), "confirmation_unavailable"),
        (AcceptedElicitation(data=SkipElicitation(reason="read-only")), "not_confirmed"),
        (AcceptedElicitation(data={"confirm": True}), "declined"),  # untyped dict is not a Confirm
        (DeclinedElicitation(), "declined"),
        (CancelledElicitation(), "cancelled"),
        (None, "confirmation_unavailable"),
        ("yes", "confirmation_unavailable"),
    ],
)
def test_everything_else_refuses(answer, code):
    d = decide_elicit(answer)
    assert d.approved is False and d.code == code


# ---------------------------------------------------------------- stateful model


class CommitProtocol(RuleBasedStateMachine):
    """Drive the gate the way the tools do; a key is 'sent' only through the
    same paths the tool layer uses. Invariant: every commit-capable key sent was
    authorized by exactly one approved, unexpired, same-screen confirmation."""

    def __init__(self):
        super().__init__()
        self.clock = Clock()
        self.gate = SafetyGate(allow_commit=True, ttl_s=TTL, clock=self.clock)
        self.screen = "s0"
        self.sent: list[tuple[str, str]] = []          # (key, screen) actually sent
        self.authorized: list[tuple[str, str]] = []    # (key, screen) a human approved, in time
        self.issued: list[str] = []
        self.created: dict[str, tuple[float, str]] = {}
        self.used: set[str] = set()
        self.dirty_since: dict[str, bool] = {}
        self.denied: set[str] = set()

    @precondition(lambda self: self.issued)
    @rule(i=st.integers(0, 50), latest=st.sampled_from([True, True, False]))
    def deny(self, i, latest):
        """A human says no through the oob channel. Own bookkeeping: a denied id
        must never be sent afterwards, whatever else happens."""
        action_id = self.issued[-1] if latest else self.issued[i % len(self.issued)]
        try:
            self.gate.deny_oob(action_id, "web-ui")
        except GateError as e:
            event(f"deny_refused:{e.code}")
            return
        event("denied")
        self.denied.add(action_id)

    @rule(key=st.sampled_from(list(Key)))
    def press(self, key):
        try:
            if self.gate.may_commit(key, self.screen):
                a, _ = self.gate.propose(key, self.screen, [])
                self.issued.append(a.action_id)
                self.created[a.action_id] = (self.clock.t, self.screen)
                self.dirty_since[a.action_id] = False
            else:
                self.gate.ensure_synced()
                self.sent.append((key.value, self.screen))
        except GateError:
            pass

    @precondition(lambda self: self.issued)
    # Weighted toward the success path (human yes, commits on, latest action)
    # so the authorized branch is common; every refusal path stays reachable.
    @rule(
        latest=st.sampled_from([True, True, True, False]),
        i=st.integers(0, 50),
        human=st.sampled_from([True, True, True, False]),
        allow=st.sampled_from([True, True, True, False]),
    )
    def confirm(self, latest, i, human, allow):
        action_id = self.issued[-1] if latest else self.issued[i % len(self.issued)]
        self.gate.allow_commit = allow
        decision = YES if human else NO
        try:
            a = self.gate.authorize(action_id, self.screen, decision)
        except GateError as e:
            event(f"refused:{e.code}")
            return
        event("authorized")
        # The model's OWN bookkeeping (not the gate's) must agree it was allowed.
        created, screen = self.created[action_id]
        assert human, "sent without a human yes"
        assert allow, "sent while read-only"
        assert self.clock.t - created < TTL, "sent after expiry"
        assert action_id not in self.used, "sent twice"
        assert action_id not in self.denied, "sent an action a human denied"
        assert action_id == self.issued[-1], "sent a superseded action"
        assert not self.dirty_since[action_id], "sent after an ambiguous ack without resync"
        assert screen == self.screen, "sent on a different screen"
        self.used.add(action_id)
        self.authorized.append((a.key, a.screen_id))
        self.sent.append((a.key, self.screen))

    @rule(seconds=st.sampled_from([0, 1, 5, 29, 30, 31, 45]))
    def tick(self, seconds):
        self.clock.t += seconds

    @rule(screen=st.sampled_from(["s0", "s1", "s2"]))
    def screen_changes(self, screen):
        self.screen = screen

    @precondition(lambda self: len(self.sent) % 3 == 0)
    @rule()
    def ambiguous(self):
        self.gate.mark_ambiguous()
        for k in self.dirty_since:
            self.dirty_since[k] = True

    @rule()
    def read_screen(self):
        self.gate.resynced()

    @invariant()
    def no_commit_without_its_own_confirmation(self):
        commits = [(k, s) for k, s in self.sent if Key(k) in COMMIT_CAPABLE]
        assert commits == self.authorized


CommitProtocol.TestCase.settings = settings(max_examples=300, stateful_step_count=50, deadline=None)
TestCommitProtocol = CommitProtocol.TestCase
