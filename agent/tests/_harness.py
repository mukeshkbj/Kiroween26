"""Test harness: a real SeanceService over FakeApp, wired to a ToolBroker,
EventMapper and Session, with no network and no LLM.

Every agent test that needs the full tool path uses ``agent_harness`` so the
service, gate, audit log and fake app are the real ones (only the bridge and the
model are doubles). The golden key policy for fake_insurance is written to a temp
file so ``confirm`` ENTER is the only commit.
"""
from __future__ import annotations

import json
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from seance_mcp.config import ConfirmMode, Settings
from seance_mcp.contracts.golden import golden_policy
from seance_mcp.factory import build_service
from seance_mcp.fake import FakeApp, fake_insurance
from seance_mcp.service import SeanceService

from seance_agent.mapper import EventMapper
from seance_agent.session import Session
from seance_agent.tools import ToolBroker


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Harness:
    app: FakeApp
    service: SeanceService
    broker: ToolBroker
    mapper: EventMapper
    session: Session
    turn_id: str | None = "t_01"


@asynccontextmanager
async def agent_harness(
    *, allow_commit: bool = True, ttl: float = 300.0, generic_tools: bool = True, real_pack: bool = False
) -> AsyncIterator[Harness]:
    app = fake_insurance()
    tmp = Path(tempfile.mkdtemp())
    (tmp / "kp.json").write_text(json.dumps(golden_policy(app)), encoding="utf-8")
    extra: dict = {}
    if real_pack:
        pack = REPO_ROOT / "docs" / "spirit-map" / "fake-insurance"
        extra = {
            "generated_tools_path": pack / "tools.json",
            "tool_approvals_path": pack / "tool-approvals.json",
        }
    settings = Settings(
        allow_commit=allow_commit,
        confirm_mode=ConfirmMode.OOB,
        pending_ttl_s=ttl,
        audit_log_path=tmp / "audit.jsonl",
        key_policy_path=tmp / "kp.json",
        **extra,
    )
    server, service = build_service(settings, app, audit_path=tmp / "audit.jsonl")
    session = Session("s_01", ring_size=10_000)
    harness_box: dict[str, Harness] = {}
    mapper = EventMapper(session, turn_id_getter=lambda: harness_box["h"].turn_id)
    mapper.attach(service)
    async with ToolBroker.start(server, generic_tools=generic_tools) as broker:
        h = Harness(app=app, service=service, broker=broker, mapper=mapper, session=session)
        harness_box["h"] = h
        try:
            yield h
        finally:
            mapper.detach()


# ---------------------------------------------------------------- loop helpers

import anyio  # noqa: E402

from seance_agent.confirm import ConfirmBroker  # noqa: E402
from seance_agent.loop import AgentLoop  # noqa: E402

from ._stream import check_stream  # noqa: E402


def make_loop(h: Harness, llm, **kw) -> AgentLoop:
    """AgentLoop over the harness. ``h.turn_id`` follows the loop's current turn."""
    confirm = ConfirmBroker(h.service, h.session, h.mapper)
    loop = AgentLoop(session=h.session, broker=h.broker, confirm=confirm, mapper=h.mapper,
                     service=h.service, llm=llm, **kw)
    h.turn_id = None
    h.mapper._turn_id = loop.current_turn_id  # noqa: SLF001
    loop.confirm_broker = confirm  # type: ignore[attr-defined]
    return loop


def events(h: Harness, type_: str | None = None) -> list[dict]:
    return [e for e in h.session._ring if type_ is None or e["type"] == type_]


async def run_with_decision(h: Harness, loop: AgentLoop, text: str, decision: str | None) -> str:
    """Run a turn; when ``confirmation_required`` appears, apply ``decision`` as the
    controller (``approve``/``deny``) or do nothing (None)."""
    out: dict[str, str] = {}

    async with anyio.create_task_group() as tg:
        async def turn() -> None:
            out["reason"] = await loop.run_turn(text)
            tg.cancel_scope.cancel()

        async def human() -> None:
            while True:
                await anyio.sleep(0.01)
                req = events(h, "confirmation_required")
                if req and decision is not None:
                    await loop.confirm_broker.decide(  # type: ignore[attr-defined]
                        req[-1]["data"]["action_id"], decision, session_id="s_01")
                    return

        tg.start_soon(turn)
        tg.start_soon(human)
    return out["reason"]


def assert_stream_ok(h: Harness) -> None:
    check_stream(events(h))
