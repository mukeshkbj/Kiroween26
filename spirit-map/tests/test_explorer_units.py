import ast
import json
from pathlib import Path

import anyio
import pytest

from seance_bridge import SessionError
from seance_mcp.fake import F, FakeApp, Rule, build_screen, fake_insurance, region_positions
from seance_spirit.explorer import Explorer
from seance_spirit.ids import node_id
from seance_spirit.seed import load_seed, parse_seed
from seance_spirit.store import read_map

ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = ROOT / "docs" / "spirit-map" / "fake-insurance" / "explore.seed.json"
MENU = node_id("ba02cc6364b6cd8728535a7085dc51abac5bd83c32a02163d91634aa6bb97271")
CONFIRM = node_id("483e5fe116720467970335b85d492910428e62124ad3ed27a6b9ad7f61e61313")


def run(ex: Explorer):
    return anyio.run(ex.run)


# ---------------------------------------------------------------- fake-insurance (task 4.4)


def test_fake_insurance_yields_the_five_screen_map() -> None:
    app = fake_insurance()
    ex = Explorer(app, load_seed(SEED_PATH))
    rep = run(ex)
    assert rep.status == "completed" and rep.reason is None
    assert len(ex.map.nodes) == 5
    assert ex.map.home == MENU
    assert {n.screen_id[:10] for n in ex.map.nodes} == {"ba02cc6364", "419888f22d", "c5d11dedae", "96fa848aaa", "483e5fe116"}
    # the only thing not done: ENTER on the confirm screen
    assert [(f.from_, f.key, f.reason) for f in ex.map.frontier] == [(CONFIRM, "ENTER", "denied_commit")]
    # nothing changed and no key was sent on confirm that could commit
    assert app.dirty is False and app.mutations == []
    assert app.policies["P0000001"]["status"] == "ACTIVE" and app.policies["P0000001"]["premium"] == "180.00"


def test_fake_insurance_map_has_the_expected_edges_and_field_keys() -> None:
    ex = Explorer(fake_insurance(), load_seed(SEED_PATH))
    run(ex)
    m = ex.map
    menu_out = {(e.key, tuple(f.probe for f in e.fills)) for e in m.edges_from(MENU)}
    assert ("ENTER", ("menu_policy_enquiry",)) in menu_out
    assert ("ENTER", ("menu_policy_list",)) in menu_out
    assert ("ENTER", ("menu_policy_update",)) in menu_out
    assert ("PF3", ()) in menu_out
    keys = {n.id: [f.key for f in n.fields if not f.output] for n in m.nodes}
    assert keys[MENU] == ["option"]
    enq = next(n for n in m.nodes if n.screen_id.startswith("419888f22d"))
    assert [f.key for f in enq.fields if f.output][:4] == ["holder", "status", "premium", "updated"]
    upd = next(n for n in m.nodes if n.screen_id.startswith("96fa848aaa"))
    assert [f.key for f in upd.fields if not f.output] == ["polno", "status", "premium"]
    # commit edge to confirm exists (update ENTER is declared read-only in the seed)
    assert any(e.to == CONFIRM and e.key == "ENTER" for e in m.edges)
    assert all(e.read_only for e in m.edges)


def test_the_map_holds_no_data_values() -> None:
    ex = Explorer(fake_insurance(), load_seed(SEED_PATH))
    run(ex)
    text = json.dumps(ex.map.model_dump(by_alias=True))
    for value in ("P0000001", "J. MARLOWE", "180.00", "ACTIVE", '"300"', '"L"'):
        assert value not in text


def test_exploration_is_deterministic() -> None:
    from seance_spirit.store import dumps, map_to_obj

    a, b = Explorer(fake_insurance(), load_seed(SEED_PATH)), Explorer(fake_insurance(), load_seed(SEED_PATH))
    run(a), run(b)
    assert dumps(map_to_obj(a.map)) == dumps(map_to_obj(b.map))


def test_map_is_written_atomically_and_reads_back(tmp_path) -> None:
    out = tmp_path / "spirit-map.json"
    ex = Explorer(fake_insurance(), load_seed(SEED_PATH), out_path=out)
    run(ex)
    assert read_map(out) == ex.map.canonical()
    assert list(tmp_path.glob("*.tmp")) == []


# ---------------------------------------------------------------- halting (REQ-005, REQ-006)


def test_ambiguous_ack_halts_at_once_and_never_resends() -> None:
    app = fake_insurance()
    app.timeout_keys = frozenset({"Clear"})
    ex = Explorer(app, load_seed(SEED_PATH))
    rep = run(ex)
    assert rep.status == "halted" and rep.reason == "ambiguous_ack"
    assert [c[1] for c in app.calls if c[0] == "press"].count("Clear") == 1  # sent once, not retried
    last = app.calls[-1]
    assert last == ("press", "Clear")  # nothing else was sent after the timeout
    assert ex.map.run.status == "halted"


def test_session_loss_halts() -> None:
    app = fake_insurance()
    ex = Explorer(app, load_seed(SEED_PATH))
    app.fail_next = SessionError("gone")
    rep = run(ex)
    assert rep.status == "halted" and rep.reason == "session_lost"
    assert app.pressed == []


def test_unexpected_pending_halts_instead_of_confirming(monkeypatch) -> None:
    """If a policy bug lets a commit key through candidates, the gate holds it and the run stops."""
    from seance_spirit import explorer as ex_mod
    from .test_explorer_properties import _mutant_policy

    monkeypatch.setattr(ex_mod, "_OTHER_KEYS", ex_mod._OTHER_KEYS + ex_mod._COMMIT_ORDER)
    app = fake_insurance()
    seed = parse_seed({"app_id": "fake-insurance", "volatile": [], "budgets": {"fanout": 50}})  # nothing declared
    ex = Explorer(app, seed, policy_factory=_mutant_policy("commit check removed"))
    rep = run(ex)
    assert rep.status == "halted" and rep.reason == "unexpected_pending"
    from seance_bridge import COMMIT_CAPABLE

    assert not {k for k in app.pressed if k in {c.value for c in COMMIT_CAPABLE}}
    assert app.dirty is False


def _unstable_app() -> FakeApp:
    """PF13 'back' from b goes home the first time and somewhere else afterwards."""
    def screen(title: str):
        return build_screen({(0, 1): title, (23, 1): "PF13=BACK"}, [F("msg", 22, 1, 70)],
                            volatile=region_positions([(22, 1, 70)]))

    def back(a: FakeApp, v) -> None:
        a.state["n"] = a.state.get("n", 0) + 1
        a.goto("a" if a.state["n"] == 1 else "c")

    rules = [
        Rule("a", "PA1", "b"), Rule("b", "PF13", effect=back), Rule("b", "PA2", "b"),
        Rule("c", "PF13", "d"), Rule("d", "PF13", "c"), Rule("c", "PA1", "b"), Rule("d", "PA1", "b"),
    ]
    return FakeApp({k: screen(k.upper() + " SCREEN") for k in "abcd"}, "a", rules)


def test_a_route_that_lands_wrongly_ends_lost_or_completes_without_unsafe_keys() -> None:
    app = _unstable_app()
    seed = parse_seed({"app_id": "x", "volatile": [[22, 1, 70]], "budgets": {"fanout": 50}})
    rep = run(Explorer(app, seed))
    assert rep.status in ("halted", "completed")
    if rep.status == "halted":
        assert rep.reason == "lost"
    assert app.dirty is False


# ---------------------------------------------------------------- budgets (REQ-007)


@pytest.mark.parametrize("budget,reason", [({"max_steps": 6}, "steps_or_time"), ({"max_screens": 2}, "screens")])
def test_budgets_end_a_run_normally(budget, reason) -> None:
    base = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    base["budgets"].update(budget)
    ex = Explorer(fake_insurance(), parse_seed(base))
    rep = run(ex)
    assert rep.status == "budget" and rep.reason == reason
    if "max_steps" in budget:
        assert rep.steps <= 6
    else:
        assert len(ex.map.nodes) <= 3
    assert ex.map.frontier  # what was left over is recorded


def test_max_depth_limits_expansion() -> None:
    base = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    base["budgets"]["max_depth"] = 0  # expand home only: its children are found but not expanded
    ex = Explorer(fake_insurance(), parse_seed(base))
    run(ex)
    assert len(ex.map.nodes) == 4
    assert {f.from_ for f in ex.map.frontier if f.reason == "budget"} == {n.id for n in ex.map.nodes} - {MENU}
    base["budgets"]["max_depth"] = 1  # one more level: the confirm screen is found but not expanded
    ex = Explorer(fake_insurance(), parse_seed(base))
    run(ex)
    assert len(ex.map.nodes) == 5
    assert (CONFIRM, "ENTER", "budget") in {(f.from_, f.key, f.reason) for f in ex.map.frontier}

# ---------------------------------------------------------------- start, attach, recipe


def test_start_recipe_is_pressed_first() -> None:
    base = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    base["start_recipe"] = ["CLEAR"]
    app = fake_insurance()
    run(Explorer(app, parse_seed(base)))
    assert app.pressed[0] == "Clear"


def test_attach_mode_does_not_connect() -> None:
    app = fake_insurance()
    anyio.run(app.connect, "localhost", 3270)
    ex = Explorer(app, load_seed(SEED_PATH), attach=True)
    rep = run(ex)
    assert rep.status == "completed"
    assert [c for c in app.calls if c[0] == "connect"] == [("connect", "localhost", 3270)]


def test_attach_mode_without_a_session_halts() -> None:
    rep = run(Explorer(fake_insurance(), load_seed(SEED_PATH), attach=True))
    assert rep.status == "halted" and rep.reason == "not_connected"


# ---------------------------------------------------------------- hidden values and harvest


SENTINEL = "@@HIDDEN-SENTINEL-91@@"


def _login_app() -> FakeApp:
    vol = region_positions([(22, 1, 70)])
    login = build_screen(
        {(0, 1): "LOGIN", (3, 1): "USER ===>", (5, 1): "PASSWORD ===>", (7, 1): "PIN ===>"},
        [F("user", 3, 12, 8, "in"), F("password", 5, 15, 8, "hidden"), F("pin", 7, 12, 4, "in"), F("msg", 22, 1, 70)],
        volatile=vol)
    login.put("password", SENTINEL[:8])
    login.text[7 * 80 + 12:7 * 80 + 16] = list("4321")  # a visible PIN typed earlier by a human
    login.put("user", "SEANCE")
    return FakeApp({"login": login}, "login", [Rule("login", "ENTER", effect=lambda a, v: None)])


def test_hidden_and_credential_values_never_reach_the_map(tmp_path) -> None:
    app = _login_app()
    seed = parse_seed({
        "app_id": "x", "volatile": [[22, 1, 70]],
        "probes": [{"field_label": "^USER", "name": "user", "value": "TESTUSER"}],
        "declared_read_only": {node_id(app.screens["login"].model().screen_id): ["ENTER"]},
    })
    out = tmp_path / "m.json"
    ex = Explorer(app, seed, out_path=out, sentinels=[SENTINEL[:8], "4321"])
    rep = run(ex)
    assert rep.status in ("completed", "budget")
    text = out.read_text(encoding="utf-8")
    assert SENTINEL[:8] not in text and "4321" not in text
    # the credential-labelled fields were never typed into
    assert "".join(app.screens["login"].text[5 * 80 + 15:5 * 80 + 23]) == SENTINEL[:8]
    assert "".join(app.screens["login"].text[7 * 80 + 12:7 * 80 + 16]) == "4321"
    assert any(f.reason == "unsafe_field" for f in ex.map.frontier)


def _harvest_app() -> FakeApp:
    vol = region_positions([(5, 13, 6)])
    s0 = build_screen({(0, 1): "FIRST", (5, 1): "CODE:"}, [F("code", 5, 13, 6)], volatile=vol)
    s1 = build_screen({(0, 1): "SECOND", (3, 1): "CODE ===>"}, [F("code", 3, 13, 6, "in"), F("msg", 22, 1, 5)],
                      volatile=vol)
    s0.put("code", "ZX9Q7A")
    return FakeApp({"s0": s0, "s1": s1}, "s0", [Rule("s0", "PA1", "s1"), Rule("s1", "ENTER", "s1"),
                                                  Rule("s1", "CLEAR", "s0")])


def test_harvested_values_are_typed_only_on_declared_keys_and_never_stored() -> None:
    app = _harvest_app()
    sid1 = app.screens["s1"].model().screen_id
    seed = parse_seed({"app_id": "x", "harvest": True, "volatile": [[5, 13, 6]],
                       "declared_read_only": {node_id(sid1): ["ENTER"]}})
    ex = Explorer(app, seed)
    run(ex)
    assert any(f.probe == "harvest" for e in ex.map.edges for f in e.fills)
    assert "ZX9Q7A" not in json.dumps(ex.map.model_dump(by_alias=True))
    # it was typed on s1 (the declared screen), and ENTER was the only commit-capable key sent
    from seance_bridge import COMMIT_CAPABLE

    assert app.pressed.count("Enter") >= 1
    assert {k for k in app.pressed if k in {c.value for c in COMMIT_CAPABLE}} == {"Enter"}


def test_no_harvesting_when_the_seed_does_not_ask_for_it() -> None:
    app = _harvest_app()
    sid1 = app.screens["s1"].model().screen_id
    seed = parse_seed({"app_id": "x", "volatile": [[5, 13, 6]], "declared_read_only": {node_id(sid1): ["ENTER"]}})
    ex = Explorer(app, seed)
    run(ex)
    assert not any(f.probe == "harvest" for e in ex.map.edges for f in e.fills)


# ---------------------------------------------------------------- REQ-002: nothing here can confirm


def test_no_code_in_spirit_map_reaches_the_confirm_path() -> None:
    """Static check: no call to confirm_action / approve_oob / deny_* and no import of the gate's
    authorize, anywhere in the package (the runtime passes through RecipeService, which has none)."""
    forbidden = {"confirm_action", "approve_oob", "deny_oob", "deny_action", "authorize", "decide_oob",
                 "decide_elicit", "decide_client_approval"}
    src = Path(__file__).resolve().parents[1] / "src" / "seance_spirit"
    hits = []
    for path in src.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in forbidden:
                hits.append((path.name, node.attr))
            if isinstance(node, ast.Name) and node.id in forbidden:
                hits.append((path.name, node.id))
            if isinstance(node, ast.ImportFrom):
                hits += [(path.name, a.name) for a in node.names if a.name in forbidden]
    assert hits == []
