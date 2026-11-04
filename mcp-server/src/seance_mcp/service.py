"""SeanceService: every tool's logic, independent of MCP.

One ``anyio.Lock`` serialises whole operations (not just single bridge calls),
because e.g. press_key is read-then-propose and confirm_action is
read-then-authorize-then-send; interleaving those across calls would break the
"same screen the human saw" guarantee. Every call that reaches the 3270 session
is audited, including refusals.
"""
from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Callable

import anyio

from seance_bridge import (
    FieldValidationError,
    Key,
    KeyboardTimeoutError,
    ScreenBridgeError,
    ScreenModel,
    SessionError,
)

from .audit import AuditEntry, AuditLog, redact
from .config import Settings
from .observe import FieldTarget, OpCallback, OpEvent, Subscribers
from .port import BridgePort
from .safety import Decision, GateError, SafetyGate
from .screens import (
    FieldOut,
    PressOut,
    ScreenOut,
    field_label,
    fields_out,
    pending_out,
    screen_out,
    snapshot,
)

MAX_VALUE_LEN = 1920


def parse_key(key: str) -> Key:
    k = key.strip().upper().replace(" ", "")
    try:
        return Key[k]
    except KeyError:
        raise GateError("bad_key", "key must be one of ENTER, CLEAR, PA1-PA3, PF1-PF24") from None


class SeanceService:
    def __init__(self, settings: Settings, port: BridgePort, audit: AuditLog, gate: SafetyGate):
        self.settings = settings
        self.port = port
        self.audit = audit
        self.gate = gate
        self._lock = anyio.Lock()
        self._last_screen_id: str | None = None
        self._ops = Subscribers()
        self._cur: OpEvent | None = None

    # -- observers (live step events; see observe.py) ---------------------

    def observe(self, cb: OpCallback) -> Callable[[], None]:
        """Subscribe to start/end events of each primitive operation. Returns unsubscribe."""
        return self._ops.add(cb)

    def _begin(self, tool: str, **kw: object) -> None:
        ev = OpEvent(tool=tool, phase="start", **kw)  # type: ignore[arg-type]
        self._cur = ev
        self._ops.emit(ev)

    def _end(self, outcome: str, screen_after: ScreenOut | None = None, **update: object) -> None:
        cur, self._cur = self._cur, None
        if cur is None:
            return
        self._ops.emit(cur.model_copy(update={"phase": "end", "outcome": outcome, "screen_after": screen_after, **update}))

    @contextlib.asynccontextmanager
    async def _trace(self, tool: str) -> AsyncIterator[None]:
        """Guarantee exactly one end event per operation, even on refusal or error."""
        self._cur = None
        try:
            yield
        except BaseException as exc:
            if self._cur is None:
                self._begin(tool)
            self._end(exc.code if isinstance(exc, GateError) else "error")
            raise
        finally:
            self._cur = None

    # -- helpers ----------------------------------------------------------

    def _require_connected(self, tool: str) -> None:
        if not self.port.connected:
            self.audit.append(tool, "not_connected")
            raise GateError("not_connected", "not connected; call connect first")

    async def _read(self) -> ScreenModel:
        s = await self.port.read_screen()
        self._last_screen_id = s.screen_id
        return s

    def _bridge_error(self, tool: str, exc: ScreenBridgeError, **audit_kw: object) -> GateError:
        if isinstance(exc, KeyboardTimeoutError):
            self.gate.mark_ambiguous()
            self.audit.append(tool, "ambiguous_ack", **audit_kw)  # type: ignore[arg-type]
            return GateError(
                "keyboard_timeout",
                "the keyboard did not unlock after the key; it was NOT resent. "
                "Call read_screen to see what happened before pressing anything else.",
            )
        if isinstance(exc, SessionError):
            self.audit.append(tool, "session_lost", **audit_kw)  # type: ignore[arg-type]
            return GateError("session_lost", "the 3270 session was lost; call connect again")
        if isinstance(exc, FieldValidationError):
            self.audit.append(tool, "field_invalid", detail=str(exc), **audit_kw)  # type: ignore[arg-type]
            return GateError("field_invalid", str(exc))
        self.audit.append(tool, "error", **audit_kw)  # type: ignore[arg-type]
        return GateError("bridge_error", "the bridge reported an error")

    # -- tools ------------------------------------------------------------

    async def connect(self, host: str | None = None, port: int | None = None) -> ScreenOut:
        h, p = host or self.settings.host, port or self.settings.port
        async with self._lock, self._trace("connect"):
            self._begin("connect")
            try:
                s = await self.port.connect(h, p)
            except ScreenBridgeError as exc:
                raise self._bridge_error("connect", exc, detail=f"{h}:{p}") from None
            self._last_screen_id = s.screen_id
            self.gate.resynced()
            self.audit.append("connect", "ok", screen_id=s.screen_id, detail=f"{h}:{p}")
            out = screen_out(s)
            self._end("ok", out)
            return out

    async def disconnect(self) -> None:
        async with self._lock:
            await self.port.disconnect()
            self.audit.append("disconnect", "ok")

    async def read_screen(self) -> ScreenOut:
        async with self._lock, self._trace("read_screen"):
            self._begin("read_screen")
            self._require_connected("read_screen")
            try:
                s = await self._read()
            except ScreenBridgeError as exc:
                raise self._bridge_error("read_screen", exc) from None
            self.gate.resynced()  # the caller has now seen the real screen
            self.audit.append("read_screen", "ok", screen_id=s.screen_id)
            out = screen_out(s)
            self._end("ok", out)
            return out

    async def list_fields(self) -> list[FieldOut]:
        async with self._lock, self._trace("list_fields"):
            self._begin("list_fields")
            self._require_connected("list_fields")
            try:
                s = await self._read()
            except ScreenBridgeError as exc:
                raise self._bridge_error("list_fields", exc) from None
            self.audit.append("list_fields", "ok", screen_id=s.screen_id)
            self._end("ok", screen_out(s))
            return fields_out(s)

    async def fill_field(self, field_ref: int | tuple[int, int], value: str) -> ScreenOut:
        async with self._lock, self._trace("fill_field"):
            self._require_connected("fill_field")
            if len(value) > MAX_VALUE_LEN:
                raise GateError("field_invalid", "value is longer than the screen")
            try:
                before = await self._read()
            except ScreenBridgeError as exc:
                raise self._bridge_error("fill_field", exc) from None
            target = _resolve(before, field_ref)
            kw: dict[str, object] = {
                "screen_id": before.screen_id,
                "field": _ref_str(field_ref),
                "value": value,
                "field_hidden": bool(target and target.hidden),
                "field_label": field_label(before, target) if target else None,
            }
            self._begin(
                "fill_field",
                screen_before=screen_out(before),
                field=_ref_str(field_ref),
                target=None if target is None else FieldTarget(
                    index=target.index, row=target.row, col=target.col, length=target.length,
                    label=str(kw["field_label"] or "")),
                value=redact(value, hidden=bool(target and target.hidden),
                             label=kw["field_label"]),  # type: ignore[arg-type]
            )
            try:
                after = await self.port.fill_field(field_ref, value)
            except ScreenBridgeError as exc:
                raise self._bridge_error("fill_field", exc, **kw) from None
            self._last_screen_id = after.screen_id
            self.audit.append("fill_field", "ok", **kw)  # type: ignore[arg-type]
            out = screen_out(after)
            self._end("ok", out)
            return out

    async def press_key(self, key: str) -> PressOut:
        k = parse_key(key)
        async with self._lock, self._trace("press_key"):
            self._require_connected("press_key")
            try:
                self.gate.ensure_synced()
            except GateError:
                self.audit.append("press_key", "needs_resync", key=k.value)
                raise
            try:
                s = await self._read()
            except ScreenBridgeError as exc:
                raise self._bridge_error("press_key", exc, key=k.value) from None
            self._begin("press_key", screen_before=screen_out(s), key=k.value)

            if self.gate.may_commit(k, s.screen_id):
                action, old = self.gate.propose(k, s.screen_id, snapshot(s))
                if old is not None:
                    self.audit.append("press_key", "superseded", action_id=old.action_id,
                                      key=old.key, screen_id=old.screen_id)
                self.audit.append("press_key", "proposed", action_id=action.action_id,
                                  key=k.value, screen_id=s.screen_id)
                self._end("pending", action_id=action.action_id)
                return PressOut(
                    status="pending",
                    message=(
                        f"{k.value} may change data on the legacy system, so it was NOT sent. "
                        "A human must confirm it: call confirm_action with this action_id."
                    ),
                    action=pending_out(action, self.gate.clock()),
                )

            try:
                after = await self.port.press(k)
            except ScreenBridgeError as exc:
                raise self._bridge_error("press_key", exc, key=k.value, screen_id=s.screen_id) from None
            self._last_screen_id = after.screen_id
            self.audit.append("press_key", "ok", key=k.value, screen_id=s.screen_id)
            out = screen_out(after)
            self._end("ok", out)
            return PressOut(status="executed", message=f"sent {k.value}", screen=out)

    async def confirm_action(self, action_id: str, decision: Decision) -> ScreenOut:
        async with self._lock, self._trace("confirm_action"):
            self._require_connected("confirm_action")
            try:
                self.gate.ensure_synced()
                current = await self._read()
            except GateError as exc:
                self.audit.append("confirm_action", exc.code, action_id=action_id)
                raise
            except ScreenBridgeError as exc:
                raise self._bridge_error("confirm_action", exc, action_id=action_id) from None
            try:
                action = self.gate.authorize(action_id, current.screen_id, decision)
            except GateError as exc:
                outcome = "blocked_read_only" if exc.code == "read_only" else exc.code
                self.audit.append("confirm_action", outcome, action_id=action_id,
                                  screen_id=current.screen_id, confirmed_by=decision.confirmed_by)
                raise
            kw: dict[str, object] = {
                "action_id": action.action_id,
                "key": action.key,
                "screen_id": action.screen_id,
                "confirmed_by": decision.confirmed_by,
            }
            self._begin("confirm_action", screen_before=screen_out(current), key=action.key,
                        action_id=action.action_id)
            try:
                after = await self.port.press(Key(action.key))
            except ScreenBridgeError as exc:
                raise self._bridge_error("confirm_action", exc, **kw) from None
            self._last_screen_id = after.screen_id
            self.audit.append("confirm_action", "ok", **kw)  # type: ignore[arg-type]
            out = screen_out(after)
            self._end("ok", out)
            return out

    async def deny_action(self, action_id: str, who: str) -> None:
        """A human declined a pending action (oob channel, not an MCP tool).

        Sends nothing to the 3270 session. Audited as ``rejected``; an unknown or
        expired id is audited with its own outcome and re-raised."""
        async with self._lock:
            try:
                action = self.gate.deny_oob(action_id, who)
            except GateError as exc:
                self.audit.append("deny_action", exc.code, action_id=action_id, confirmed_by=f"oob:{who}")
                raise
            self.audit.append("deny_action", "rejected", action_id=action.action_id, key=action.key,
                              screen_id=action.screen_id, confirmed_by=f"oob:{who}")

    def audit_entries(self, limit: int | None = None) -> list[AuditEntry]:
        return self.audit.read(limit)


def _ref_str(ref: int | tuple[int, int]) -> str:
    return str(ref) if isinstance(ref, int) else f"{ref[0]},{ref[1]}"


def _resolve(screen: ScreenModel, ref: int | tuple[int, int]):
    from seance_bridge import ScreenParser

    if isinstance(ref, int):
        return next((f for f in screen.fields if f.index == ref), None)
    return ScreenParser.field_at(screen, ref[0], ref[1])
