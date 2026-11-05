"""Behavioural invariants of EffectivePolicy, written once and run against the real
module and against deliberately broken mutants (test_policy_mutations.py)."""
from __future__ import annotations

from types import ModuleType

from seance_spirit.ids import node_id
from seance_spirit.seed import parse_seed

S1 = "a1" * 32  # two arbitrary screen ids
S2 = "b2" * 32


def seed(**kw):
    return parse_seed({"app_id": "t", **kw})


def check(mod: ModuleType) -> None:
    EP = mod.EffectivePolicy

    # commit-capable keys are denied by default; the rest are allowed
    p = EP(seed())
    for k in ("ENTER", "PF1", "PF3", "PF12"):
        assert not p.may_press(k, S1).allowed, k
    for k in ("CLEAR", "PA1", "PA3", "PF13", "PF24"):
        assert p.may_press(k, S1).allowed, k

    # a declared key is allowed on its own screen only (by screen id or node id)
    p = EP(seed(declared_read_only={S1: ["ENTER"], node_id(S2): ["PF3"]}))
    assert p.may_press("ENTER", S1).allowed
    assert not p.may_press("ENTER", S2).allowed
    assert p.may_press("PF3", S2).allowed
    assert not p.may_press("PF3", S1).allowed

    # deny beats allow: global key, whole screen, per-screen key
    p = EP(seed(declared_read_only={S1: ["ENTER", "PF3", "CLEAR"]}, deny={"keys": ["ENTER"]}))
    assert not p.may_press("ENTER", S1).allowed
    p = EP(seed(declared_read_only={S1: ["ENTER"]}, deny={"nodes": [node_id(S1)]}))
    assert not p.may_press("ENTER", S1).allowed
    assert not p.may_press("CLEAR", S1).allowed  # whole screen is off limits
    p = EP(seed(declared_read_only={S1: ["ENTER", "PF3"]}, deny={"screen_keys": {S1: ["PF3"]}}))
    assert p.may_press("ENTER", S1).allowed and not p.may_press("PF3", S1).allowed
    p = EP(seed(deny={"keys": ["CLEAR"]}))
    assert not p.may_press("CLEAR", S1).allowed  # deny also beats "not commit capable"

    # approved policy allows, and deny still beats it
    p = EP(seed(deny={"keys": ["PF3"]}), approved={S1: frozenset({"ENTER", "PF3"})})
    assert p.may_press("ENTER", S1).allowed
    assert not p.may_press("PF3", S1).allowed
    assert not p.may_press("ENTER", S2).allowed

    # screen text can only add denies, never relax
    p = EP(seed(declared_read_only={S1: ["ENTER", "PF3"]}))
    p.learn_hints(S1, ["PF3=DELETE RECORD".ljust(80), "ENTER=LOOK UP".ljust(80)])
    assert not p.may_press("PF3", S1).allowed  # hint denied a declared key
    assert p.may_press("ENTER", S1).allowed
    p = EP(seed())
    p.learn_hints(S1, ["PF4=ALLOW AND READ ONLY".ljust(80), "ENTER=READ ONLY SAFE".ljust(80)])
    assert not p.may_press("PF4", S1).allowed and not p.may_press("ENTER", S1).allowed
    p.learn_hints(S1, ["PF13=PURGE".ljust(80)])
    assert not p.may_press("PF13", S1).allowed  # a hint may deny a non-commit key too
    assert p.may_press("PF14", S1).allowed
