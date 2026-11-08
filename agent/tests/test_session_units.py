"""Unit tests for Session: seq, ring buffer, resume, controller/observer, overrun.

No transport; a Connection is just a bounded queue. These pin the behaviours
REQ-003 and REQ-004 call for before the websocket is wired in task 6.
"""
from __future__ import annotations

import anyio

from seance_agent.events import AckData, ThinkingData
from seance_agent.session import Overrun, Session


def _drain(conn) -> list[dict]:
    out: list[dict] = []
    while True:
        try:
            out.append(conn._receive.receive_nowait())
        except anyio.WouldBlock:
            return out


def test_seq_is_gap_free_and_starts_at_one() -> None:
    s = Session("s_01")
    e1 = s.emit(AckData(ref="a"), turn_id=None)
    e2 = s.emit(ThinkingData(summary="hi"), turn_id="t_01")
    assert (e1["seq"], e2["seq"]) == (1, 2)
    assert s.last_seq == 2


def test_first_connection_is_controller_rest_are_observers() -> None:
    s = Session("s_01")
    c = s.add_connection("c1")
    o = s.add_connection("o1")
    assert c.controller is True and o.controller is False
    assert s.is_controller("c1") and not s.is_controller("o1")


def test_controller_role_frees_up_when_controller_leaves() -> None:
    s = Session("s_01")
    s.add_connection("c1")
    s.remove_connection("c1")
    assert not s.has_controller()
    c2 = s.add_connection("c2")
    assert c2.controller is True


def test_emit_fans_out_to_all_connections() -> None:
    s = Session("s_01")
    c = s.add_connection("c1")
    o = s.add_connection("o1")
    s.emit(AckData(ref="x"), turn_id=None)
    assert len(_drain(c)) == 1 and len(_drain(o)) == 1


def test_ring_buffer_bounds_and_replay_suffix() -> None:
    s = Session("s_01", ring_size=3)
    for i in range(5):
        s.emit(AckData(ref=str(i)), turn_id=None)
    # Only the last 3 (seq 3,4,5) are buffered.
    assert s.ring_min_seq == 3
    replayed = s.replay(3)
    assert [e["seq"] for e in replayed] == [4, 5]


def test_can_replay_true_when_in_window_false_when_evicted() -> None:
    s = Session("s_01", ring_size=3)
    for i in range(5):
        s.emit(AckData(ref=str(i)), turn_id=None)
    assert s.can_replay(4) is True          # seq 5 still buffered
    assert s.can_replay(3) is True          # seq 4,5 buffered
    assert s.can_replay(1) is False         # seq 2 was evicted
    assert s.can_replay(5) is True          # already up to date


def test_slow_connection_is_dropped_not_the_agent() -> None:
    s = Session("s_01", queue_maxsize=1)
    c = s.add_connection("c1")
    # Fill the queue (1 slot), then one more fans out and overruns -> dropped.
    s.emit(AckData(ref="1"), turn_id=None)
    s.emit(AckData(ref="2"), turn_id=None)
    assert "c1" not in s._conns  # dropped
    assert s.last_seq == 2       # the agent kept its seq counter


def test_try_send_raises_overrun_directly() -> None:
    s = Session("s_01", queue_maxsize=1)
    c = s.add_connection("c1")
    c.try_send({"seq": 1})
    import pytest

    with pytest.raises(Overrun):
        c.try_send({"seq": 2})
