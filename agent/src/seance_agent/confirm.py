"""ConfirmBroker: the out-of-band human gate (REQ-015 to REQ-019, REQ-027).

This is where the component's one promise is kept: **even a fully compromised
model cannot change data on the legacy system.** The model has no tool that
confirms; when a tool returns ``pending`` the agent loop hands the action here and
*suspends*. The only thing that can resume it with an approval is a
``confirm_decision{approve}`` from the **controller** websocket, which the broker
turns into ``gate.approve_oob(action_id, who)`` followed by ``service.confirm_action``.
Observers, unknown ids, expired ids and double decisions are refused and change
nothing on the 3270 session.

Authoritative modal content (``key``, ``screen_id``, ``field_snapshot``,
``expires_in_s``) is copied from ``gate.pending`` when ``confirmation_required`` is
emitted, never from the model. The model's own words travel only as
``agent_summary``, which the UI labels unverified.

Exactly one ``confirmation_resolved`` is emitted per ``confirmation_required``
(approved | denied | expired | superseded | blocked_read_only | stale | error).
The broker keeps its own minimal ledger (one entry, since the gate allows one
pending action) and never reads the gate's private state to decide.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import anyio
from mcp.server.mcpserver.exceptions import ToolError  # noqa: F401  (documentation of error origin)

from seance_mcp.config import ConfirmMode
from seance_mcp.safety import GateError, decide

from .events import ConfirmationRequiredData, ConfirmationResolvedData
from .mapper import CallScope, EventMapper
from .session import Session

if TYPE_CHECKING:  # avoid importing the heavy service type at runtime
    from seance_mcp.service import SeanceService


@dataclass
class Resolution:
    """What the loop needs to continue the turn after a decision."""

    outcome: str  # approved | denied | expired | superseded | blocked_read_only | stale | error
    error_code: str | None = None


# outcome of a failed confirm_action (GateError.code) -> resolved outcome
_GATE_OUTCOME = {
    "read_only": "blocked_read_only",
    "stale_screen": "stale",
    "action_expired": "expired",
    "unknown_action": "error",
    "needs_resync": "error",
}


@dataclass
class _Pending:
    action_id: str
    turn_id: str | None
    tool_call_id: str
    event: anyio.Event
    resolution: Resolution | None = None


class ConfirmBroker:
    """Owns the single in-flight pending action and resolves it out of band."""

    def __init__(self, service: "SeanceService", session: Session, mapper: EventMapper):
        self._service = service
        self._session = session
        self._mapper = mapper
        self._pending: _Pending | None = None

    @property
    def pending_action_id(self) -> str | None:
        return self._pending.action_id if self._pending else None

    # -- the loop suspends here -------------------------------------------

    def register_pending(
        self, *, tool_call_id: str, turn_id: str | None, read_only: bool, agent_summary: str | None
    ) -> str:
        """Emit ``confirmation_required`` from the gate's pending action and record
        the in-flight entry, without blocking. Returns the action_id.

        Separated from the blocking wait so the state machine (REQ-027) can drive
        registration and resolution as independent steps. Raises
        ``GateError('confirmation_unavailable')`` if there is no live pending
        action (fail closed: the loop must not have called us)."""
        gate_pending = self._service.gate.pending
        if gate_pending is None:
            raise GateError("confirmation_unavailable", "no pending action to confirm")
        aid = gate_pending.action_id

        # A new pending action supersedes any previous one we were awaiting.
        if self._pending is not None and self._pending.action_id != aid:
            self._resolve(self._pending, Resolution("superseded"))

        entry = _Pending(action_id=aid, turn_id=turn_id, tool_call_id=tool_call_id, event=anyio.Event())
        self._pending = entry

        self._session.emit(
            ConfirmationRequiredData(
                action_id=aid,
                tool_call_id=tool_call_id,
                screen_id=gate_pending.screen_id,
                key=gate_pending.key,
                field_snapshot=list(gate_pending.field_snapshot),
                expires_in_s=round(max(0.001, gate_pending.expires_at - self._service.gate.clock()), 1),
                read_only=read_only,
                agent_summary=agent_summary,
            ),
            turn_id=turn_id,
        )
        return aid

    async def await_decision(
        self, *, tool_call_id: str, turn_id: str | None, read_only: bool, agent_summary: str | None
    ) -> Resolution:
        """Register the pending action, then block until the controller (or the
        clock) resolves it. Returns the resolution the loop turns into the single
        ``tool_result``."""
        self.register_pending(
            tool_call_id=tool_call_id, turn_id=turn_id, read_only=read_only, agent_summary=agent_summary
        )
        entry = self._pending
        assert entry is not None
        await entry.event.wait()
        assert entry.resolution is not None
        return entry.resolution

    # -- controller decisions ---------------------------------------------

    async def decide(self, action_id: str, decision: str, *, session_id: str) -> Resolution | None:
        """Apply a controller's ``confirm_decision``. Returns the Resolution if it
        matched the in-flight action, or None for an unknown/stale id (the caller
        emits an ``error`` event and nothing touches the 3270 session).

        Controller-vs-observer is enforced by the caller (``api.py``): only a
        controller message reaches this method."""
        entry = self._pending
        if entry is None or entry.action_id != action_id or entry.resolution is not None:
            return None  # unknown, already resolved, or superseded: no effect
        who = f"web-ui:{session_id}"
        if decision == "deny":
            return await self._deny(entry, who)
        return await self._approve(entry, who)

    async def _deny(self, entry: _Pending, who: str) -> Resolution:
        try:
            await self._service.deny_action(entry.action_id, who)
        except GateError as exc:
            # Expired between request and deny: still resolve exactly once.
            outcome = _GATE_OUTCOME.get(exc.code, "error")
            self._flush_after(entry)
            res = Resolution(outcome, error_code=exc.code if outcome == "error" else None)
            self._resolve(entry, res, confirmed_by=None)
            return res
        self._flush_after(entry)
        res = Resolution("denied")
        self._resolve(entry, res, confirmed_by=f"oob:{who}")
        return res

    async def _approve(self, entry: _Pending, who: str) -> Resolution:
        # Record the human approval in the gate, then authorise+send through the
        # service. The model never had either call in its tool list.
        try:
            self._service.gate.approve_oob(entry.action_id, who)
        except GateError as exc:
            outcome = _GATE_OUTCOME.get(exc.code, "error")
            self._flush_after(entry)
            res = Resolution(outcome, error_code=exc.code if outcome == "error" else None)
            self._resolve(entry, res, confirmed_by=None)
            return res
        decision = decide(ConfirmMode.OOB, None, "agent", self._service.gate.peek(entry.action_id))
        scope = CallScope(tool_call_id=entry.tool_call_id)
        try:
            await self._service.confirm_action(entry.action_id, decision)
        except GateError as exc:
            outcome = _GATE_OUTCOME.get(exc.code, "error")
            if exc.code == "read_only":
                # The action can never run under read-only: drop it so a retry fails closed.
                try:
                    await self._service.deny_action(entry.action_id, who)
                except GateError:
                    pass
            self._flush_after(entry)
            res = Resolution(outcome, error_code=exc.code if outcome == "error" else None)
            self._resolve(entry, res, confirmed_by=None)
            return res
        self._flush_after(entry)  # screen{after} of the committed key
        res = Resolution("approved")
        self._resolve(entry, res, confirmed_by=f"oob:{who}")
        return res

    # -- expiry / supersede (driven by the loop's timer or a new pending) --

    async def expire(self, action_id: str) -> Resolution | None:
        """Time out the in-flight action (TTL). The key is never sent."""
        entry = self._pending
        if entry is None or entry.action_id != action_id or entry.resolution is not None:
            return None
        try:
            await self._service.deny_action(action_id, "timer")
        except GateError:
            pass  # already expired/consumed; audited by the service
        self._flush_after(entry)
        res = Resolution("expired", error_code="action_expired")
        self._resolve(entry, res, confirmed_by=None)
        return res

    async def wait(self, action_id: str) -> Resolution:
        """Block until the in-flight action ``action_id`` is resolved."""
        entry = self._pending
        if entry is None or entry.action_id != action_id:
            raise GateError("unknown_action", "that action is not awaiting a decision")
        await entry.event.wait()
        assert entry.resolution is not None
        return entry.resolution

    async def abandon(self, action_id: str) -> Resolution | None:
        """The turn was cancelled while the action was pending: drop it unsent.
        Resolved as ``denied`` with no confirmer (a person did not approve it)."""
        entry = self._pending
        if entry is None or entry.action_id != action_id or entry.resolution is not None:
            return None
        try:
            await self._service.deny_action(action_id, "turn-cancelled")
        except GateError:
            pass
        self._flush_after(entry)
        res = Resolution("denied")
        self._resolve(entry, res, confirmed_by=None)
        return res

    # -- internals --------------------------------------------------------

    def _flush_after(self, entry: _Pending) -> None:
        """Map any screen/audit events the confirm/deny produced onto this call."""
        self._mapper.flush(CallScope(tool_call_id=entry.tool_call_id, before_sent=True))

    def _resolve(self, entry: _Pending, res: Resolution, *, confirmed_by: str | None = None) -> None:
        if entry.resolution is not None:
            return
        entry.resolution = res
        self._session.emit(
            ConfirmationResolvedData(
                action_id=entry.action_id,
                outcome=res.outcome,  # type: ignore[arg-type]
                confirmed_by=confirmed_by,
                error_code=res.error_code,
            ),
            turn_id=entry.turn_id,
        )
        entry.event.set()
        if self._pending is entry:
            self._pending = None


__all__ = ["ConfirmBroker", "Resolution"]
