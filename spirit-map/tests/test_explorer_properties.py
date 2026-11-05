"""Property tests for the explorer (REQ-032, REQ-033, REQ-034), with mutation checks.

The model of "what may be pressed" lives in ``fake_apps.Case.allowed``; it is written from
the case's own data (what the strategy declared and denied), never from the code under test.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import anyio
import pytest
from hypothesis import HealthCheck, given, settings

from seance_spirit import driver as driver_mod
from seance_spirit import policy as policy_mod
from seance_spirit.driver import Halt
from seance_spirit.explorer import Explorer
from seance_spirit.ids import key_name
from seance_spirit.policy import EffectivePolicy
from seance_spirit.replay import replay_map

from .fake_apps import SECRET_CELLS, Case, cases
from .test_policy_mutations import MUTANTS, SRC as POLICY_SRC

PROP = settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def explore(case: Case, policy_factory=EffectivePolicy):
    app = case.build()
    ex = Explorer(app, case.seed(), policy_factory=policy_factory)
    report = anyio.run(ex.run)
    return app, ex, report


def check_safety(case: Case, policy_factory=EffectivePolicy) -> None:
    app, ex, report = explore(case, policy_factory)
    for screen, key in app.received:
        assert case.allowed(int(screen[1:]), key), f"{key} was sent on {screen}"
    assert not app.dirty, f"app data changed: {app.mutations}"
    assert [k for _, k in ex.driver.keys_sent] == [k for _, k in app.received]
    for k, sd in enumerate(case.screens):
        if sd.has_secret:
            assert all(app.screens[f"s{k}"].text[p] == " " for p in SECRET_CELLS), "a hidden field was typed into"
    assert report.status in ("completed", "budget", "halted")


# ---------------------------------------------------------------- REQ-033: explorer safety


@PROP
@given(cases())
def test_explorer_never_sends_a_disallowed_key_and_never_changes_data(case: Case) -> None:
    check_safety(case)


# ---------------------------------------------------------------- mutation checks of the safety property
#
# The explorer has independent layers (see explorer.py): the policy, candidate generation (only
# declared commit keys are ever tried), the driver's own check, and the service gate, which reads
# the declarations straight from the data. A mutation oracle is a small hand-built hostile app
# plus the same ``check_safety``: a broken rule must fail it, the real code must pass it.


def mk(n: int, trans: dict[int, dict[str, tuple[int, bool]]], declared=(), deny_keys=(), deny_screens=(),
       deny_screen_keys=(), danger: dict[int, tuple[str, ...]] | None = None) -> Case:
    """A hostile app: ``trans[screen][key] = (target, mutating)``."""
    from .fake_apps import ScreenDef, Trans

    danger = danger or {}
    screens = tuple(
        ScreenDef(False, frozenset(danger.get(k, ())),
                  tuple(sorted((key, Trans(to, mut, False)) for key, (to, mut) in trans.get(k, {}).items())))
        for k in range(n))
    return Case(screens, True, frozenset(declared), frozenset(deny_keys), frozenset(deny_screens),
                frozenset(deny_screen_keys))


HOME = {"CLEAR": (0, False)}
ORACLES = {
    "deny key": mk(2, {0: {**HOME, "PA1": (1, False)}, 1: HOME}, deny_keys={"PA1"}),
    "deny screen": mk(2, {0: {**HOME, "PA1": (1, False)}, 1: {**HOME, "PA2": (0, False)}}, deny_screens={1}),
    "deny screen key": mk(2, {0: {**HOME, "PA1": (1, False)}, 1: HOME}, deny_screen_keys={(0, "PA1")}),
    "deny beats declared": mk(2, {0: {**HOME, "ENTER": (1, False)}, 1: HOME}, declared={(0, "ENTER")},
                              deny_keys={"ENTER"}),
    "legend says DELETE": mk(2, {0: {**HOME, "ENTER": (1, False)}, 1: HOME}, declared={(0, "ENTER")},
                             danger={0: ("ENTER",)}),
}
OVER_ALLOW = {
    "undeclared commit keys": mk(2, {0: {**HOME, "ENTER": (1, True), "PF9": (1, True)}, 1: HOME}),
    "declaration on another screen": mk(
        2, {0: {**HOME, "PF3": (1, False)}, 1: {**HOME, "PF3": (0, True)}}, declared={(0, "PF3")}),
}
KILLED_BY = {
    "drop global key deny": "deny key",
    "drop screen deny": "deny screen",
    "drop per-screen key deny": "deny screen key",
    "text hint no longer denies": "legend says DELETE",
    "text hint relaxes (allows what it names)": "legend says DELETE",
    "allow before deny": "deny beats declared",
}


def _mutant_policy(name: str):
    old, new = MUTANTS[name]
    assert old in POLICY_SRC
    mod = types.ModuleType("seance_spirit._mutant_policy_x")
    mod.__package__ = "seance_spirit"
    sys.modules[mod.__name__] = mod
    exec(compile(POLICY_SRC.replace(old, new, 1), "<mutant>", "exec"), mod.__dict__)  # noqa: S102
    return mod.EffectivePolicy


@pytest.mark.parametrize("name", sorted(ORACLES))
def test_real_code_passes_every_oracle(name: str) -> None:
    check_safety(ORACLES[name])


@pytest.mark.parametrize("name", sorted(OVER_ALLOW))
def test_real_code_passes_over_allow_oracles(name: str) -> None:
    check_safety(OVER_ALLOW[name])


@pytest.mark.parametrize("name", sorted(KILLED_BY))
def test_policy_mutant_is_killed(name: str) -> None:
    with pytest.raises(AssertionError):
        check_safety(ORACLES[KILLED_BY[name]], _mutant_policy(name))


def check_dirty_free(case: Case, policy_factory=EffectivePolicy) -> None:
    app, _, _ = explore(case, policy_factory)
    assert not app.dirty, f"app data changed: {app.mutations}"


def _widen_candidates(monkeypatch) -> None:
    """Mutant: candidate generation also tries undeclared ENTER and PF1-12."""
    from seance_spirit import explorer as ex_mod

    monkeypatch.setattr(ex_mod, "_OTHER_KEYS", ex_mod._OTHER_KEYS + ex_mod._COMMIT_ORDER)


OVER_ALLOWING_POLICIES = ["commit check removed", "declared keys apply on every screen"]


@pytest.mark.parametrize("oracle", sorted(OVER_ALLOW))
@pytest.mark.parametrize("name", OVER_ALLOWING_POLICIES)
def test_policy_that_over_allows_is_neutralised_by_candidates_and_gate(name, oracle) -> None:
    """Policy mutant alone: the explorer never even tries undeclared commit keys."""
    check_dirty_free(OVER_ALLOW[oracle], _mutant_policy(name))


@pytest.mark.parametrize("oracle", sorted(OVER_ALLOW))
@pytest.mark.parametrize("name", OVER_ALLOWING_POLICIES)
def test_gate_alone_holds_when_policy_and_candidates_are_both_wrong(name, oracle, monkeypatch) -> None:
    _widen_candidates(monkeypatch)
    check_dirty_free(OVER_ALLOW[oracle], _mutant_policy(name))  # the gate holds the key as pending


def test_with_the_gate_opened_the_same_bugs_reach_the_app(monkeypatch) -> None:
    """Mutation check of the gate layer: open it and the data changes."""
    _widen_candidates(monkeypatch)
    monkeypatch.setattr(driver_mod.ExplorerKeyPolicy, "may_commit", lambda self, key, sid: False)
    with pytest.raises(AssertionError):
        check_dirty_free(OVER_ALLOW["undeclared commit keys"], _mutant_policy("commit check removed"))


# -- the driver's own layer, tested directly


def _driver_for(case: Case):
    from seance_spirit.driver import build_driver

    app = case.build()
    drv = build_driver(app, case.seed())
    anyio.run(lambda: drv.connect("localhost", 3270))
    return app, drv


def test_driver_refuses_a_denied_key_before_the_service() -> None:
    from seance_spirit.driver import PolicyDenied

    app, drv = _driver_for(ORACLES["deny key"])
    with pytest.raises(PolicyDenied):
        anyio.run(lambda: drv.press("PA1"))
    with pytest.raises(PolicyDenied):  # ENTER is commit-capable and undeclared
        anyio.run(lambda: drv.press("ENTER"))
    assert app.received == []


def test_driver_check_is_necessary_for_denied_non_commit_keys(monkeypatch) -> None:
    """Mutation check of the driver layer: without it a denied PA key reaches the app."""
    monkeypatch.setattr(driver_mod.Driver, "press", _press_without_policy)
    app, drv = _driver_for(ORACLES["deny key"])
    anyio.run(lambda: drv.press("PA1"))
    assert app.received == [("s0", "PA1")]  # the real driver raises PolicyDenied instead (test above)

async def _press_without_policy(self, key: str):
    screen = self.screen
    k = key_name(key)
    self._spend()
    self.keys_sent.append((screen.screen_id, k))
    out = await self.service.press_key(k)
    if out.status != "executed" or out.screen is None:
        raise Halt("unexpected_pending")
    self.screen = out.screen
    return out.screen


def test_driver_never_types_into_hidden_or_credential_fields() -> None:
    from seance_spirit.driver import PolicyDenied
    from .fake_apps import ScreenDef

    case = Case((ScreenDef(True, frozenset(), ()), ScreenDef(False, frozenset(), ())), True, frozenset(),
                frozenset(), frozenset(), frozenset())
    app, drv = _driver_for(case)
    hidden = next(f for f in drv.screen.fields if f.hidden)
    with pytest.raises(PolicyDenied):
        anyio.run(lambda: drv.fill(hidden.index, "TOPSECRET"))
    assert all(app.screens["s0"].text[p] == " " for p in SECRET_CELLS)
    protected = next(f for f in drv.screen.fields if f.protected)
    with pytest.raises(PolicyDenied):
        anyio.run(lambda: drv.fill(protected.index, "x"))

# ---------------------------------------------------------------- REQ-034: completeness


@PROP
@given(cases(connected=True, denies=False))
def test_every_reachable_screen_is_found(case: Case) -> None:
    _, ex, report = explore(case)
    assert report.status == "completed", report
    ids = case.screen_ids()
    found = {n.screen_id for n in ex.map.nodes}
    expected = {ids[k] for k in case.reachable()}
    assert expected <= found, "a reachable screen was missed"
    assert found <= set(ids)


# ---------------------------------------------------------------- REQ-032: replay


@PROP
@given(cases(denies=False))
def test_replay_of_a_fresh_copy_lands_on_every_recorded_screen(case: Case) -> None:
    _, ex, report = explore(case)
    if report.status != "completed":
        return
    fresh = case.build()
    rep = anyio.run(lambda: replay_map(fresh, ex.map, case.seed()))
    assert rep.halted is None and rep.mismatches == [], rep
    assert fresh.dirty is False
    for screen, key in fresh.received:
        assert case.allowed(int(screen[1:]), key)
    # every edge whose source is reachable by recorded read-only routes was replayed
    skipped_ok = {"no_route", "position_unknown"}
    assert set(rep.skipped.values()) <= skipped_ok, rep.skipped


def test_replay_detects_a_changed_app() -> None:
    from hypothesis import find

    case = find(cases(connected=True, denies=False, secrets=False),
                lambda c: len(c.screens) >= 3 and len(c.reachable()) >= 3,
                settings=settings(max_examples=500, database=None, derandomize=True))
    _, ex, report = explore(case)
    assert report.status == "completed"
    changed = case.build()
    # re-route every transition of screen 0 to a different screen
    other = 1 if True else 2
    for rule in changed.rules:
        if rule.frm == "s0" and rule.key != "Clear":
            rule.to = f"s{other}" if rule.to != f"s{other}" else "s2"
    rep = anyio.run(lambda: replay_map(changed, ex.map, case.seed()))
    edges_from_home = [e for e in ex.map.edges_from(ex.map.home) if e.key != "CLEAR"]
    if edges_from_home:
        assert rep.mismatches or rep.halted or rep.skipped
