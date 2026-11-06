"""Human review: approve tools and promote the proposed key policy. The only writer of
``key-policy.json`` (REQ-025, REQ-031). A person runs these from the CLI.

``review --tools`` writes ``tool-approvals.json`` (name + current ``def_hash`` + who + when).
Editing a tool changes its hash, so the old approval no longer matches and mcp-server skips it.

``review --policy`` copies ``key-policy.proposed.json`` to ``key-policy.json`` and stamps it.
Nothing else ever writes that file; labels and screen text can never widen it (REQ-017, 7.2).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .store import write_json


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def approve_tools(pack_path: Path, approvals_path: Path, who: str, *, names: list[str] | None = None,
                  now: str | None = None) -> list[str]:
    """Record approval of each tool (or the named subset) at its current def_hash."""
    pack = json.loads(Path(pack_path).read_text(encoding="utf-8"))
    stamp = now or _now()
    approved = []
    for tool in pack["tools"]:
        if names is not None and tool["name"] not in names:
            continue
        approved.append({"name": tool["name"], "def_hash": tool["def_hash"],
                         "approved_by": who, "approved_at": stamp})
    write_json(approvals_path, {"approved": sorted(approved, key=lambda a: a["name"])})
    return [a["name"] for a in approved]


def promote_policy(proposed_path: Path, policy_path: Path, who: str, *, now: str | None = None) -> dict:
    """Copy the proposed key policy to the approved file, stamping who/when in a sidecar.

    The policy file keeps the exact format mcp-server loads (``{screen_id: {read_only_keys}}``);
    approval metadata goes to ``<policy>.approval.json`` so the loaded file stays clean."""
    proposed = json.loads(Path(proposed_path).read_text(encoding="utf-8"))
    write_json(policy_path, proposed)
    meta = {"schema": "gss.keypolicy.approval/1", "approved_by": who, "approved_at": now or _now(),
            "screens": sorted(proposed)}
    write_json(Path(policy_path).with_suffix(".approval.json"), meta)
    return proposed


def summarise(pack_path: Path, approvals_path: Path | None) -> str:
    """A diff-friendly summary of a pack and which tools are approved (REQ-031)."""
    pack = json.loads(Path(pack_path).read_text(encoding="utf-8"))
    approved: dict[str, str] = {}
    if approvals_path and Path(approvals_path).exists():
        for a in json.loads(Path(approvals_path).read_text(encoding="utf-8")).get("approved", []):
            approved[a["name"]] = a["def_hash"]
    from seance_mcp.toolpack import def_hash

    lines = [f"app {pack['app_id']}  ({len(pack['tools'])} tools)"]
    for t in pack["tools"]:
        current = def_hash(t)  # recompute, so an edit that forgot to rehash still shows as stale
        mark = "approved" if approved.get(t["name"]) == current else (
            "STALE" if t["name"] in approved else "unreviewed")
        draft = " draft" if t.get("provenance", {}).get("needs_review") else ""
        lines.append(f"  [{mark}]{draft} {t['name']} ({t['kind']}) {t['def_hash'][:19]}")
    return "\n".join(lines)
