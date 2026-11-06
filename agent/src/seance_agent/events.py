"""Pydantic models for every websocket message in docs/contracts.md section 4.

Two directions:

* **Server -> client** events (``ServerEvent``): the agent emits these. Each is an
  envelope ``{v, type, seq, ts, session_id, turn_id, data}`` with a typed ``data``
  payload. ``make_event`` stamps the envelope so the rest of the agent only ever
  builds a ``data`` model.
* **Client -> server** messages (``ClientMessage``): the UI sends these; the agent
  parses and validates them.

The shared data shapes (``ScreenOut``, ``FieldOut``, ``FieldSnap``, ``AuditEntry``)
are imported from ``seance_mcp`` rather than re-declared: contracts section 3 names
those Pydantic models the single source of truth, and importing them means a change
there is a type error here instead of silent drift.

A conformance test (``tests/test_events_conformance.py``) round-trips every example
in ``docs/contracts/examples/events/`` through these models and the generated JSON
Schemas, so this file cannot drift from the contract unnoticed (REQ-030).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from seance_mcp.audit import AuditEntry
from seance_mcp.safety import FieldSnap
from seance_mcp.screens import FieldOut, ScreenOut

PROTOCOL_VERSION = 1

__all__ = [
    "PROTOCOL_VERSION",
    "iso_ms",
    "make_event",
    # data payloads
    "SessionStateData", "LlmInfo", "ToolCounts", "AckData", "TurnStartedData",
    "ThinkingData", "AssistantDeltaData", "AssistantMessageData", "ToolCallData",
    "ScreenData", "FieldFocusData", "ToolResultData", "ConfirmationRequiredData",
    "ConfirmationResolvedData", "AuditEntryData", "TurnFinishedData", "Usage",
    "ErrorData", "PongData",
    # events
    "SessionStateEvent", "AckEvent", "TurnStartedEvent", "ThinkingEvent",
    "AssistantDeltaEvent", "AssistantMessageEvent", "ToolCallEvent", "ScreenEvent",
    "FieldFocusEvent", "ToolResultEvent", "ConfirmationRequiredEvent",
    "ConfirmationResolvedEvent", "AuditEntryEvent", "TurnFinishedEvent",
    "ErrorEvent", "PongEvent", "ServerEvent", "server_event_adapter",
    # client messages
    "Hello", "ConnectSystem", "UserMessage", "ConfirmDecision", "CancelTurn",
    "Ping", "ClientMessage", "client_message_adapter",
    "AuditEntry", "FieldSnap", "FieldOut", "ScreenOut",
]


def iso_ms(now: datetime | None = None) -> str:
    """Envelope timestamp: ISO-8601 UTC with milliseconds and a literal ``Z``."""
    dt = (now or datetime.now(UTC)).astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


# ---------------------------------------------------------------- data payloads


class LlmInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: str
    model: str
    available: bool


class ToolCounts(BaseModel):
    model_config = ConfigDict(frozen=True)
    business: int = Field(ge=0)
    generic: int = Field(ge=0)


class SessionStateData(BaseModel):
    model_config = ConfigDict(frozen=True)
    state: Literal["disconnected", "connecting", "connected", "session_lost", "error"]
    app_id: str | None
    read_only: bool
    confirm_mode: Literal["oob"]
    llm: LlmInfo
    tools: ToolCounts
    resync: bool = False
    controller: bool = True


class AckData(BaseModel):
    model_config = ConfigDict(frozen=True)
    ref: str


class TurnStartedData(BaseModel):
    model_config = ConfigDict(frozen=True)
    user_message_id: str


class ThinkingData(BaseModel):
    model_config = ConfigDict(frozen=True)
    summary: str = Field(max_length=300)


class AssistantDeltaData(BaseModel):
    model_config = ConfigDict(frozen=True)
    message_id: str
    text: str


class AssistantMessageData(BaseModel):
    model_config = ConfigDict(frozen=True)
    message_id: str
    text: str


class ToolCallData(BaseModel):
    model_config = ConfigDict(frozen=True)
    tool_call_id: str
    tool: str
    kind: Literal["business", "generic"]
    arguments: dict[str, Any]
    may_commit: bool | None


class ScreenData(BaseModel):
    model_config = ConfigDict(frozen=True)
    phase: Literal["before", "after", "snapshot"]
    tool_call_id: str | None
    screen: ScreenOut


class FieldFocusData(BaseModel):
    model_config = ConfigDict(frozen=True)
    tool_call_id: str
    step: int = Field(ge=0)
    mode: Literal["read", "fill", "key"]
    screen_id: str
    field_index: int | None
    row: int | None = Field(default=None, ge=0, lt=24)
    col: int | None = Field(default=None, ge=0, lt=80)
    length: int | None = Field(default=None, ge=0)
    label: str | None
    key: str | None


class ToolResultData(BaseModel):
    model_config = ConfigDict(frozen=True)
    tool_call_id: str
    status: Literal["ok", "pending", "error"]
    error_code: str | None
    summary: str
    result: dict[str, Any] | None
    truncated: bool


class ConfirmationRequiredData(BaseModel):
    model_config = ConfigDict(frozen=True)
    action_id: str
    tool_call_id: str
    screen_id: str
    key: str
    field_snapshot: list[FieldSnap]
    expires_in_s: float = Field(gt=0)
    read_only: bool
    agent_summary: str | None


class ConfirmationResolvedData(BaseModel):
    model_config = ConfigDict(frozen=True)
    action_id: str
    outcome: Literal[
        "approved", "denied", "expired", "superseded", "blocked_read_only", "stale", "error"
    ]
    confirmed_by: str | None
    error_code: str | None


class AuditEntryData(BaseModel):
    model_config = ConfigDict(frozen=True)
    entry: AuditEntry


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class TurnFinishedData(BaseModel):
    model_config = ConfigDict(frozen=True)
    reason: Literal["completed", "cancelled", "error", "max_steps"]
    usage: Usage | None


class ErrorData(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    message: str
    recoverable: bool
    ref: str | None


class PongData(BaseModel):
    model_config = ConfigDict(frozen=True)


# ---------------------------------------------------------------- envelope


class _Envelope(BaseModel):
    """Common envelope fields. ``ts`` matches the contract's millisecond pattern."""

    model_config = ConfigDict(frozen=True)
    v: Literal[1] = 1
    seq: int = Field(ge=1)
    ts: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
    session_id: str
    turn_id: str | None


class SessionStateEvent(_Envelope):
    type: Literal["session_state"] = "session_state"
    data: SessionStateData


class AckEvent(_Envelope):
    type: Literal["ack"] = "ack"
    data: AckData


class TurnStartedEvent(_Envelope):
    type: Literal["turn_started"] = "turn_started"
    data: TurnStartedData


class ThinkingEvent(_Envelope):
    type: Literal["thinking"] = "thinking"
    data: ThinkingData


class AssistantDeltaEvent(_Envelope):
    type: Literal["assistant_delta"] = "assistant_delta"
    data: AssistantDeltaData


class AssistantMessageEvent(_Envelope):
    type: Literal["assistant_message"] = "assistant_message"
    data: AssistantMessageData


class ToolCallEvent(_Envelope):
    type: Literal["tool_call"] = "tool_call"
    data: ToolCallData


class ScreenEvent(_Envelope):
    type: Literal["screen"] = "screen"
    data: ScreenData


class FieldFocusEvent(_Envelope):
    type: Literal["field_focus"] = "field_focus"
    data: FieldFocusData


class ToolResultEvent(_Envelope):
    type: Literal["tool_result"] = "tool_result"
    data: ToolResultData


class ConfirmationRequiredEvent(_Envelope):
    type: Literal["confirmation_required"] = "confirmation_required"
    data: ConfirmationRequiredData


class ConfirmationResolvedEvent(_Envelope):
    type: Literal["confirmation_resolved"] = "confirmation_resolved"
    data: ConfirmationResolvedData


class AuditEntryEvent(_Envelope):
    type: Literal["audit_entry"] = "audit_entry"
    data: AuditEntryData


class TurnFinishedEvent(_Envelope):
    type: Literal["turn_finished"] = "turn_finished"
    data: TurnFinishedData


class ErrorEvent(_Envelope):
    type: Literal["error"] = "error"
    data: ErrorData


class PongEvent(_Envelope):
    type: Literal["pong"] = "pong"
    data: PongData


ServerEvent = Annotated[
    Union[
        SessionStateEvent, AckEvent, TurnStartedEvent, ThinkingEvent,
        AssistantDeltaEvent, AssistantMessageEvent, ToolCallEvent, ScreenEvent,
        FieldFocusEvent, ToolResultEvent, ConfirmationRequiredEvent,
        ConfirmationResolvedEvent, AuditEntryEvent, TurnFinishedEvent,
        ErrorEvent, PongEvent,
    ],
    Field(discriminator="type"),
]

server_event_adapter: TypeAdapter[Any] = TypeAdapter(ServerEvent)

# data payload -> event class, so make_event can wrap a payload into its envelope.
_EVENT_FOR_DATA: dict[type, Any] = {
    SessionStateData: SessionStateEvent,
    AckData: AckEvent,
    TurnStartedData: TurnStartedEvent,
    ThinkingData: ThinkingEvent,
    AssistantDeltaData: AssistantDeltaEvent,
    AssistantMessageData: AssistantMessageEvent,
    ToolCallData: ToolCallEvent,
    ScreenData: ScreenEvent,
    FieldFocusData: FieldFocusEvent,
    ToolResultData: ToolResultEvent,
    ConfirmationRequiredData: ConfirmationRequiredEvent,
    ConfirmationResolvedData: ConfirmationResolvedEvent,
    AuditEntryData: AuditEntryEvent,
    TurnFinishedData: TurnFinishedEvent,
    ErrorData: ErrorEvent,
    PongData: PongEvent,
}


def make_event(
    data: BaseModel,
    *,
    seq: int,
    session_id: str,
    turn_id: str | None,
    ts: str | None = None,
) -> _Envelope:
    """Wrap a typed ``data`` payload in its envelope. The caller owns ``seq`` and
    ``turn_id``; ``ts`` defaults to now in millisecond ISO form."""
    cls = _EVENT_FOR_DATA.get(type(data))
    if cls is None:
        raise TypeError(f"no server event type for data payload {type(data).__name__}")
    return cls(seq=seq, ts=ts or iso_ms(), session_id=session_id, turn_id=turn_id, data=data)


# ---------------------------------------------------------------- client messages


class Hello(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str = Field(min_length=1, max_length=64)
    type: Literal["hello"] = "hello"
    v: Literal[1]
    client: str
    token: str
    resume_from: int | None = Field(default=None, ge=0)


class ConnectSystem(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str = Field(min_length=1, max_length=64)
    type: Literal["connect_system"] = "connect_system"
    app_id: str


class UserMessage(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str = Field(min_length=1, max_length=64)
    type: Literal["user_message"] = "user_message"
    text: str = Field(min_length=1, max_length=4000)


class ConfirmDecision(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str = Field(min_length=1, max_length=64)
    type: Literal["confirm_decision"] = "confirm_decision"
    action_id: str
    decision: Literal["approve", "deny"]


class CancelTurn(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str = Field(min_length=1, max_length=64)
    type: Literal["cancel_turn"] = "cancel_turn"
    turn_id: str


class Ping(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str = Field(min_length=1, max_length=64)
    type: Literal["ping"] = "ping"


ClientMessage = Annotated[
    Union[Hello, ConnectSystem, UserMessage, ConfirmDecision, CancelTurn, Ping],
    Field(discriminator="type"),
]

client_message_adapter: TypeAdapter[Any] = TypeAdapter(ClientMessage)
