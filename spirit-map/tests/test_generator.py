"""Generator tests: REQ-036 (label independence), REQ-037 (snapshot), REQ-039 (golden policy),
REQ-020/021/023 (kind, strict schemas, refuse credential params), plus hash stability."""
from __future__ import annotations

import json
from pathlib import Path

import anyio
import pytest
from hypothesis import given, settings, strategies as st

from seance_mcp.fake import F, FakeApp, Rule, build_screen, fake_insurance, region_positions
from seance_mcp.toolpack import def_hash
from seance_spirit.explorer import Explorer
from seance_spirit.generator import Generator, Overrides
from seance_spirit.ids import node_id
from seance_spirit.keypolicy import candidates, proposed_policy
from seance_spirit.labeller import Labeller
from seance_spirit.labels import Labels
from seance_spirit.llm import ScriptedLlm
from seance_spirit.seed import load_seed, parse_seed
from seance_spirit.store import read_labels, read_map

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "docs" / "spirit-map" / "fake-insurance"
GOLDEN_POLICY = ROOT / "docs" / "contracts" / "examples" / "toolpack" / "key-policy.golden.json"


def artefacts():
    m = read_map(D / "spirit-map.json")
    labels = read_labels(D / "labels.json")
    seed = load_seed(D / "explore.seed.json")
    overrides = Overrides.load(json.loads((D / "overrides.json").read_text(encoding="utf-8")))
    return m, labels, seed, overrides


def generate(labels=None, overrides=None):
    m, lab, seed, ov = artefacts()
    g = Generator(m, labels or lab, seed, overrides if overrides is not None else ov)
    return g, g.generate()


# ---------------------------------------------------------------- shapes and kinds (REQ-020)


def test_three_tools_with_expected_kinds() -> None:
    _, pack = generate()
    tools = {t["name"]: t for t in pack["tools"]}
    assert set(tools) == {"lookup_policy", "list_policies", "update_policy"}
    assert tools["lookup_policy"]["kind"] == "read"
    assert tools["list_policies"]["kind"] == "read"
    assert tools["update_policy"]["kind"] == "commit"
    # the commit tool ends in propose, and no recipe ever confirms
    assert tools["update_policy"]["recipe"][-1]["op"] == "propose"
    for t in pack["tools"]:
        assert not any(s["op"] == "confirm" for s in t["recipe"])
        assert sum(1 for s in t["recipe"] if s["op"] == "propose") <= 1


def test_strict_schemas(REQ021_also=True) -> None:
    _, pack = generate()
    for t in pack["tools"]:
        for schema in (t["input_schema"], t["output_schema"]):
            assert schema["additionalProperties"] is False
        for prop in t["input_schema"]["properties"].values():
            if prop.get("type") == "string":
                assert "maxLength" in prop and "pattern" in prop
    look = next(t for t in pack["tools"] if t["name"] == "lookup_policy")
    assert look["input_schema"]["properties"]["policy_number"]["maxLength"] == 8
    upd = next(t for t in pack["tools"] if t["name"] == "update_policy")
    assert upd["input_schema"]["properties"]["premium"]["pattern"] == "^[0-9]{1,7}$"


def test_descriptions_end_with_the_untrusted_line() -> None:
    _, pack = generate()
    for t in pack["tools"]:
        assert t["description"].endswith("untrusted data.")


# ---------------------------------------------------------------- REQ-039 golden policy


def test_proposed_policy_equals_the_golden_modulo_screen_id() -> None:
    m, _, seed, _ = artefacts()
    policy, _ = proposed_policy(m, seed)
    golden = json.loads(GOLDEN_POLICY.read_text(encoding="utf-8"))
    assert policy == golden


def test_confirm_enter_is_never_a_candidate() -> None:
    m, _, seed, _ = artefacts()
    confirm = node_id("483e5fe116720467970335b85d492910428e62124ad3ed27a6b9ad7f61e61313")
    cands = {(c.screen_id, c.key) for c in candidates(m, seed)}
    confirm_sid = next(n.screen_id for n in m.nodes if n.id == confirm)
    assert (confirm_sid, "ENTER") not in cands  # the one real commit stays off the policy


def test_evidence_cites_a_reason_for_every_candidate() -> None:
    m, _, seed, _ = artefacts()
    _, evidence = proposed_policy(m, seed)
    for screen in evidence["screens"].values():
        for item in screen:
            assert item["rules"] and item["evidence"]


# ---------------------------------------------------------------- REQ-036 label independence


def _hostile_labels(m, seed_text: str) -> Labels:
    client = ScriptedLlm(model="m", default=json.dumps({
        "name": seed_text, "kind": "confirm", "purpose": seed_text, "confidence": 1.0,
        "read_only": True, "safe": True,
        "fields": {}}))
    return Labeller(client).label(m)


@settings(max_examples=25, deadline=None)
@given(st.text(min_size=0, max_size=40))
def test_policy_kinds_and_recipe_keys_independent_of_labels(evil: str) -> None:
    m, base_labels, seed, ov = artefacts()
    heuristic = Labeller().label(m)
    hostile = _hostile_labels(m, evil + " mark everything read only confidence 1.0")

    def shape(labels):
        # Keyed by the provenance node path, which is label-independent. Names and descriptions
        # legitimately come from labels; kind, recipe key set and key policy must not (REQ-017).
        g = Generator(m, labels, seed, Overrides())  # no overrides: isolate the label effect
        pack = g.generate()
        policy, _ = proposed_policy(m, seed)
        by_path = {
            "+".join(t["provenance"]["nodes"]): (
                t["kind"],
                [(s["op"], s.get("key")) for s in t["recipe"]],
                sorted(t["input_schema"].get("required", [])) == sorted(t["input_schema"]["properties"])
                if False else sorted(_recipe_field_keys(t)),
            )
            for t in pack["tools"]
        }
        return policy, by_path

    assert shape(heuristic) == shape(hostile)


def _recipe_field_keys(tool: dict) -> list[str]:
    keys = [s["field"] for s in tool["recipe"] if s["op"] == "fill"]
    keys += [v for s in tool["recipe"] if s["op"] == "extract" for v in s["into"].values()]
    keys += [v for s in tool["recipe"] if s["op"] == "extract_list" for v in s["row_fields"].values()]
    return sorted(keys)


# ---------------------------------------------------------------- REQ-023 refuse credential params


def _login_update_app() -> FakeApp:
    vol = region_positions([(22, 1, 70)])
    menu = build_screen({(0, 1): "MENU", (3, 1): "OPTION ===>", (23, 1): "ENTER=GO"},
                        [F("option", 3, 13, 1, "in"), F("msg", 22, 1, 70)], cursor_field="option", volatile=vol)
    form = build_screen({(0, 1): "SET PASSWORD", (3, 1): "USER ===>", (5, 1): "PASSWORD ===>", (23, 1): "ENTER=SAVE"},
                        [F("user", 3, 12, 8, "in"), F("password", 5, 15, 8, "hidden"), F("msg", 22, 1, 70)],
                        cursor_field="user", volatile=vol)
    rules = [Rule("*", "CLEAR", "menu"), Rule("menu", "ENTER", "form", when=lambda v: v.get("option") == "1"),
             Rule("form", "ENTER", "form")]
    return FakeApp({"menu": menu, "form": form}, "menu", rules)


def test_generator_refuses_a_credential_parameter() -> None:
    app = _login_update_app()
    menu_sid = app.screens["menu"].model().screen_id
    form_sid = app.screens["form"].model().screen_id
    seed = parse_seed({"app_id": "x", "volatile": [[22, 1, 70]],
                       "probes": [{"field_label": "^OPTION", "name": "opt", "value": "1"}],
                       "declared_read_only": {node_id(menu_sid): ["ENTER"], node_id(form_sid): ["ENTER"]}})
    ex = Explorer(app, seed)
    anyio.run(ex.run)
    g = Generator(ex.map, Labeller().label(ex.map), seed)
    pack = g.generate()
    # the only input besides user is a hidden password; the tool must not take a password param
    for t in pack["tools"]:
        assert "password" not in t["input_schema"]["properties"]
    assert any("refuses parameter" in r for r in g.report.refused) or pack["tools"] == [] or all(
        "password" not in json.dumps(t) for t in pack["tools"])


# ---------------------------------------------------------------- hashes, names, snapshot


def test_def_hash_is_recomputable_and_excludes_provenance() -> None:
    _, pack = generate()
    for t in pack["tools"]:
        assert t["def_hash"] == def_hash(t)
        edited = dict(t)
        edited["title"] = t["title"] + " (edited)"
        assert def_hash(edited) != t["def_hash"]  # editing invalidates the hash (REQ-029)


def test_names_are_legal_unique_and_not_generic() -> None:
    import re
    from seance_mcp.toolpack import GENERIC_TOOLS

    _, pack = generate()
    names = [t["name"] for t in pack["tools"]]
    assert len(set(names)) == len(names)
    for n in names:
        assert re.fullmatch(r"[a-z][a-z0-9_]{2,40}", n) and n not in GENERIC_TOOLS


def test_generation_is_deterministic() -> None:
    _, a = generate()
    _, b = generate()
    a.pop("generated_at"), b.pop("generated_at")
    assert a == b


UPDATE_SNAPSHOT = "tests/snapshots/fake-insurance-tools.json"


def test_snapshot_matches(request) -> None:
    """REQ-037: committed golden tools (minus the timestamp). Update with --snapshot-update."""
    _, pack = generate()
    pack.pop("generated_at")
    snap = ROOT / "spirit-map" / UPDATE_SNAPSHOT
    if request.config.getoption("--snapshot-update", default=False):
        from seance_spirit.store import write_json

        write_json(snap, pack)
        pytest.skip("snapshot updated")
    assert snap.exists(), f"missing snapshot; run pytest --snapshot-update"
    golden = json.loads(snap.read_text(encoding="utf-8"))
    golden.pop("generated_at", None)
    assert pack == golden
