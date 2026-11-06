"""SeanceHub: everything behind the websocket, with no HTTP in it.

The hub owns the Session (events, seq, connections), the connected system's
runtime (MCP server, tool broker, mapper, confirm broker, agent loop) and the
handling of each client message. ``api.py`` is a thin transport over it, so the
rules here (who may decide, one turn at a time, nothing sent to a live host
without permission) are testable without a socket.

Trust model in one place: only a message from the **controller** connection can
start a turn, connect a system, decide a confirmation or cancel. An observer's
control message gets ``observer_only`` and reaches no component that can touch
the 3270 session.
"""
from __future__ import annotations

import json
import secrets
import time
from collections.abc import Callable, Mapping
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
from pydantic import ValidationError

from seance_mcp.audit import AuditLog
from seance_mcp.paths import resolve_path
from seance_mcp.safety import GateError

from .apps import AppRegistry, SystemRuntime, build_runtime
from .config import Settings
from .confirm import ConfirmBroker
from .events import (
    AckData,
    ConnectSystem,
    ConfirmDecision,
    CancelTurn,
    ErrorData,
    Hello,
    LlmInfo,
    Ping,
    PongData,
    ScreenData,
    SessionStateData,
    ToolCounts,
    UserMessage,
    client_message_adapter,
)
from .llm.base import LlmProvider
from .llm.factory import build_llm
from .loop import AgentLoop
from .mapper import EventMapper
from .session import Connection, Session
from .tools import ToolBroker

TOKEN_TTL_S = 15 * 60


@dataclass
class Live:
    """A connected system and everything that serves it."""

    rt: SystemRuntime
    broker: ToolBroker
    mapper: EventMapper
    confirm: ConfirmBroker
    loop: AgentLoop
    stop: anyio.Event
    done: anyio.Event


class SeanceHub:
    def __init__(
        self,
        settings: Settings,
        registry: AppRegistry,
        *,
        session_id: str | None = None,
        clock: Callable[[], float] = time.monotonic,
        env: Mapping[str, str] | None = None,
        llm: tuple[LlmProvider | None, bool] | None = None,
    ):
        self.settings, self.registry, self._env = settings, registry, env
        self.session_id = session_id or "s_" + secrets.token_hex(2)
        self._clock = clock
        self.session = Session(self.session_id, ring_size=settings.ring_size, event_log=settings.event_log,
                               clock=clock)
        self.llm, self.llm_available = llm if llm is not None else build_llm(settings)
        self._tokens: dict[str, float] = {}
        self.tg: anyio.abc.TaskGroup | None = None
        self.live: Live | None = None
        self.state = "disconnected"
        self._busy_connecting = False

    # -- tokens (REQ-002) ---------------------------------------------------

    def issue_token(self) -> str:
        now = self._clock()
        self._tokens = {t: exp for t, exp in self._tokens.items() if exp > now}
        tok = secrets.token_urlsafe(24)
        self._tokens[tok] = now + TOKEN_TTL_S
        return tok

    def token_valid(self, token: str) -> bool:
        now = self._clock()
        return any(secrets.compare_digest(token, t) and exp > now for t, exp in self._tokens.items())

    # -- state --------------------------------------------------------------

    def state_data(self, *, resync: bool = False) -> SessionStateData:
        business, generic = self.live.broker.counts() if self.live else (0, 0)
        return SessionStateData(
            state=self.state,  # type: ignore[arg-type]
            app_id=self.live.rt.app_id if self.live else None,
            read_only=not self.settings.allow_commit,
            confirm_mode="oob",
            llm=LlmInfo(provider=self.llm.name if self.llm else self.settings.llm_provider.value,
                        model=self.llm.model if self.llm else self.settings.llm_model,
                        available=self.llm_available),
            tools=ToolCounts(business=business, generic=generic),
            resync=resync,
            controller=True,
        )

    def emit_state(self, **kw: Any) -> None:
        self.session.emit(self.state_data(**kw), turn_id=None)

    def error(self, code: str, message: str, ref: str | None = None, recoverable: bool = True) -> None:
        self.session.emit(ErrorData(code=code, message=message, recoverable=recoverable, ref=ref), turn_id=None)

    # -- handshake (contracts 4.1, 4.4) -------------------------------------

    def attach(self, conn_id: str, token: str, resume_from: int | None) -> Connection:
        """Complete a ``hello``: state, then a replay or a snapshot.

        * ``resume_from`` inside the ring: replay ``seq > resume_from`` (contracts 4.4).
        * no ``resume_from`` and the ring still starts at seq 1: replay the whole session,
          so the client gets a baseline from seq 1 and the full log.
        * otherwise: ``session_state{resync:true}`` and a ``screen{snapshot}``. A client
          with no history must get a baseline; a mid-session event with no resync is a gap
          (found running C's reducer live).

        The fresh ``session_state`` is emitted *before* the connection joins and delivered
        as the tail of the replay, so the connection sees each event exactly once, in order."""
        s = self.session
        resuming = resume_from is not None
        start = resume_from if resuming else 0
        if start is not None and start <= s.last_seq and s.can_replay(start) and (resuming or s.ring_min_seq in (None, 1)):
            self.emit_state()
            conn = s.add_connection(conn_id, token, resuming=resuming)
            s.deliver_to(conn, s.replay(start))
            return conn
        first = s.last_seq + 1
        self.emit_state(resync=True)
        if self.live is not None and self.live.mapper.last_screen is not None:
            s.emit(ScreenData(phase="snapshot", tool_call_id=None, screen=self.live.mapper.last_screen), turn_id=None)
        conn = s.add_connection(conn_id, token, resuming=resuming)
        s.deliver_to(conn, s.replay(first - 1))
        return conn
    def detach(self, conn_id: str) -> None:
        self.session.remove_connection(conn_id)

    # -- message handling ---------------------------------------------------

    async def handle(self, conn: Connection, text: str) -> None:
        try:
            msg = client_message_adapter.validate_json(text)
        except ValidationError:
            self.error("bad_message", "that message is not valid", _ref_of(text))
            return
        if isinstance(msg, Hello):
            self.error("bad_message", "hello was already received", msg.id)
        elif isinstance(msg, Ping):
            self.session.emit(AckData(ref=msg.id), turn_id=None)
            self.session.emit(PongData(), turn_id=None)
        elif not conn.controller or not self.session.is_controller(conn.conn_id):
            self.error("observer_only", "only the controller can do that", msg.id)
        elif isinstance(msg, ConnectSystem):
            await self._connect_system(msg)
        elif isinstance(msg, UserMessage):
            self._user_message(msg)
        elif isinstance(msg, ConfirmDecision):
            await self._confirm_decision(msg)
        elif isinstance(msg, CancelTurn):
            self._cancel(msg)

    def _user_message(self, msg: UserMessage) -> None:
        live = self.live
        if live is None or self.state != "connected":
            self.error("not_connected", "connect a system first", msg.id)
            return
        if live.loop.busy:
            self.error("turn_in_progress", "a request is already running", msg.id)
            return
        self.session.emit(AckData(ref=msg.id), turn_id=None)
        assert self.tg is not None
        self.tg.start_soon(live.loop.run_turn, msg.text)

    async def _confirm_decision(self, msg: ConfirmDecision) -> None:
        live = self.live
        if live is None or live.confirm.pending_action_id != msg.action_id:
            # Unknown, expired, resolved or superseded: an error, no effect on the system.
            self.error("unknown_action", "no pending action with that id", msg.id)
            return
        self.session.emit(AckData(ref=msg.id), turn_id=None)
        await live.confirm.decide(msg.action_id, msg.decision, session_id=self.session_id)

    def _cancel(self, msg: CancelTurn) -> None:
        live = self.live
        if live is None or live.loop.current_turn_id() != msg.turn_id:
            self.error("bad_message", "no such running request", msg.id)
            return
        self.session.emit(AckData(ref=msg.id), turn_id=None)
        live.loop.cancel()

    # -- connecting a system (REQ-022, REQ-023) ----------------------------------

    async def _connect_system(self, msg: ConnectSystem) -> None:
        entry = self.registry.get(msg.app_id)
        if entry is None:
            self.error("unknown_app", f"unknown app {msg.app_id!r}", msg.id)
            return
        if self._busy_connecting or (self.live and self.live.loop.busy):
            self.error("session_busy", "a request or connection is in progress", msg.id)
            return
        self._busy_connecting = True
        try:
            await self._close_live()
            try:
                rt = build_runtime(entry, self.registry, self.settings, env=self._env)
            except GateError as exc:  # live_not_allowed / unknown_app: nothing was built or opened
                self.error(exc.code, exc.message, msg.id)
                return
            self.session.emit(AckData(ref=msg.id), turn_id=None)
            self.state = "connecting"
            self.emit_state()
            live = await self._start_live(rt)
            try:
                screen = await rt.service.connect()
            except GateError as exc:
                await self._stop(live)
                self.live, self.state = None, "error"
                self.error(exc.code, exc.message, msg.id)
                self.emit_state()
                return
            self.live = live
            live.mapper.flush(None)
            live.mapper.last_screen = screen
            self.state = "connected"
            self.emit_state()
            self.session.emit(ScreenData(phase="snapshot", tool_call_id=None, screen=screen), turn_id=None)
        finally:
            self._busy_connecting = False

    async def _start_live(self, rt: SystemRuntime) -> Live:
        assert self.tg is not None
        box: dict[str, Any] = {}
        ready, stop, done = anyio.Event(), anyio.Event(), anyio.Event()

        async def run() -> None:
            try:
                async with ToolBroker.start(rt.server, generic_tools=self.settings.generic_tools) as broker:
                    mapper = EventMapper(self.session, turn_id_getter=lambda: box["loop"].current_turn_id())
                    mapper.attach(rt.service)
                    confirm = ConfirmBroker(rt.service, self.session, mapper)
                    box["loop"] = AgentLoop(
                        session=self.session, broker=broker, confirm=confirm, mapper=mapper, service=rt.service,
                        llm=self.llm, llm_available=self.llm_available, max_steps=self.settings.max_steps,
                        max_tool_errors=self.settings.max_tool_errors,
                        turn_timeout_s=self.settings.turn_timeout_s, commit_hints=rt.commit_hints,
                        on_error_code=self._on_error_code)
                    box["live"] = Live(rt, broker, mapper, confirm, box["loop"], stop, done)
                    ready.set()
                    await stop.wait()
                    mapper.detach()
                    try:
                        await rt.service.disconnect()
                    except Exception:  # noqa: BLE001 - closing a dead session must not raise
                        pass
            finally:
                ready.set()
                done.set()

        self.tg.start_soon(run)
        await ready.wait()
        if "live" not in box:
            raise GateError("bridge_error", "could not start the tool server")
        return box["live"]

    async def _stop(self, live: Live) -> None:
        live.stop.set()
        await live.done.wait()

    async def _close_live(self) -> None:
        if self.live is not None:
            live, self.live = self.live, None
            await self._stop(live)
            self.state = "disconnected"

    def _on_error_code(self, code: str) -> None:
        if code == "session_lost":
            self.state = "session_lost"
            self.emit_state()

    async def shutdown(self) -> None:
        await self._close_live()

    # -- REST helpers -------------------------------------------------------

    def audit(self, limit: int) -> dict[str, Any]:
        try:
            log = AuditLog(resolve_path(self.settings.audit_log_path))
        except ValueError:  # the chain fails verification: report it, never repair it
            return {"entries": [], "chain_ok": False, "broken_seq": None}
        broken = log.verify()
        entries = log.read(limit)
        return {"entries": [e.model_dump(mode="json") for e in entries], "chain_ok": broken is None,
                "broken_seq": broken}


def _ref_of(text: str) -> str | None:
    try:
        obj = json.loads(text)
        v = obj.get("id") if isinstance(obj, dict) else None
        return v if isinstance(v, str) and 0 < len(v) <= 64 else None
    except ValueError:
        return None
