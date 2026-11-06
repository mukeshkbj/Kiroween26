"""Stable ids and shared small helpers (pure)."""
from __future__ import annotations

import hashlib
import re

from seance_bridge import COMMIT_CAPABLE, Key

# Fields whose label looks credential-like are never filled, exposed or used as a tool parameter.
# A superset of the audit-log redaction rule in mcp-server.
CREDENTIAL_RE = re.compile(r"pass(word|wd|phrase)?|pwd|\bpw\b|\bpin\b|secret|token", re.IGNORECASE)
_CREDENTIAL_SAMPLES = ("PASSWORD", "PASSWD", "PASSPHRASE", "PWD", "PW", "PIN", "SECRET", "TOKEN")

# Key names as written in key-policy.json and the seed: ENTER, CLEAR, PA1-3, PF1-24.
COMMIT_CAPABLE_NAMES: frozenset[str] = frozenset(k.name for k in COMMIT_CAPABLE)
ALL_KEY_NAMES: frozenset[str] = frozenset(k.name for k in Key)


def key_name(key: str) -> str:
    """Canonical key name (``ENTER``, ``PF3``...). Accepts the bridge value (``Enter``) too.

    Raises ``ValueError`` for anything that is not a 3270 attention key."""
    k = key.strip().upper().replace(" ", "")
    if k not in ALL_KEY_NAMES:
        raise ValueError(f"unknown key {key!r}; want ENTER, CLEAR, PA1-PA3 or PF1-PF24")
    return k


def is_commit_capable(key: str) -> bool:
    return key_name(key) in COMMIT_CAPABLE_NAMES


def node_id(screen_id: str) -> str:
    """``n_`` + first 10 hex of the screen id (docs/contracts.md section 7.3)."""
    return "n_" + screen_id[:10]


def edge_id(from_node: str, key: str, fills: tuple[tuple[str, str], ...], to_node: str) -> str:
    raw = "|".join([from_node, key_name(key), ";".join(f"{f}={p}" for f, p in fills), to_node])
    return "e_" + hashlib.sha256(raw.encode()).hexdigest()[:10]


def looks_credential(label: str) -> bool:
    return bool(CREDENTIAL_RE.search(label or ""))


def pattern_targets_credentials(pattern: str) -> bool:
    """True if a label regex would select credential-like fields (so a probe may not use it)."""
    if CREDENTIAL_RE.search(pattern):
        return True
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return False
    return any(rx.search(s) for s in _CREDENTIAL_SAMPLES)
