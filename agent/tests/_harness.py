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
    *, allow_commit: bool = True, ttl: float = 300.0, generic_tools: bool = True
) -> AsyncIterator[Harness]:
    app = fake_insurance()
    tmp = Path(tempfile.mkdtemp())
    (tmp / "kp.json").write_text(json.dumps(golden_policy(app)), encoding="utf-8")
    settings = Settings(
        allow_commit=allow_commit,
        confirm_mode=ConfirmMode.OOB,
        pending_ttl_s=ttl,
        audit_log_path=tmp / "audit.jsonl",
        key_policy_path=tmp / "kp.json",
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
