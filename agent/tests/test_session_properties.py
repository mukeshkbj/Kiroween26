"""REQ-026 (stream shape): properties of the Session's seq and resume logic.

Two properties, over Hypothesis-generated emit sequences:

1. **seq is gap-free and strictly increasing**, starting at 1, whatever the mix
   and count of events, and the event in the ring carries the same seq.
2. **replay is a suffix**: for any ``resume_from`` the Session says it can replay,
   ``replay(resume_from)`` equals the tail of the full emitted stream with
   ``seq > resume_from`` (same events, same order). This is the resume guarantee
   the UI relies on after a dropped socket.

A third property drives ``check_stream`` with generated *well-formed* turns to
show the ordering checker accepts every legal interleaving the agent can emit.
"""
from __future__ import annotations

from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from seance_agent.events import (
    AckData,
    AssistantDeltaData,
    PongData,
    ThinkingData,
    TurnFinishedData,
    TurnStartedData,
)
from seance_agent.session import Session

from ._stream import check_stream

# A generated "event" is a (payload, turn_id) pair the Session will stamp.
_session_level = st.sampled_from([AckData(ref="r"), PongData()])
_turn_level = st.sampled_from([ThinkingData(summary="s"), AssistantDeltaData(message_id="m", text="t")])


@st.composite
def _emits(draw: st.DrawFn) -> list[tuple[Any, str | None]]:
    n = draw(st.integers(min_value=0, max_value=40))
    out: list[tuple[Any, str | None]] = []
    for _ in range(n):
        if draw(st.booleans()):
            out.append((draw(_session_level), None))
        else:
            out.append((draw(_turn_level), "t_01"))
    return out


@given(_emits())
def test_seq_gap_free_strictly_increasing(emits: list[tuple[Any, str | None]]) -> None:
    s = Session("s_01", ring_size=10_000)
    seqs: list[int] = []
    for data, turn in emits:
        ev = s.emit(data, turn_id=turn)
        seqs.append(ev["seq"])
    assert seqs == list(range(1, len(emits) + 1))
    assert s.last_seq == len(emits)


@given(_emits(), st.integers(min_value=0, max_value=50))
def test_replay_is_a_suffix(emits: list[tuple[Any, str | None]], resume_from: int) -> None:
    s = Session("s_01", ring_size=10_000)  # big ring: nothing evicted
    full: list[dict] = [s.emit(data, turn_id=turn) for data, turn in emits]
    if not s.can_replay(resume_from):
        return
    replayed = s.replay(resume_from)
    expected = [e for e in full if e["seq"] > resume_from]
    assert replayed == expected
    # And it really is a contiguous tail of the stream.
    assert full[len(full) - len(replayed):] == replayed


@st.composite
def _well_formed_turn(draw: st.DrawFn) -> list[dict]:
    """A legal single turn: turn_started, some middle events, one tool_call with
    exactly one tool_result, one turn_finished. Emitted through a Session so seq
    and envelopes are real."""
    s = Session("s_01", ring_size=10_000)
    s.emit(TurnStartedData(user_message_id="m_01"), turn_id="t_01")
    if draw(st.booleans()):
        s.emit(ThinkingData(summary="thinking"), turn_id="t_01")
    # One tool call + result (kept inside the turn).
    from seance_agent.events import ToolCallData, ToolResultData

    s.emit(ToolCallData(tool_call_id="c_01", tool="lookup_policy", kind="business",
                        arguments={}, may_commit=False), turn_id="t_01")
    for _ in range(draw(st.integers(min_value=0, max_value=3))):
        s.emit(AssistantDeltaData(message_id="m_02", text="x"), turn_id="t_01")
    s.emit(ToolResultData(tool_call_id="c_01", status="ok", error_code=None,
                         summary="ok", result=None, truncated=False), turn_id="t_01")
    s.emit(TurnFinishedData(reason="completed", usage=None), turn_id="t_01")
    return list(s._ring)


@given(_well_formed_turn())
def test_check_stream_accepts_well_formed_turns(events: list[dict]) -> None:
    check_stream(events)  # must not raise
