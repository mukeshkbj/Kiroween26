"""The explorer's effective key policy: a pure decision, checked before every press.

Order of rules (deny always beats allow):

    1. deny: global key, whole screen, per-screen key, key learnt from a screen legend
    2. allow: key declared read-only for this screen in the human seed, or present in
       the approved ``key-policy.json`` for this screen_id
    3. allow: key is not commit-capable (CLEAR, PA1-3, PF13-24)
    4. otherwise deny ``commit_capable``

There is deliberately no path from screen text to *allow*: legends such as
``PF4=DELETE`` are parsed into extra denies only (``learn_hints``).
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .ids import is_commit_capable, key_name, node_id
from .seed import ExploreSeed


@dataclass(frozen=True)
class Allow:
    reason: str  # "declared" | "approved_policy" | "not_commit_capable"
    allowed: bool = True


@dataclass(frozen=True)
class Deny:
    reason: str  # "denied_key" | "denied_screen" | "denied_hint" | "commit_capable"
    allowed: bool = False


Decision = Allow | Deny

# Legend text such as "PF4=DELETE" or "ENTER=CONFIRM AND SAVE". Parsed as data only.
_LEGEND_RE = re.compile(r"\b(ENTER|CLEAR|PA[123]|PF(?:[1-9]|1\d|2[0-4]))\s*[=:]\s*([A-Z]+(?: [A-Z]+){0,3})", re.IGNORECASE)
_DANGEROUS_RE = re.compile(
    r"\b(delete|purge|remove|erase|submit|save|update|commit|confirm|send|post|apply|approve|pay)\b",
    re.IGNORECASE,
)


def hint_denies(rows: Iterable[str]) -> frozenset[str]:
    """Keys whose on-screen legend suggests they change data. Only ever used to deny."""
    out: set[str] = set()
    for row in rows:
        for m in _LEGEND_RE.finditer(row):
            if _DANGEROUS_RE.search(m.group(2)):
                out.add(key_name(m.group(1)))
    return frozenset(out)


def load_approved_policy(path: Path | None) -> dict[str, frozenset[str]]:
    """Read an approved ``key-policy.json`` (the format mcp-server loads). Missing = empty."""
    if path is None or not Path(path).exists():
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {sid: frozenset(key_name(k) for k in entry.get("read_only_keys", [])) for sid, entry in raw.items()}


def _refs(screen_id: str) -> tuple[str, str]:
    return screen_id, node_id(screen_id)


@dataclass
class EffectivePolicy:
    seed: ExploreSeed
    approved: Mapping[str, frozenset[str]] = field(default_factory=dict)
    _hints: dict[str, frozenset[str]] = field(default_factory=dict)

    # -- text hints (deny only) ---------------------------------------------

    def learn_hints(self, screen_id: str, rows: Iterable[str]) -> frozenset[str]:
        """Record keys whose legend looks dangerous on this screen. Returns the new denies."""
        found = hint_denies(rows)
        if found:
            self._hints[screen_id] = self._hints.get(screen_id, frozenset()) | found
        return found

    # -- the decision -------------------------------------------------------

    def may_press(self, key: str, screen_id: str) -> Decision:
        k = key_name(key)
        sid, nid = _refs(screen_id)
        d = self.seed.deny
        if k in d.keys:
            return Deny("denied_key")
        if sid in d.nodes or nid in d.nodes:
            return Deny("denied_screen")
        if any(k in d.screen_keys.get(ref, ()) for ref in (sid, nid)):
            return Deny("denied_key")
        if k in self._hints.get(screen_id, frozenset()):
            return Deny("denied_hint")
        if any(k in self.seed.declared_read_only.get(ref, ()) for ref in (sid, nid)):
            return Allow("declared")
        if k in self.approved.get(screen_id, frozenset()):
            return Allow("approved_policy")
        if not is_commit_capable(k):
            return Allow("not_commit_capable")
        return Deny("commit_capable")

    def declared_keys(self, screen_id: str) -> frozenset[str]:
        """Keys a human declared read-only (seed) or approved (key-policy.json) for this
        screen, read straight from the data. No deny logic and no ``may_press`` here, so the
        service gate built on it stays independent of the rules above."""
        sid, nid = _refs(screen_id)
        return frozenset(self.approved.get(screen_id, ())) | frozenset(
            k for ref in (sid, nid) for k in self.seed.declared_read_only.get(ref, ())
        )

    def read_only_keys(self, screen_id: str) -> frozenset[str]:
        """Declared or approved keys that no deny overrides."""
        return frozenset(k for k in self.declared_keys(screen_id) if self.may_press(k, screen_id).allowed)