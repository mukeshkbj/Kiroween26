"""Review tests (task 6.5/6.6): approvals carry the current def_hash; editing a tool un-approves
it (the hash no longer matches); promote_policy is the only writer of key-policy.json."""
from __future__ import annotations

import json
from pathlib import Path

from seance_mcp.toolpack import load_approvals, load_toolpack
from seance_spirit.review import approve_tools, promote_policy, summarise
from seance_spirit.store import write_json

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "docs" / "spirit-map" / "fake-insurance"


def _copy_pack(tmp_path) -> Path:
    pack = json.loads((D / "tools.json").read_text(encoding="utf-8"))
    p = tmp_path / "tools.json"
    write_json(p, pack)
    return p


def test_approve_tools_records_name_hash_who_when(tmp_path) -> None:
    pack_p = _copy_pack(tmp_path)
    approvals = tmp_path / "tool-approvals.json"
    names = approve_tools(pack_p, approvals, "alice", now="2026-11-15T12:00:00.000Z")
    assert set(names) == {"lookup_policy", "list_policies", "update_policy"}
    raw = json.loads(approvals.read_text(encoding="utf-8"))["approved"]
    pack = json.loads(pack_p.read_text(encoding="utf-8"))
    hashes = {t["name"]: t["def_hash"] for t in pack["tools"]}
    for a in raw:
        assert a["approved_by"] == "alice" and a["approved_at"] == "2026-11-15T12:00:00.000Z"
        assert a["def_hash"] == hashes[a["name"]]


def test_editing_a_tool_invalidates_its_approval(tmp_path) -> None:
    pack_p = _copy_pack(tmp_path)
    approvals = tmp_path / "tool-approvals.json"
    approve_tools(pack_p, approvals, "alice")
    # a human edits the pack (e.g. widens a maxLength) WITHOUT re-running the generator's hash
    pack = json.loads(pack_p.read_text(encoding="utf-8"))
    look = next(t for t in pack["tools"] if t["name"] == "lookup_policy")
    look["description"] = look["description"] + " (tampered)"
    write_json(pack_p, pack)
    # mcp-server recomputes def_hash and finds it no longer matches the stored approval
    loaded = load_toolpack(pack_p, approvals, allow_unreviewed=False)
    registered = {t["name"] for t in loaded.approved}
    skipped = dict(loaded.skipped)
    assert "lookup_policy" in skipped and skipped["lookup_policy"] == "hash_mismatch"
    assert "update_policy" in registered  # untouched tools still register


def test_approving_a_subset(tmp_path) -> None:
    pack_p = _copy_pack(tmp_path)
    approvals = tmp_path / "tool-approvals.json"
    names = approve_tools(pack_p, approvals, "bob", names=["lookup_policy"])
    assert names == ["lookup_policy"]
    assert set(load_approvals(approvals)) == {"lookup_policy"}


def test_promote_policy_is_the_only_writer_of_key_policy(tmp_path) -> None:
    proposed = tmp_path / "key-policy.proposed.json"
    write_json(proposed, json.loads((D / "key-policy.proposed.json").read_text(encoding="utf-8")))
    policy = tmp_path / "key-policy.json"
    out = promote_policy(proposed, policy, "carol", now="2026-11-15T12:00:00.000Z")
    assert json.loads(policy.read_text(encoding="utf-8")) == out  # exact mcp-server format
    meta = json.loads((tmp_path / "key-policy.approval.json").read_text(encoding="utf-8"))
    assert meta["approved_by"] == "carol" and meta["screens"]
    # the policy file itself carries no approval metadata (it is what KeyPolicy.load reads)
    assert "approved_by" not in policy.read_text(encoding="utf-8")


def test_summary_marks_stale_after_edit(tmp_path) -> None:
    pack_p = _copy_pack(tmp_path)
    approvals = tmp_path / "tool-approvals.json"
    approve_tools(pack_p, approvals, "alice")
    assert "approved" in summarise(pack_p, approvals)
    pack = json.loads(pack_p.read_text(encoding="utf-8"))
    pack["tools"][0]["title"] += " x"
    write_json(pack_p, pack)
    assert "STALE" in summarise(pack_p, approvals)
