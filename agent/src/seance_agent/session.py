"""Session: the fan-out point between the agent loop and the browser connections.

One ``Session`` per agent process (the demo is single-session). It owns:

* the monotonic, gap-free ``seq`` counter (contracts 4.2: starts at 1, strictly
  increasing per ``session_id``);
* a ring buffer of the last ``ring_size`` serialised events, for resume (4.4);
* the set of connections, exactly one of which is the **controller** (the first
  valid ``hello``); the rest are **observers** (REQ-003);
* an optional append-only JSONL event log (``AGENT_EVENT_LOG``, gitignored).

Transport-free on purpose (no FastAPI import here) so it is unit-testable: a
``Connection`` is just an id, a role and a bounded queue. ``api.py`` owns the
websocket and pumps each connection's queue to the socket.

Backpressure (REQ-004): each connection has a bounded queue. A connection whose
queue is full is marked ``overrun`` and dropped; it never stalls the agent. The
ring buffer and ``seq`` are unaffected, so a dropped client can reconnect and
resume.
"""
from __future__ import annotations

import json
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
from pydantic import BaseModel

from .events import (
    LlmInfo,
    PROTOCOL_VERSION,
    ScreenData,
    SessionStateData,
    ToolCounts,
    iso_ms,
    make_event,
    server_event_adapter,
)

DEFAULT_QUEUE_MAXSIZE = 500


class Overrun(Exception):
    """A connection's send queue was full: the client is too slow and is dropped."""


@dataclass
class Connection:
    """One websocket's view. ``controller`` is True for the single controller."""

    conn_id: str
    controller: bool
    _queue: anyio.streams.memory.MemoryObjectSendStream[dict[str, Any]]
    _receive: anyio.streams.memory.MemoryObjectReceiveStream[dict[str, Any]]
    overrun: bool = False
    closed: bool = False

    def try_send(self, event: dict[str, Any]) -> None:
        """Enqueue a serialised event without blocking. Full queue -> Overrun."""
        if self.closed:
            return
        try:
            self._queue.send_nowait(event)
        except anyio.WouldBlock:
            self.overrun = True
            raise Overrun(self.conn_id) from None
        except anyio.BrokenResourceError:
            self.closed = True

    async def events(self) -> Iterator[dict[str, Any]]:
        """Async iterator the transport pumps to the websocket."""
        async with self._receive:
            async for event in self._receive:
                yield event

    def close(self) -> None:
        self.closed = True
        self._queue.close()


class Session:
    """Owns seq, the ring buffer, the connection set and resume logic."""

    def __init__(
        self,
        session_id: str,
        *,
        ring_size: int = 1000,
        queue_maxsize: int = DEFAULT_QUEUE_MAXSIZE,
        event_log: Path | None = None,
    ):
        self.session_id = session_id
        self._seq = 0
        self._ring: deque[dict[str, Any]] = deque(maxlen=ring_size)
        self._conns: dict[str, Connection] = {}
        self._queue_maxsize = queue_maxsize
        self._event_log = event_log
        self._controller_id: str | None = None
        if event_log is not None:
            event_log.parent.mkdir(parents=True, exist_ok=True)

    # -- sequence / ring ---------------------------------------------------

    @property
    def last_seq(self) -> int:
        return self._seq

    @property
    def ring_min_seq(self) -> int | None:
        """The lowest seq still replayable, or None if the ring is empty."""
        return self._ring[0]["seq"] if self._ring else None

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    # -- connections -------------------------------------------------------

    @property
    def controller_id(self) -> str | None:
        return self._controller_id

    def has_controller(self) -> bool:
        cid = self._controller_id
        return cid is not None and cid in self._conns and not self._conns[cid].closed

    def add_connection(self, conn_id: str) -> Connection:
        """Register a connection. The first one (while no live controller exists)
        becomes the controller (contracts 4.1); the rest are observers."""
        send, receive = anyio.create_memory_object_stream(max_buffer_size=self._queue_maxsize)
        is_controller = not self.has_controller()
        conn = Connection(conn_id=conn_id, controller=is_controller, _queue=send, _receive=receive)
        self._conns[conn_id] = conn
        if is_controller:
            self._controller_id = conn_id
        return conn

    def remove_connection(self, conn_id: str) -> None:
        conn = self._conns.pop(conn_id, None)
        if conn is not None:
            conn.close()
        if self._controller_id == conn_id:
            self._controller_id = None

    def is_controller(self, conn_id: str) -> bool:
        return self._controller_id == conn_id

    # -- emit --------------------------------------------------------------

    def emit(self, data: BaseModel, *, turn_id: str | None, ts: str | None = None) -> dict[str, Any]:
        """Stamp a data payload into an envelope, buffer it, log it and fan it out
        to every connection. Returns the serialised event. The agent loop and the
        confirm broker call this; they never build an envelope themselves."""
        event = make_event(
            data, seq=self._next_seq(), session_id=self.session_id, turn_id=turn_id, ts=ts or iso_ms()
        )
        payload = event.model_dump(mode="json")
        self._ring.append(payload)
        self._write_log(payload)
        self._fan_out(payload)
        return payload

    def _fan_out(self, payload: dict[str, Any]) -> None:
        for conn_id, conn in list(self._conns.items()):
            try:
                conn.try_send(payload)
            except Overrun:
                # Drop the slow client; the agent keeps streaming to everyone else.
                self.remove_connection(conn_id)

    def _write_log(self, payload: dict[str, Any]) -> None:
        if self._event_log is None:
            return
        with open(self._event_log, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    # -- resume (contracts 4.4) -------------------------------------------

    def can_replay(self, resume_from: int) -> bool:
        """True when every seq after ``resume_from`` is still in the ring."""
        if resume_from >= self._seq:
            return True  # nothing to replay; already up to date
        lo = self.ring_min_seq
        return lo is not None and resume_from + 1 >= lo

    def replay(self, resume_from: int) -> list[dict[str, Any]]:
        """The buffered events with ``seq > resume_from`` (contracts 4.2: the client
        ignores ``seq <= last_seq``, and a replay is a suffix of the stream)."""
        return [e for e in self._ring if e["seq"] > resume_from]

    def deliver_to(self, conn: Connection, events: list[dict[str, Any]]) -> None:
        """Push a batch (e.g. a replay) to one connection only."""
        for e in events:
            try:
                conn.try_send(e)
            except Overrun:
                self.remove_connection(conn.conn_id)
                return

    # -- convenience builders used by api/loop ----------------------------

    def session_state_data(
        self,
        *,
        state: str,
        app_id: str | None,
        read_only: bool,
        llm: LlmInfo,
        tools: ToolCounts,
        controller: bool,
        resync: bool = False,
    ) -> SessionStateData:
        return SessionStateData(
            state=state,  # type: ignore[arg-type]
            app_id=app_id,
            read_only=read_only,
            confirm_mode="oob",
            llm=llm,
            tools=tools,
            resync=resync,
            controller=controller,
        )

    @staticmethod
    def snapshot_data(screen: Any) -> ScreenData:
        """A ``screen{phase:snapshot}`` payload for connect/resync (ScreenOut in)."""
        return ScreenData(phase="snapshot", tool_call_id=None, screen=screen)


__all__ = [
    "Session",
    "Connection",
    "Overrun",
    "DEFAULT_QUEUE_MAXSIZE",
    "PROTOCOL_VERSION",
    "server_event_adapter",
]
