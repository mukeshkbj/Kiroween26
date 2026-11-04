"""Commit safety: key policy, pending actions, and the human-confirmation decision.

``SafetyGate`` is a pure, synchronous state machine (no I/O, injected clock).
The single entry point for executing a commit-capable key is ``authorize()``,
which applies every rule in a fixed order and consumes the action, so the tool
layer cannot get the order wrong and an action can never fire twice:

    lookup -> expired? -> operator switch -> human decision -> same screen? -> consume

Decisions come from ``decide_*`` functions, one per confirm mode. The elicit
decision is deliberately strict: only ``AcceptedElicitation`` whose ``data`` is a
``Confirm`` with ``confirm=True`` approves. The SDK hands a resolver's direct
return value to the tool wrapped as ``AcceptedElicitation`` too (spike finding),
so "accepted" alone must never mean "approved".
"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from seance_bridge import COMMIT_CAPABLE, Key

from .config import ConfirmMode

WEAKEST = "client-approval(weakest)"


class GateError(Exception):
    """A refusal with a stable code (surfaced to the MCP caller as-is)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class FieldSnap(BaseModel):
    """An unprotected field as the human saw it when the action was proposed."""

    model_config = ConfigDict(frozen=True)

    index: int
    row: int
    col: int
    label: str
    value: str  # already redacted: "<hidden>" / "<redacted>" where needed


class PendingAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_id: str
    screen_id: str
    key: str
    field_snapshot: tuple[FieldSnap, ...]
    created_at: float
    expires_at: float
    approved_by: str | None = None  # set by the oob channel only


class Confirm(BaseModel):
    """The elicitation form: one yes/no checkbox."""

    confirm: bool


class ConfirmationUnavailable(BaseModel):
    """Returned by the resolver instead of asking when nobody can be asked."""

    reason: str


class SkipElicitation(BaseModel):
    """Returned by the resolver when the mode does not elicit, or the action
    cannot be confirmed anyway (unknown/expired/read-only): no question asked."""

    reason: str


@dataclass(frozen=True)
class Decision:
    approved: bool
    confirmed_by: str
    code: str = ""
    message: str = ""


# ---------------------------------------------------------------- key policy


class KeyPolicy:
    """Per-screen read-only key overrides. Empty by default (safe)."""

    def __init__(self, read_only: dict[str, frozenset[str]] | None = None):
        self._ro = read_only or {}

    @classmethod
    def load(cls, path: Path | None) -> "KeyPolicy":
        if path is None:
            return cls()
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        table: dict[str, frozenset[str]] = {}
        for screen_id, entry in raw.items():
            keys = entry.get("read_only_keys", [])
            table[screen_id] = frozenset(Key[k.upper()].value for k in keys)
        return cls(table)

    def may_commit(self, key: Key, screen_id: str | None) -> bool:
        if screen_id is not None and key.value in self._ro.get(screen_id, frozenset()):
            return False
        return key in COMMIT_CAPABLE


# ---------------------------------------------------------------- the gate


@dataclass
class SafetyGate:
    allow_commit: bool
    ttl_s: float
    policy: KeyPolicy = field(default_factory=KeyPolicy)
    clock: Callable[[], float] = time.monotonic
    _pending: PendingAction | None = None
    needs_resync: bool = False

    # -- proposal -------------------------------------------------------

    def may_commit(self, key: Key, screen_id: str | None) -> bool:
        return self.policy.may_commit(key, screen_id)

    def propose(
        self, key: Key, screen_id: str, snapshot: Iterable[FieldSnap]
    ) -> tuple[PendingAction, PendingAction | None]:
        """Create the pending action. Returns (new, superseded_or_None)."""
        self.ensure_synced()
        now = self.clock()
        action = PendingAction(
            action_id=str(uuid.uuid4()),
            screen_id=screen_id,
            key=key.value,
            field_snapshot=tuple(snapshot),
            created_at=now,
            expires_at=now + self.ttl_s,
        )
        old, self._pending = self._pending, action
        return action, old

    @property
    def pending(self) -> PendingAction | None:
        return self._pending

    # -- lookups (side-effect free; safe for resolvers) -------------------

    def peek(self, action_id: str) -> PendingAction | None:
        """The live pending action with this id, or None. Never mutates."""
        p = self._pending
        if p is None or p.action_id != action_id or self.clock() >= p.expires_at:
            return None
        return p

    # -- oob channel ------------------------------------------------------

    def approve_oob(self, action_id: str, who: str) -> PendingAction:
        """Record a human approval from the out-of-band channel (web UI modal)."""
        p = self.peek(action_id)
        if p is None:
            raise GateError("unknown_action", "no live pending action with that id")
        approved = p.model_copy(update={"approved_by": f"oob:{who}"})
        self._pending = approved
        return approved

    # -- the only way to a commit ----------------------------------------

    def authorize(
        self, action_id: str, current_screen_id: str | None, decision: Decision
    ) -> PendingAction:
        """Apply every rule in order; on success the action is consumed."""
        self.ensure_synced()
        p = self._pending
        if p is None or p.action_id != action_id:
            raise GateError("unknown_action", "no pending action with that id (it may have run already)")
        if self.clock() >= p.expires_at:
            self._pending = None
            raise GateError("action_expired", "the pending action expired; propose it again")
        if not self.allow_commit:
            # Stays pending: the operator may still enable commits.
            raise GateError("read_only", "server is read-only (SEANCE_ALLOW_COMMIT is off)")
        if not decision.approved:
            if decision.code in ("declined", "cancelled"):
                self._pending = None
            raise GateError(decision.code or "not_confirmed", decision.message or "not confirmed by a human")
        if current_screen_id != p.screen_id:
            self._pending = None
            raise GateError("stale_screen", "the screen changed since the action was proposed")
        self._pending = None  # consume BEFORE the key is sent: never twice
        return p

    # -- ambiguous acknowledgement ----------------------------------------

    def mark_ambiguous(self) -> None:
        self.needs_resync = True
        self._pending = None

    def resynced(self) -> None:
        self.needs_resync = False

    def ensure_synced(self) -> None:
        if self.needs_resync:
            raise GateError(
                "needs_resync",
                "a key press had an ambiguous acknowledgement; call read_screen before any key",
            )


# ---------------------------------------------------------------- decisions


def decide_elicit(answer: object) -> Decision:
    """Strict: approve only an accepted form whose data is Confirm(confirm=True)."""
    from mcp.server.mcpserver import AcceptedElicitation, CancelledElicitation, DeclinedElicitation

    if isinstance(answer, AcceptedElicitation):
        data = getattr(answer, "data", None)
        if type(data) is Confirm and data.confirm is True:
            return Decision(True, "elicit")
        if isinstance(data, ConfirmationUnavailable):
            return Decision(False, "elicit", "confirmation_unavailable",
                            f"cannot ask a human: {data.reason}; server stays read-only for this client")
        if isinstance(data, SkipElicitation):
            return Decision(False, "elicit", "not_confirmed", data.reason)
        return Decision(False, "elicit", "declined", "the user did not confirm")
    if isinstance(answer, DeclinedElicitation):
        return Decision(False, "elicit", "declined", "the user declined")
    if isinstance(answer, CancelledElicitation):
        return Decision(False, "elicit", "cancelled", "the user dismissed the question")
    return Decision(False, "elicit", "confirmation_unavailable", "no confirmation was obtained")


def decide_client_approval(client: str) -> Decision:
    return Decision(True, f"{WEAKEST}:{client}")


def decide_oob(action: PendingAction | None) -> Decision:
    if action is not None and action.approved_by:
        return Decision(True, action.approved_by)
    return Decision(False, "oob", "awaiting_oob",
                    "waiting for confirmation in the Seance UI; nothing was sent")


def decide(mode: ConfirmMode, answer: object, client: str, action: PendingAction | None) -> Decision:
    if mode is ConfirmMode.ELICIT:
        return decide_elicit(answer)
    if mode is ConfirmMode.CLIENT_APPROVAL:
        return decide_client_approval(client)
    return decide_oob(action)


def confirmation_prompt(action: PendingAction) -> str:
    """The question shown to the human. Field values are screen data (untrusted)
    and are shown as data, already redacted."""
    lines = [
        f"Send {action.key} to the mainframe?",
        f"Screen {action.screen_id[:12]}. This may change data on the legacy system.",
    ]
    for f in action.field_snapshot:
        label = f.label or f"field {f.index}"
        lines.append(f"  {label}: {f.value!r}")
    return "\n".join(lines)
