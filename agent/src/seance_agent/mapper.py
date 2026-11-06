"""EventMapper: service observers -> websocket screen/field_focus/audit events.

The service emits an ``OpEvent`` (observe.py) at the start and end of every
primitive operation, and an ``AuditEntry`` after every durable append. The agent
subscribes to both in-process; this class turns that stream into the UI events of
contracts 4.3 so the planchette can follow a multi-step recipe.

The mapping is the one proven by ``seance_mcp.contracts.record`` (read as the
worked example):

* One ``screen{phase:before}`` per tool call, at the first operation that has a
  ``screen_before``; a ``screen{phase:after}`` after every operation that
  succeeded (``outcome == "ok"`` with a ``screen_after``). The last ``after`` is
  the call's final screen.
* ``field_focus`` when an operation *starts*: ``fill`` carries the field position;
  ``key`` carries the key name and no position; ``read`` carries no position. An
  operation refused before it chose a key (``key is None``) emits no focus.
* ``audit_entry`` in the order entries were appended.

Safety: the mapper only forwards what the service already made safe. ``ScreenOut``
has hidden values nulled; ``OpEvent.value`` is redacted; ``AuditEntry`` values are
redacted. The mapper never reads a raw screen and never reaches the bridge.

Callbacks fire inside the service lock, so the subscribed handler must only append
to a buffer and return; the mapping and the (synchronous) ``Session.emit`` happen
later, in ``flush`` after the tool call returns on the agent's own task.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from seance_mcp.audit import AuditEntry
from seance_mcp.observe import OpEvent

from .events import AuditEntryData, FieldFocusData, ScreenData
from .session import Session

BusItem = tuple[Literal["op", "audit"], Any]


@dataclass
class CallScope:
    """Per-tool-call mapping state: the id, a step counter and whether the
    ``before`` screen was sent yet."""

    tool_call_id: str
    step: int = 0
    before_sent: bool = False
    cur_screen_id: str = ""


class EventMapper:
    """Subscribes to one service's observers and maps buffered events to the UI.

    Subscribe once per connected service with :meth:`attach`; buffered items are
    flushed per tool call via :meth:`flush`. Items that arrive outside a tool call
    (connect, resync) are flushed with ``scope=None`` and only produce
    ``audit_entry`` events (connect's own screen is sent as a snapshot by the
    caller, matching the recorded transcripts)."""

    def __init__(self, session: Session, *, turn_id_getter: Callable[[], str | None]):
        self._session = session
        self._turn_id = turn_id_getter
        self._bus: list[BusItem] = []
        self._unsub: list[Callable[[], None]] = []
        self.last_screen: Any = None  # latest ScreenOut seen (for argument redaction)

    def attach(self, service: Any) -> None:
        self._unsub.append(service.observe(lambda e: self._bus.append(("op", e))))
        self._unsub.append(service.audit.subscribe(lambda e: self._bus.append(("audit", e))))

    def detach(self) -> None:
        for u in self._unsub:
            u()
        self._unsub.clear()
        self._bus.clear()

    def take_bus(self) -> list[BusItem]:
        items, self._bus = self._bus, []
        return items

    # -- mapping ----------------------------------------------------------

    def flush(self, scope: CallScope | None) -> None:
        """Map everything buffered since the last flush into UI events."""
        for kind, item in self.take_bus():
            if kind == "audit":
                self._emit_audit(item)
                continue
            ev: OpEvent = item
            if ev.tool == "connect":
                # connect's screen is sent as a snapshot by the caller.
                continue
            if ev.phase == "start":
                if scope is not None and not scope.before_sent and ev.screen_before is not None:
                    self._emit_screen("before", scope, ev.screen_before)
                    scope.before_sent = True
                self._emit_focus(scope, ev)
            elif ev.outcome == "ok" and ev.screen_after is not None:
                self._emit_screen("after", scope, ev.screen_after)

    def _emit_screen(self, phase: Literal["before", "after", "snapshot"], scope: CallScope | None, screen: Any) -> None:
        self.last_screen = screen
        if scope is not None:
            scope.cur_screen_id = screen.screen_id
        self._session.emit(
            ScreenData(phase=phase, tool_call_id=scope.tool_call_id if scope else None, screen=screen),
            turn_id=self._turn_id(),
        )

    def _emit_focus(self, scope: CallScope | None, ev: OpEvent) -> None:
        if scope is None:
            return
        mode = {"fill_field": "fill", "press_key": "key", "confirm_action": "key"}.get(ev.tool, "read")
        if mode == "key" and ev.key is None:
            return  # refused before a key was chosen: nothing to point at
        sid = ev.screen_before.screen_id if ev.screen_before else scope.cur_screen_id
        target = ev.target
        self._session.emit(
            FieldFocusData(
                tool_call_id=scope.tool_call_id,
                step=scope.step,
                mode=mode,  # type: ignore[arg-type]
                screen_id=sid,
                field_index=target.index if target else None,
                row=target.row if target else None,
                col=target.col if target else None,
                length=target.length if target else None,
                label=(target.label or None) if target else None,
                key=ev.key if mode == "key" else None,
            ),
            turn_id=self._turn_id(),
        )
        scope.step += 1

    def _emit_audit(self, entry: AuditEntry) -> None:
        self._session.emit(AuditEntryData(entry=entry), turn_id=self._turn_id())


__all__ = ["EventMapper", "CallScope", "BusItem"]
