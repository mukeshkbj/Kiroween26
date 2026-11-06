"""FakeApp / fake_insurance (docs/contracts.md sections 2.2 and 10)."""
from __future__ import annotations

import json
from pathlib import Path

import anyio
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from seance_bridge import Key
from seance_mcp.fake import (
    SEED_POLICIES,
    CaptureError,
    FakeApp,
    build_screen,
    F,
    fake_insurance,
    region_positions,
    DEMO_VOLATILE_REGIONS,
)

from harness import Session, human, make_rig

SENTINEL = "@"


def run(coro):
    async def go():
        return await coro

    return anyio.run(go)


def press(app: FakeApp, key: str):
    return run(app.press(Key[key]))


def fill(app: FakeApp, name: str, value: str):
    spec = app.screens[app.current]
    return run(app.fill_field(spec.names[name], value))


def test_five_distinct_screens_with_real_screen_ids():
    app = fake_insurance()
    ids = {name: spec.model().screen_id for name, spec in app.screens.items()}
    assert set(ids) == {"menu", "enquiry", "list", "update", "confirm"}
    assert len(set(ids.values())) == 5
    assert all(len(i) == 64 for i in ids.values())


def test_lookup_returns_policy_and_screen_id_is_data_independent():
    app = fake_insurance()
    fill(app, "option", "1")
    press(app, "ENTER")
    assert app.current == "enquiry"
    before = app.screens["enquiry"].model().screen_id
    fill(app, "polno", "P0000003")
    press(app, "ENTER")
    assert app.screens["enquiry"].get("holder") == "A. ROSE"
    assert app.screens["enquiry"].get("premium") == "250.00"
    id_a = app.screens["enquiry"].model().screen_id
    fill(app, "polno", "P0000001")
    press(app, "ENTER")
    assert app.screens["enquiry"].get("holder") == "J. MARLOWE"
    assert before == id_a == app.screens["enquiry"].model().screen_id
    fill(app, "polno", "NOPE")
    press(app, "ENTER")
    assert app.screens["enquiry"].get("msg") == "POLICY NOT FOUND"


def test_only_enter_on_confirm_changes_data():
    app = fake_insurance()
    fill(app, "option", "3"); press(app, "ENTER")
    fill(app, "polno", "P0000003"); fill(app, "status", "L"); fill(app, "premium", "300")
    press(app, "ENTER")
    assert app.current == "confirm" and not app.dirty
    assert app.policies["P0000003"]["status"] == "ACTIVE"
    press(app, "PF3")  # cancel
    assert app.current == "menu" and not app.dirty and app.policies["P0000003"]["premium"] == "250.00"
    fill(app, "option", "3"); press(app, "ENTER")
    fill(app, "polno", "P0000003"); fill(app, "premium", "300"); press(app, "ENTER")
    press(app, "ENTER")  # the commit
    assert app.dirty and app.mutations == [("confirm", "Enter")]
    assert app.policies["P0000003"]["premium"] == "300.00"
    app.reset()
    assert not app.dirty and app.policies == SEED_POLICIES and app.pressed == []


def test_list_shows_eight_seed_rows_and_clear_goes_home():
    app = fake_insurance()
    fill(app, "option", "2"); press(app, "ENTER")
    assert app.current == "list" and app.screens["list"].get("row7_polno") == "P0000008"
    press(app, "CLEAR")
    assert app.current == "menu"


def test_hidden_fields_never_expose_values():
    spec = build_screen({(0, 1): "T"}, [F("pin", 3, 10, 4, "hidden_num"), F("name", 4, 10, 6, "in")])
    spec.put("pin", "1234"); spec.put("name", "BOB")
    m = spec.model()
    assert "1234" not in "".join(m.rows) and all(f.value is None for f in m.fields if f.hidden)
    assert spec.get("pin") == ""  # hidden reads back as empty, never the value


def test_full_service_path_fake_app_sees_no_commit_key_until_confirmed():
    app = fake_insurance()
    rig = make_rig(port=app, allow_commit=True)
    s = Session(rig, elicitation_callback=human(rig))
    s.ok("connect")
    # drive the app to the confirm screen with direct port calls (test setup), then use the tools
    fill(app, "option", "3"); press(app, "ENTER")
    fill(app, "polno", "P0000002"); fill(app, "premium", "400"); press(app, "ENTER")
    app.calls.clear()
    pending = s.ok("press_key", key="ENTER")
    assert pending["status"] == "pending" and app.pressed == [] and not app.dirty
    s.ok("confirm_action", action_id=pending["action"]["action_id"])
    assert app.pressed == ["Enter"] and app.dirty


def test_capture_roundtrip(tmp_path):
    app = fake_insurance()
    scr = {}
    for name in ("menu", "enquiry"):
        spec = app.screens[name]
        m = spec.model()
        scr[name] = {
            "name": name,
            "volatile": [list(r) for r in DEMO_VOLATILE_REGIONS],
            "screen": {"trust": "untrusted-screen-data", "screen_id": m.screen_id, "cursor": list(m.cursor),
                       "rows": list(m.rows),
                       "fields": [{"index": f.index, "row": f.row, "col": f.col, "length": f.length,
                                   "protected": f.protected, "numeric": f.numeric, "hidden": f.hidden,
                                   "intensified": f.intensified, "label": "", "value": f.value} for f in m.fields]},
        }
    cap = {"schema": "gss.capture/1", "app_id": "t", "captured_at": "2026-11-04T00:00:00Z",
           "screens": list(scr.values()),
           "transitions": [{"from": "menu", "key": "PF3", "fills": [], "to": "enquiry"}]}
    path = tmp_path / "c.json"
    path.write_text(json.dumps(cap), encoding="utf-8")
    replay = FakeApp.from_capture(path)
    assert run(replay.read_screen()).screen_id == scr["menu"]["screen"]["screen_id"]
    assert run(replay.press(Key.PF3)).screen_id == scr["enquiry"]["screen"]["screen_id"]
    cap["screens"][0]["screen"]["screen_id"] = "0" * 64
    path.write_text(json.dumps(cap), encoding="utf-8")
    with pytest.raises(CaptureError):
        FakeApp.from_capture(path)


KEYS = [k for k in ("ENTER", "CLEAR", "PF3", "PF7", "PF8", "PA1", "PF12")]


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(st.tuples(st.sampled_from(KEYS + ["fill_option", "fill_polno", "fill_status", "fill_premium"]),
                          st.text(alphabet="0123ALCP", max_size=8)), max_size=40))
def test_random_walk_invariants(steps):
    app = fake_insurance()
    seen: dict[str, str] = {}
    for action, text in steps:
        if action.startswith("fill_"):
            name = action[5:]
            spec = app.screens[app.current]
            if name in spec.names and spec.kinds[name] in ("in", "num"):
                try:
                    run(app.fill_field(spec.names[name], text))
                except Exception:
                    pass
        else:
            press(app, action)
        assert app.current in app.screens
        sid = app.screens[app.current].model().screen_id
        assert seen.setdefault(app.current, sid) == sid  # screen name -> screen_id is a function
    # data changes only through the single mutating rule
    assert (not app.dirty) or all(m == ("confirm", "Enter") for m in app.mutations)
    assert len(set(seen.values())) == len(seen)


def test_region_positions_clip():
    assert region_positions([(23, 78, 10)]) <= set(range(1920))


# ---------------------------------------------------------------- real captures (Agent A, 2026-11-05)

CAPTURES = sorted((Path(__file__).resolve().parents[2] / "legacy" / "captures").glob("*/capture.json"))


@pytest.mark.skipif(not CAPTURES, reason="no captures in this checkout")
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.parent.name)
def test_every_real_capture_rebuilds_with_the_recorded_screen_ids(path):
    """Includes tk4-builtins, whose welcome screen has a zero-length field in the last cell."""
    app = FakeApp.from_capture(path)  # raises CaptureError on any screen_id mismatch
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert list(app.screens) == [s["name"] for s in raw["screens"]]
    for s in raw["screens"]:
        assert app.screens[s["name"]].model().screen_id == s["screen"]["screen_id"]
        assert all(f.value is None for f in app.screens[s["name"]].model().fields if f.hidden)


def _screen_out_dict(spec):
    from seance_mcp.screens import screen_out

    return screen_out(spec.model()).model_dump(mode="json")


def test_capture_with_a_field_in_the_last_cell_wraps_to_offset_1919(tmp_path):
    """The parser reports an attribute in the last cell as a zero-length field at (0, 0)."""
    from seance_bridge import BUFFER_SIZE, FieldAttrs
    from seance_mcp.fake import P, ScreenSpec

    spec = ScreenSpec({10: "HELLO"}, [(8, P), (BUFFER_SIZE - 1, FieldAttrs(protected=True))])
    so = _screen_out_dict(spec)
    assert any(f["row"] == 0 and f["col"] == 0 and f["length"] == 0 for f in so["fields"])
    cap = {"schema": "gss.capture/1", "app_id": "t", "captured_at": "2026-11-06T00:00:00.000Z",
           "screens": [{"name": "s", "screen": so, "volatile": []}], "transitions": []}
    p = tmp_path / "c.json"
    p.write_text(json.dumps(cap), encoding="utf-8")
    app = FakeApp.from_capture(p)
    assert app.screens["s"].model().screen_id == so["screen_id"]
    assert BUFFER_SIZE - 1 in [fs.pos for fs in app.screens["s"].starts]


def test_capture_does_not_invent_a_field_at_the_top_left(tmp_path):
    """A screen whose first field is not at the top-left must keep its recorded structure."""
    from seance_bridge import FieldAttrs
    from seance_mcp.fake import ScreenSpec

    spec = ScreenSpec({0: "TEXT BEFORE ANY FIELD"}, [(30, FieldAttrs(protected=False))])
    so = _screen_out_dict(spec)
    cap = {"schema": "gss.capture/1", "app_id": "t", "captured_at": "2026-11-06T00:00:00.000Z",
           "screens": [{"name": "s", "screen": so, "volatile": []}], "transitions": []}
    p = tmp_path / "c.json"
    p.write_text(json.dumps(cap), encoding="utf-8")
    app = FakeApp.from_capture(p)
    assert [fs.pos for fs in app.screens["s"].starts] == [30]
    assert app.screens["s"].model().screen_id == so["screen_id"]


def test_legacy_volatile_regions_file_equals_the_fakes_demo_regions():
    """docs/contracts.md 10.4: the real app's VOLATILE_REGIONS must equal DEMO_VOLATILE_REGIONS."""
    from seance_mcp.config import parse_regions
    from seance_mcp.fake import DEMO_VOLATILE_REGIONS

    f = Path(__file__).resolve().parents[2] / "legacy" / "volatile-regions.txt"
    if not f.exists():
        pytest.skip("legacy/volatile-regions.txt not in this checkout")
    spec = [ln for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    assert len(spec) == 1
    assert set(parse_regions(spec[0])) == set(DEMO_VOLATILE_REGIONS)
