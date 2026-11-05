import pytest
from hypothesis import given, strategies as st

from seance_bridge import COMMIT_CAPABLE
from seance_spirit import policy
from seance_spirit.ids import ALL_KEY_NAMES, node_id
from seance_spirit.seed import SeedError, parse_seed

from .policy_invariants import S1, S2, check, seed

KEYS = sorted(ALL_KEY_NAMES)
S = st.sampled_from([S1, S2])


def test_invariants_hold_for_real_policy() -> None:
    check(policy)


def test_commit_capable_names_match_bridge() -> None:
    from seance_spirit.ids import COMMIT_CAPABLE_NAMES

    assert COMMIT_CAPABLE_NAMES == {k.name for k in COMMIT_CAPABLE}


@given(key=st.sampled_from(KEYS), sid=S)
def test_empty_seed_allows_exactly_the_non_commit_keys(key: str, sid: str) -> None:
    from seance_spirit.ids import COMMIT_CAPABLE_NAMES

    allowed = policy.EffectivePolicy(seed()).may_press(key, sid).allowed
    assert allowed == (key not in COMMIT_CAPABLE_NAMES)


@given(key=st.sampled_from(KEYS), sid=S, declared=st.booleans(), approved=st.booleans(), hint=st.booleans(),
       deny_key=st.booleans(), deny_screen=st.booleans())
def test_model_of_the_decision(key, sid, declared, approved, hint, deny_key, deny_screen) -> None:
    """Independent model of the rules (own bookkeeping, not the policy's code)."""
    from seance_spirit.ids import COMMIT_CAPABLE_NAMES

    p = policy.EffectivePolicy(
        seed(declared_read_only={sid: [key]} if declared else {},
             deny={"keys": [key] if deny_key else [], "nodes": [node_id(sid)] if deny_screen else []}),
        approved={sid: frozenset({key})} if approved else {},
    )
    if hint:
        p.learn_hints(sid, [f"{key}=DELETE".ljust(80)])
    expected = not (deny_key or deny_screen or hint) and (declared or approved or key not in COMMIT_CAPABLE_NAMES)
    assert p.may_press(key, sid).allowed == expected


def test_legend_hints() -> None:
    assert policy.hint_denies(["PF4=DELETE  PF5=SAVE  PF3=BACK"]) == {"PF4", "PF5"}
    assert policy.hint_denies(["ENTER=CONFIRM AND SAVE  PF3=CANCEL"]) == {"ENTER"}
    assert policy.hint_denies(["ENTER=LOOK UP  PF3=BACK"]) == frozenset()


def test_read_only_keys_exclude_denied() -> None:
    p = policy.EffectivePolicy(seed(declared_read_only={S1: ["ENTER", "PF3"]}, deny={"keys": ["PF3"]}),
                               approved={S1: frozenset({"PF7"})})
    assert p.read_only_keys(S1) == {"ENTER", "PF7"}
    assert p.read_only_keys(S2) == frozenset()


# -- seed validation ---------------------------------------------------------------------------


def test_seed_rejects_unknown_fields_and_keys() -> None:
    with pytest.raises(SeedError):
        parse_seed({"app_id": "t", "declare_read_only": {}})
    with pytest.raises(SeedError):
        parse_seed({"app_id": "t", "declared_read_only": {S1: ["PF99"]}})


def test_seed_rejects_credential_probe() -> None:
    for pat in ("PASS|PWD", "PASSWORD", "pin", "SECRET", "TOKEN", "^PW$"):
        with pytest.raises(SeedError):
            parse_seed({"app_id": "t", "probes": [{"field_label": pat, "name": "x", "value": "1"}]})
    ok = parse_seed({"app_id": "t", "probes": [{"field_label": "POLNO|POLICY", "name": "known", "value": "P0000001"}]})
    assert ok.probe_for("POLNO").value == "P0000001"
    assert ok.probe_for("HOLDER") is None


def test_seed_start_recipe_never_commit_capable() -> None:
    parse_seed({"app_id": "t", "start_recipe": ["CLEAR"]})
    with pytest.raises(SeedError):
        parse_seed({"app_id": "t", "start_recipe": ["ENTER"]})


def test_seed_defaults() -> None:
    s = parse_seed({"app_id": "t"})
    assert (s.budgets.max_screens, s.budgets.max_steps, s.budgets.max_depth) == (50, 300, 8)
    assert s.harvest is False
