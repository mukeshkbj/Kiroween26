"""App registry, system runtimes and the SpiritMapView loader (REQ-022, REQ-024).

``agent/apps.json`` (contracts section 8) names apps and the *environment variable
names* for live hosts; it never holds a host, port or credential.

A ``kind: fake`` app runs over ``seance_mcp.fake``. A ``kind: live`` app is refused
(``live_not_allowed``) unless the checkout is allowed to touch the live container
(contracts section 2.1). The refusal happens **before any port is built**, and the
service's own guard is a second layer. This module never probes a live host:
``reachable`` is reported as ``null`` rather than opening a connection to find out.
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from seance_mcp import fake as fake_mod
from seance_mcp.config import ConfirmMode, Settings as McpSettings
from seance_mcp.factory import build_service
from seance_mcp.live import LIVE_REFUSAL, live_allowed
from seance_mcp.paths import REPO_ROOT
from seance_mcp.safety import GateError
from seance_mcp.service import SeanceService

from .config import Settings

AGENT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_APPS_FILE = AGENT_DIR / "apps.json"
# Documented defaults per port variable (contracts section 8): TK4- 3270, the stand-in 3271.
DEFAULT_PORTS = {"TN3270_PORT": 3270, "STANDIN_PORT": 3271}
MAP_ROLES = {"identifier", "display", "input", "selector", "status", "other"}
MAP_KINDS = {"menu", "enquiry", "list", "form", "confirm", "error", "other"}


class AppEntry(BaseModel):
    app_id: str
    name: str
    kind: str  # "fake" | "live"
    description: str
    fake: str | None = None
    host_env: str | None = None
    port_env: str | None = None


class AppRegistry:
    def __init__(self, apps: list[AppEntry], root: Path = REPO_ROOT):
        self._apps = {a.app_id: a for a in apps}
        self.root = root

    @classmethod
    def load(cls, path: Path = DEFAULT_APPS_FILE, root: Path = REPO_ROOT) -> "AppRegistry":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([AppEntry.model_validate(a) for a in raw["apps"]], root)

    def get(self, app_id: str) -> AppEntry | None:
        return self._apps.get(app_id)

    def all(self) -> list[AppEntry]:
        return list(self._apps.values())

    def artefact_dir(self, app_id: str) -> Path:
        return self.root / "docs" / "spirit-map" / app_id

    # -- REST: AppInfo ----------------------------------------------------

    def info(self, entry: AppEntry, settings: Settings) -> dict[str, Any]:
        business, approved = self._tool_counts(entry.app_id)
        return {
            "app_id": entry.app_id, "name": entry.name, "kind": entry.kind, "description": entry.description,
            "reachable": None,  # never probe: a probe of a live host is a live connection
            "has_map": (self.artefact_dir(entry.app_id) / "spirit-map.json").is_file(),
            "tools": {"business": business, "approved": approved},
            "read_only": not settings.allow_commit,
        }

    def _tool_counts(self, app_id: str) -> tuple[int, int]:
        d = self.artefact_dir(app_id)
        try:
            pack = json.loads((d / "tools.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0, 0
        tools = pack.get("tools", [])
        approved = _approved(d)
        return len(tools), sum(1 for t in tools if approved.get(t.get("name")) == t.get("def_hash"))

    # -- SpiritMapView ----------------------------------------------------

    def spirit_map_view(self, app_id: str) -> dict[str, Any] | None:
        """Build the view from ``spirit-map.json`` + ``labels.json`` + ``tools.json`` +
        ``tool-approvals.json``. None if there is no map. Read-only."""
        d = self.artefact_dir(app_id)
        try:
            m = json.loads((d / "spirit-map.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        labels = _load(d / "labels.json")
        pack = _load(d / "tools.json")
        approved = _approved(d)
        ln, lf, le = labels.get("nodes", {}), labels.get("fields", {}), labels.get("edges", {})

        nodes = []
        for n in m.get("nodes", []):
            nl = ln.get(n["id"], {})
            conf = float(nl.get("confidence", 0.0))
            kind = nl.get("kind", "other")
            fields = []
            for f in n.get("fields", []):
                fl = lf.get(f"{n['id']}:{f.get('key')}", {})
                role = fl.get("role", "other")
                fields.append({
                    "key": f.get("key", ""), "label": f.get("label", ""),
                    "business_name": fl.get("business_name", f.get("key", "")),
                    "role": role if role in MAP_ROLES else "other",
                    "row": f["row"], "col": f["col"], "length": f["length"],
                    "protected": bool(f.get("protected")), "hidden": bool(f.get("hidden")),
                })
            nodes.append({
                "id": n["id"], "screen_id": n["screen_id"], "name": nl.get("name", n["id"]),
                "kind": kind if kind in MAP_KINDS else "other", "confidence": conf,
                "needs_review": bool(nl.get("needs_review", conf < 0.7)), "visits": int(n.get("visits", 0)),
                "preview": [str(r)[:80].ljust(80) for r in (n.get("rows") or [])][:24]
                + [" " * 80] * max(0, 24 - len(n.get("rows") or [])),
                "fields": fields,
            })
        edges = [{
            "id": e["id"], "from": e["from"], "to": e["to"], "key": e["key"],
            "meaning": le.get(e["id"], {}).get("meaning", e["key"]),
            "read_only": bool(e.get("read_only")),
            "status": "observed" if e.get("observed", 0) else "declared",
        } for e in m.get("edges", [])]
        frontier = [{"from": x["from"], "key": x["key"], "reason": x["reason"], "meaning": x.get("meaning")}
                    for x in m.get("frontier", [])]
        tools = [{
            "name": t["name"], "kind": t["kind"],
            "approved": approved.get(t["name"]) == t.get("def_hash"),
            "path": list(t.get("provenance", {}).get("nodes", [])),
        } for t in pack.get("tools", [])]
        return {
            "app_id": app_id, "version": labels.get("map_hash") or pack.get("map_hash") or "",
            "generated_at": pack.get("generated_at") or (m.get("run") or {}).get("started_at") or "",
            "home": m.get("home", ""), "nodes": nodes, "edges": edges, "frontier": frontier, "tools": tools,
        }


def _load(p: Path) -> dict[str, Any]:
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def _approved(d: Path) -> dict[str, str]:
    raw = _load(d / "tool-approvals.json")
    return {a["name"]: a["def_hash"] for a in raw.get("approved", []) if "name" in a and "def_hash" in a}


# ---------------------------------------------------------------- runtimes


@dataclass
class SystemRuntime:
    """A built, not yet connected, system: the MCP server and its service."""

    app_id: str
    server: Any
    service: SeanceService
    commit_hints: dict[str, bool]


def build_runtime(
    entry: AppEntry,
    registry: AppRegistry,
    settings: Settings,
    *,
    env: Mapping[str, str] | None = None,
    audit_path: Path | None = None,
) -> SystemRuntime:
    """Build the in-process server for ``entry``. Raises ``GateError`` with a stable
    code: ``live_not_allowed`` (before any port is built) or ``unknown_app``."""
    e = os.environ if env is None else env
    art = registry.artefact_dir(entry.app_id)
    pack, approvals, policy = art / "tools.json", art / "tool-approvals.json", art / "key-policy.json"
    mcp = McpSettings(
        allow_commit=settings.allow_commit, confirm_mode=ConfirmMode.OOB, pending_ttl_s=settings.pending_ttl_s,
        audit_log_path=settings.audit_log_path,
        key_policy_path=settings.key_policy_path or (policy if policy.is_file() else None),
        generated_tools_path=settings.generated_tools_path or (pack if pack.is_file() else None),
        tool_approvals_path=settings.tool_approvals_path or (approvals if approvals.is_file() else None),
    )
    port: Any = None
    if entry.kind == "fake":
        factory = getattr(fake_mod, entry.fake or "", None)
        if factory is None:
            raise GateError("unknown_app", f"{entry.app_id}: no fake app named {entry.fake!r}")
        port = factory()
    elif entry.kind == "live":
        if not live_allowed(e):
            raise GateError("live_not_allowed", LIVE_REFUSAL)
        host = e.get(entry.host_env or "") or settings.tn3270_host
        # Each live app reads its own port variable (contracts section 8). An unset
        # STANDIN_PORT falls back to the stand-in's default, never to TK4-'s port:
        # otherwise "Seance Insurance" would silently connect to the wrong system.
        tport = e.get(entry.port_env or "") or (
            settings.tn3270_port if entry.port_env == "TN3270_PORT" else None
        ) or DEFAULT_PORTS.get(entry.port_env or "")
        if not host or not tport:
            raise GateError("unknown_app", f"{entry.app_id}: set {entry.host_env} and {entry.port_env}")
        mcp = mcp.model_copy(update={"host": host, "port": int(tport)})
    else:
        raise GateError("unknown_app", f"{entry.app_id}: unsupported kind {entry.kind!r}")
    server, service = build_service(mcp, port, audit_path=audit_path)
    hints = {}
    try:
        for t in json.loads(pack.read_text(encoding="utf-8")).get("tools", []):
            hints[t["name"]] = t.get("kind") == "commit"
    except (OSError, ValueError, KeyError):
        pass
    return SystemRuntime(entry.app_id, server, service, hints)


__all__ = ["AppEntry", "AppRegistry", "SystemRuntime", "build_runtime", "live_allowed"]
