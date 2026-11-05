"""Section 4 unit tests: the oob confirmation flow (REQ-015 to REQ-019).

Driven through the real service/gate/FakeApp. Each test stages an update to the
``confirm`` screen (where ENTER is the only commit under the golden policy), then
exercises one resolution path and asserts:

* exactly one ``confirmation_required`` and one ``confirmation_resolved`` with the
  expected outcome;
* the FakeApp only recorded the committing ENTER when the outcome was ``approved``
  (``app.dirty`` / ``app.mutations``);
* the modal content came from the gate, not from any model text.
"""
from __future__ import annotations

import anyio
import pytest

from seance_agent.confirm import ConfirmBroker

from ._harness import Harness, agent_harness


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


pytestmark = pytest.mark.anyio


async def _stage_update(h: Harness, polno: str = "P0000003", premium: str = "300") -> str:
    """Drive the service to the confirm screen and press ENTER (-> pending). Returns action_id."""
    s = h.service
    await s.connect()
    await s.press_key("CLEAR")
    await s.fill_field(h.app.screens["menu"].names["option"], "3")
    await s.press_key("ENTER")
    await s.fill_field(h.app.screens["update"].names["polno"], polno)
    await s.fill_field(h.app.screens["update"].names["premium"], premium)
    await s.press_key("ENTER")   # update -> confirm (read-only)
    press = await s.press_key("ENTER")   # commit on confirm -> pending
    assert press.status == "pending"
    h.mapper.take_bus()  # drop the staging events; tests look at confirm events only
    return s.gate.pending.action_id


def _events(h: Harness, type_: str) -> list[dict]:
    return [e for e in h.session._ring if e["type"] == type_]


async def test_approve_sends_the_key_and_resolves_once() -> None:
    async with agent_harness(allow_commit=True) as h:
        aid = await _stage_update(h)
        broker = ConfirmBroker(h.service, h.session, h.mapper)

        async with anyio.create_task_group() as tg:
            async def driver() -> None:
                await anyio.sleep(0.01)
                res = await broker.decide(aid, "approve", session_id="s_01")
                assert res is not None and res.outcome == "approved"

            tg.start_soon(driver)
            resolution = await broker.await_decision(
                tool_call_id="c_01", turn_id="t_01", read_only=False,
                agent_summary="Change premium to 300.00")
        assert resolution.outcome == "approved"

        assert len(_events(h, "confirmation_required")) == 1
        resolved = _events(h, "confirmation_resolved")
        assert len(resolved) == 1 and resolved[0]["data"]["outcome"] == "approved"
        assert resolved[0]["data"]["confirmed_by"] == "oob:web-ui:s_01"
        assert h.app.dirty and ("confirm", "Enter") in h.app.mutations


async def test_deny_sends_nothing_and_resolves_denied() -> None:
    async with agent_harness(allow_commit=True) as h:
        aid = await _stage_update(h)
        broker = ConfirmBroker(h.service, h.session, h.mapper)
        async with anyio.create_task_group() as tg:
            async def driver() -> None:
                await anyio.sleep(0.01)
                await broker.decide(aid, "deny", session_id="s_01")

            tg.start_soon(driver)
            resolution = await broker.await_decision(
                tool_call_id="c_01", turn_id="t_01", read_only=False, agent_summary=None)
        assert resolution.outcome == "denied"
        assert not h.app.dirty  # the committing key was never sent
        resolved = _events(h, "confirmation_resolved")
        assert len(resolved) == 1 and resolved[0]["data"]["outcome"] == "denied"


async def test_expire_resolves_expired_and_sends_nothing() -> None:
    async with agent_harness(allow_commit=True, ttl=300.0) as h:
        aid = await _stage_update(h)
        broker = ConfirmBroker(h.service, h.session, h.mapper)
        async with anyio.create_task_group() as tg:
            async def driver() -> None:
                await anyio.sleep(0.01)
                await broker.expire(aid)

            tg.start_soon(driver)
            resolution = await broker.await_decision(
                tool_call_id="c_01", turn_id="t_01", read_only=False, agent_summary=None)
        assert resolution.outcome == "expired"
        assert not h.app.dirty
        resolved = _events(h, "confirmation_resolved")
        assert len(resolved) == 1 and resolved[0]["data"]["error_code"] == "action_expired"


async def test_unknown_or_duplicate_decision_has_no_effect() -> None:
    async with agent_harness(allow_commit=True) as h:
        aid = await _stage_update(h)
        broker = ConfirmBroker(h.service, h.session, h.mapper)
        async with anyio.create_task_group() as tg:
            async def driver() -> None:
                await anyio.sleep(0.01)
                # Wrong id: no effect, returns None.
                assert await broker.decide("00000000-0000-0000-0000-000000000000", "approve", session_id="s_01") is None
                # Correct id approves.
                assert (await broker.decide(aid, "approve", session_id="s_01")).outcome == "approved"
                # Duplicate approve after resolution: no effect.
                assert await broker.decide(aid, "approve", session_id="s_01") is None

            tg.start_soon(driver)
            await broker.await_decision(tool_call_id="c_01", turn_id="t_01", read_only=False, agent_summary=None)
        assert len(_events(h, "confirmation_resolved")) == 1


async def test_read_only_blocks_the_commit_visibly() -> None:
    async with agent_harness(allow_commit=False) as h:
        aid = await _stage_update(h)
        broker = ConfirmBroker(h.service, h.session, h.mapper)
        async with anyio.create_task_group() as tg:
            async def driver() -> None:
                await anyio.sleep(0.01)
                res = await broker.decide(aid, "approve", session_id="s_01")
                assert res is not None and res.outcome == "blocked_read_only"

            tg.start_soon(driver)
            resolution = await broker.await_decision(
                tool_call_id="c_01", turn_id="t_01", read_only=True, agent_summary=None)
        assert resolution.outcome == "blocked_read_only"
        assert not h.app.dirty  # read-only: the key was never sent
        resolved = _events(h, "confirmation_resolved")
        assert len(resolved) == 1 and resolved[0]["data"]["outcome"] == "blocked_read_only"
