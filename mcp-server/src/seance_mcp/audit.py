"""Append-only, hash-chained audit log (mainframe-safety: "audit everything").

One JSON object per line. Each entry carries the hash of the previous one, so
editing, deleting or reordering any line is detected by ``verify()``. The class
exposes ``append``, ``read`` and ``verify`` only: there is no rewrite API.

Redaction happens inside ``append`` so no caller can forget it: a value typed
into a hidden (non-display) field is stored as ``<hidden>``, and a value whose
field label looks credential-like is stored as ``<redacted>`` even when the
3270 datastream did not mark the field non-display.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

HIDDEN = "<hidden>"
REDACTED = "<redacted>"
_GENESIS = "0" * 64
_CREDENTIAL_RE = re.compile(r"pass(word|wd|phrase)?|\bpw\b|\bpin\b|secret|token", re.IGNORECASE)


class AuditEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    seq: int
    ts: str
    tool: str
    outcome: str
    screen_id: str | None = None
    field: str | None = None
    value: str | None = None
    key: str | None = None
    action_id: str | None = None
    confirmed_by: str = "n/a"
    detail: str | None = None
    prev_hash: str
    hash: str


def redact(value: str | None, *, hidden: bool = False, label: str | None = None) -> str | None:
    """Return the value as it may be stored or shown. Idempotent."""
    if value is None:
        return None
    if value in (HIDDEN, REDACTED):
        return value
    if hidden:
        return HIDDEN
    if label and _CREDENTIAL_RE.search(label):
        return REDACTED
    return value


def _digest(prev_hash: str, body: dict[str, object]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, path: Path, now: Callable[[], datetime] | None = None):
        self._path = Path(path)
        self._now = now or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.touch(exist_ok=True)
        entries = self.read()
        broken = self.verify()
        if broken is not None:
            # Never "repair" or truncate: refuse to extend a tampered chain.
            raise ValueError(f"audit log {self._path} fails verification at seq {broken}")
        self._seq = entries[-1].seq if entries else 0
        self._last = entries[-1].hash if entries else _GENESIS

    @property
    def path(self) -> Path:
        return self._path

    def append(
        self,
        tool: str,
        outcome: str,
        *,
        screen_id: str | None = None,
        field: str | None = None,
        value: str | None = None,
        field_hidden: bool = False,
        field_label: str | None = None,
        key: str | None = None,
        action_id: str | None = None,
        confirmed_by: str = "n/a",
        detail: str | None = None,
    ) -> AuditEntry:
        with self._lock:
            body: dict[str, object] = {
                "seq": self._seq + 1,
                "ts": self._now().isoformat(),
                "tool": tool,
                "outcome": outcome,
                "screen_id": screen_id,
                "field": field,
                "value": redact(value, hidden=field_hidden, label=field_label),
                "key": key,
                "action_id": action_id,
                "confirmed_by": confirmed_by,
                "detail": detail,
                "prev_hash": self._last,
            }
            h = _digest(self._last, body)
            entry = AuditEntry.model_validate({**body, "hash": h})
            line = json.dumps(entry.model_dump(), sort_keys=True, ensure_ascii=False)
            with open(self._path, "a", encoding="utf-8", newline="\n") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
            self._seq += 1
            self._last = h
            return entry

    def _lines(self) -> list[str]:
        # errors="replace": a corrupted multi-byte character must show up as a
        # hash mismatch in verify(), not crash the reader.
        with open(self._path, encoding="utf-8", errors="replace") as f:
            return [ln.rstrip("\n") for ln in f if ln.strip()]

    def read(self, limit: int | None = None) -> list[AuditEntry]:
        """Parsed entries, newest last. Unparseable lines are skipped here;
        ``verify()`` reports them."""
        out: list[AuditEntry] = []
        for ln in self._lines():
            try:
                out.append(AuditEntry.model_validate_json(ln))
            except ValueError:
                continue
        return out[-limit:] if limit else out

    def verify(self) -> int | None:
        """Return the first broken seq (1-based line position), or None if intact."""
        prev = _GENESIS
        for i, ln in enumerate(self._lines(), start=1):
            try:
                raw = json.loads(ln)
                stored = raw.pop("hash")
            except (ValueError, KeyError, AttributeError, TypeError):
                return i
            if raw.get("seq") != i or raw.get("prev_hash") != prev:
                return i
            if _digest(prev, raw) != stored:
                return i
            prev = stored
        return None
