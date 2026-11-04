"""Load a spirit-map tool pack and decide which tools may be registered.

Format and rules: docs/contracts.md section 6. The enforcement lives here, on the
safety side, not in spirit-map: a tool is registered only if

* the pack and the tool are well formed and the name is legal and unique,
* ``def_hash`` equals the hash recomputed from the tool's own content (so an
  edited tool cannot ride on an old hash), and
* an entry with that exact name and hash is in ``tool-approvals.json`` (written
  by a human with ``spirit-map review --tools``), or ``allow_unreviewed`` is set
  (FakeBridge work only; the caller audits it).

Anything else is skipped with a reason. Pack-level problems raise ``ToolPackError``:
a configured but unusable pack must be loud, never silently ignored.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "gss.toolpack/1"
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
KINDS = frozenset({"read", "commit"})
GENERIC_TOOLS = frozenset(
    {"connect", "read_screen", "list_fields", "fill_field", "press_key", "confirm_action", "get_audit_log"}
)


class ToolPackError(Exception):
    """The configured tool pack cannot be used (fail closed, loudly)."""


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def def_hash(tool: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of the tool without ``def_hash`` and ``provenance``."""
    body = {k: v for k, v in tool.items() if k not in ("def_hash", "provenance")}
    return "sha256:" + hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


@dataclass
class LoadedPack:
    pack: dict[str, Any]
    approved: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (tool name, reason)
    unreviewed_allowed: bool = False


def _read_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolPackError(f"cannot read {what} {path}: {type(exc).__name__}") from None


def load_approvals(path: Path | None) -> dict[str, str]:
    """{tool name: approved def_hash}. A missing file means nothing is approved."""
    if path is None or not path.exists():
        return {}
    raw = _read_json(path, "tool approvals")
    out: dict[str, str] = {}
    try:
        for item in raw["approved"]:
            out[str(item["name"])] = str(item["def_hash"])
    except (KeyError, TypeError):
        raise ToolPackError(f"{path}: expected {{'approved': [{{'name', 'def_hash'}}, ...]}}") from None
    return out


def load_toolpack(path: Path, approvals_path: Path | None, allow_unreviewed: bool = False) -> LoadedPack:
    raw = _read_json(path, "tool pack")
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA or not isinstance(raw.get("tools"), list):
        raise ToolPackError(f"{path}: not a {SCHEMA} file")
    approvals = load_approvals(approvals_path)
    loaded = LoadedPack(pack=raw, unreviewed_allowed=allow_unreviewed)
    seen: set[str] = set()
    for tool in raw["tools"]:
        name = tool.get("name") if isinstance(tool, dict) else None
        label = str(name) if isinstance(name, str) else "<unnamed>"
        reason = _reject_reason(tool, name, seen)
        if reason is None:
            seen.add(name)  # type: ignore[arg-type]
            if not allow_unreviewed and approvals.get(name) != tool["def_hash"]:  # type: ignore[arg-type]
                reason = "not_approved"
        if reason is not None:
            loaded.skipped.append((label, reason))
        else:
            loaded.approved.append(tool)
    return loaded


def _reject_reason(tool: Any, name: Any, seen: set[str]) -> str | None:
    if not isinstance(tool, dict) or not isinstance(name, str) or not NAME_RE.match(name):
        return "bad_name"
    if name in GENERIC_TOOLS:
        return "name_collision"
    if name in seen:
        return "duplicate"
    if tool.get("kind") not in KINDS:
        return "bad_kind"
    if not isinstance(tool.get("input_schema"), dict) or not isinstance(tool.get("recipe"), list):
        return "malformed"
    if tool.get("def_hash") != def_hash(tool):
        return "hash_mismatch"
    return None


class RecipeService:
    """The only handle generated tools get on the 3270 session.

    It forwards to the real service (so every step is gated, audited and observed
    exactly like a generic call) but has **no** ``confirm_action``, ``deny_action``,
    ``gate`` or audit access. A recipe can therefore propose a commit but can
    never confirm one, whatever the tool pack says.
    """

    __slots__ = ("_s",)

    def __init__(self, service: Any):
        self._s = service

    async def read_screen(self) -> Any:
        return await self._s.read_screen()

    async def list_fields(self) -> Any:
        return await self._s.list_fields()

    async def fill_field(self, field_ref: int | tuple[int, int], value: str) -> Any:
        return await self._s.fill_field(field_ref, value)

    async def press_key(self, key: str) -> Any:
        return await self._s.press_key(key)


Registrar = Callable[[Any, "RecipeService", list[dict[str, Any]], dict[str, Any]], list[str]]


def default_registrar() -> Registrar:
    """``seance_spirit.register(server, service, tools, pack) -> registered names``."""
    try:
        mod = importlib.import_module("seance_spirit")
    except ImportError:
        raise ToolPackError(
            "GENERATED_TOOLS_PATH is set but the seance_spirit package is not installed"
        ) from None
    reg = getattr(mod, "register", None)
    if reg is None:
        raise ToolPackError("seance_spirit has no register(server, service, tools, pack)")
    return reg  # type: ignore[no-any-return]
