"""Build a server around a FakePort and talk to it with a real in-process MCP Client."""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
from mcp import Client
from mcp.types import ElicitResult

from seance_mcp.audit import AuditLog
from seance_mcp.config import ConfirmMode, Settings
from seance_mcp.safety import KeyPolicy, SafetyGate
from seance_mcp.server import build_server
from seance_mcp.service import SeanceService

from fakes import FakePort


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@dataclass
class Rig:
    port: FakePort
    service: SeanceService
    clock: Clock
    asked: list[str] = field(default_factory=list)  # elicitation messages shown to the "human"

    @property
    def gate(self) -> SafetyGate:
        return self.service.gate

    @property
    def audit_text(self) -> str:
        return self.service.audit.path.read_text(encoding="utf-8")

    def outcomes(self, tool: str) -> list[str]:
        return [e.outcome for e in self.service.audit.read() if e.tool == tool]


def make_rig(*, allow_commit=True, mode=ConfirmMode.ELICIT, port: FakePort | None = None,
             policy: KeyPolicy | None = None, ttl=300.0) -> Rig:
    d = Path(tempfile.mkdtemp())
    s = Settings(allow_commit=allow_commit, confirm_mode=mode, pending_ttl_s=ttl,
                 audit_log_path=d / "audit.jsonl")
    clock = Clock()
    gate = SafetyGate(allow_commit=allow_commit, ttl_s=ttl, policy=policy or KeyPolicy(), clock=clock)
    p = port or FakePort()
    svc = SeanceService(s, p, AuditLog(s.audit_log_path), gate)
    return Rig(p, svc, clock)


def human(rig: Rig, answer: str = "accept", confirm: bool = True):
    async def cb(ctx, params):
        rig.asked.append(params.message)
        if answer == "accept":
            return ElicitResult(action="accept", content={"confirm": confirm})
        return ElicitResult(action=answer)

    return cb


class Session:
    """Synchronous facade: each call runs the coroutine in a fresh event loop
    against a fresh in-process client (the server state lives in the rig)."""

    def __init__(self, rig: Rig, **client_kw: Any):
        self.rig = rig
        self.server = build_server(rig.service)
        self.client_kw = client_kw

    def call(self, tool: str, **args: Any):
        async def go():
            async with Client(self.server, **self.client_kw) as c:
                return await c.call_tool(tool, args)

        return anyio.run(go)

    def ok(self, tool: str, **args: Any) -> Any:
        r = self.call(tool, **args)
        assert not r.is_error, _text(r)
        return r.structured_content

    def err(self, tool: str, **args: Any) -> str:
        r = self.call(tool, **args)
        assert r.is_error, f"expected an error from {tool}, got {r.structured_content}"
        return _text(r)

    def list_tools(self):
        async def go():
            async with Client(self.server, **self.client_kw) as c:
                return (await c.list_tools()).tools

        return anyio.run(go)

    def read_resource(self, uri: str) -> str:
        async def go():
            async with Client(self.server, **self.client_kw) as c:
                res = await c.read_resource(uri)
                return "".join(getattr(x, "text", "") for x in res.contents)

        return anyio.run(go)


def _text(r) -> str:
    return " ".join(getattr(x, "text", "") for x in r.content)


def dump(obj: Any) -> str:
    return json.dumps(obj, default=str)
