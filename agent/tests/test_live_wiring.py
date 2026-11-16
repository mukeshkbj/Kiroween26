"""A's request-d-seance-insurance-wiring, item 1: per-app volatile regions for live apps.

Without them every live app got the TK4- clock mask, whose (0,11,6) span cuts the title
"SEANCE INSURANCE". So the live COBOL app's screen ids never matched the map, B's approved key
policy or B's tools. A measured it live: menu ``cf68541fac`` instead of the fake's ``ba02cc6364``.

These tests rebuild that proof offline: the same menu text parsed with the regions the live
runtime would use. Nothing here connects to anything; ``build_runtime`` only constructs the port.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from seance_bridge import Buffer
from seance_mcp.config import TK4_CLOCK_REGIONS
from seance_mcp.fake import DEMO_VOLATILE_REGIONS, PARSER, fake_insurance, region_positions

from seance_agent.apps import AppRegistry, build_runtime, pack_volatile_regions
from seance_agent.config import Settings

from ._harness import REPO_ROOT

LIVE_ENV = {"GSS_LIVE_OK": "1", "TN3270_HOST": "127.0.0.1", "TN3270_PORT": "3270", "STANDIN_PORT": "3271"}
FAKE_ART = REPO_ROOT / "docs" / "spirit-map" / "fake-insurance"


def _menu_id(regions) -> str:
    """The fake menu's text, parsed the way the live bridge would with these regions."""
    spec = fake_insurance().screens["menu"]
    buf = Buffer(text="".join(spec.text), field_starts=spec.starts, cursor_row=spec.cursor[0], cursor_col=spec.cursor[1])
    return PARSER.parse(buf, region_positions(regions)).screen_id


def _registry_with_seance_insurance(tmp_path: Path, *, edit_pack=None) -> AppRegistry:
    """A registry whose seance-insurance artefacts are B's fake-insurance pack and map (A: identical
    to the live map), in a temp root, so the test does not depend on what this branch has promoted."""
    art = tmp_path / "docs" / "spirit-map" / "seance-insurance"
    art.mkdir(parents=True)
    for name in ("tools.json", "tool-approvals.json", "key-policy.json", "spirit-map.json"):
        if (FAKE_ART / name).is_file():
            shutil.copy(FAKE_ART / name, art / name)
    if edit_pack is not None:
        pack = json.loads((art / "tools.json").read_text(encoding="utf-8"))
        edit_pack(pack)
        (art / "tools.json").write_text(json.dumps(pack), encoding="utf-8")
    return AppRegistry(AppRegistry.load().all(), root=tmp_path)


def _runtime(reg: AppRegistry, app_id: str, tmp_path: Path):
    return build_runtime(reg.get(app_id), reg, Settings(), env=LIVE_ENV, audit_path=tmp_path / f"{app_id}.jsonl")


def test_the_problem_is_real() -> None:
    """A's live finding, reproduced: the TK4- default mask changes the menu's id."""
    fake_menu = fake_insurance().screens["menu"].model().screen_id
    assert _menu_id(DEMO_VOLATILE_REGIONS) == fake_menu
    assert _menu_id(TK4_CLOCK_REGIONS) != fake_menu


def test_seance_insurance_live_runtime_uses_the_packs_regions(tmp_path: Path) -> None:
    rt = _runtime(_registry_with_seance_insurance(tmp_path), "seance-insurance", tmp_path)
    regions = rt.service.settings.volatile_regions
    assert rt.volatile_source == "pack"
    assert set(regions) == set(DEMO_VOLATILE_REGIONS)
    # The live menu therefore gets the fake's (and the approved policy's) screen id.
    assert _menu_id(regions) == fake_insurance().screens["menu"].model().screen_id
    assert rt.service.settings.port == 3271  # item 2 stays right


def test_tk4_builtins_keeps_the_clock_mask(tmp_path: Path) -> None:
    rt = _runtime(_registry_with_seance_insurance(tmp_path), "tk4-builtins", tmp_path)  # no pack for tk4
    assert rt.volatile_source == "default"
    assert tuple(rt.service.settings.volatile_regions) == tuple(TK4_CLOCK_REGIONS)


@pytest.mark.parametrize("edit,source", [
    # a pack that masks more than its map recorded (here: the title row) is not trusted
    (lambda p: p.update(volatile_regions=p["volatile_regions"] + ";0,1,40"), "default:pack-map-mismatch"),
    # a pack that masks less is not trusted either: its ids would not match the approved policy
    (lambda p: p.update(volatile_regions=";".join(p["volatile_regions"].split(";")[1:])), "default:pack-map-mismatch"),
    (lambda p: p.update(volatile_regions="0,1"), "default:bad-pack-regions"),
])
def test_untrustworthy_pack_regions_fail_closed(tmp_path: Path, edit, source) -> None:
    rt = _runtime(_registry_with_seance_insurance(tmp_path, edit_pack=edit), "seance-insurance", tmp_path)
    assert rt.volatile_source == source
    assert tuple(rt.service.settings.volatile_regions) == tuple(TK4_CLOCK_REGIONS)
    # Fail closed: the live ids no longer match the approved key policy, so its read-only
    # overrides cannot apply and every commit-capable key needs a person.
    policy = json.loads((FAKE_ART / "key-policy.json").read_text(encoding="utf-8"))
    assert _menu_id(rt.service.settings.volatile_regions) not in policy


def test_the_fake_app_is_unaffected(tmp_path: Path) -> None:
    reg = AppRegistry.load()
    rt = build_runtime(reg.get("fake-insurance"), reg, Settings(), env={}, audit_path=tmp_path / "f.jsonl")
    assert rt.volatile_source == "fake"


def test_repo_seance_insurance_pack_when_promoted(tmp_path: Path) -> None:
    """On branches that carry B's promoted seance-insurance map (integration), the real artefacts
    must pass the same check. Skipped where they are not there yet."""
    art = REPO_ROOT / "docs" / "spirit-map" / "seance-insurance"
    if not (art / "tools.json").is_file():
        pytest.skip("seance-insurance pack not on this branch yet (B's promotion is on integration)")
    regions, source = pack_volatile_regions(art)
    assert source == "pack" and regions is not None
    assert _menu_id(regions) == fake_insurance().screens["menu"].model().screen_id
