"""build_service: one place that wires settings, audit, gate, port and server.

Used by ``python -m seance_mcp`` (stdio) and by the agent, which hosts the
server in-process (docs/contracts.md section 4.5 and agent design.md). Relative
paths in settings resolve against the repo root, so behaviour does not depend on
the launch directory.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from mcp.server import MCPServer

from .audit import AuditLog
from .config import Settings
from .paths import REPO_ROOT, resolve_path
from .port import BridgePort, RealBridgePort
from .safety import KeyPolicy, SafetyGate
from .server import build_server
from .service import SeanceService
from .toolpack import Registrar


def build_service(
    settings: Settings,
    port: BridgePort | None = None,
    *,
    audit_path: Path | None = None,
    clock: Callable[[], float] | None = None,
    root: Path = REPO_ROOT,
    registrar: Registrar | None = None,
) -> tuple[MCPServer, SeanceService]:
    """Return ``(server, service)`` sharing one gate, audit log and port.

    ``port`` defaults to the real bridge adapter; pass ``seance_mcp.fake`` ports
    for anything that must not touch the live container. ``service.gate`` is the
    handle the agent's confirmation broker uses for ``approve_oob``/``deny_oob``;
    it is never exposed as a tool.
    """
    audit = AuditLog(resolve_path(audit_path or settings.audit_log_path, root))  # type: ignore[arg-type]
    gate_kw = {"clock": clock} if clock is not None else {}
    gate = SafetyGate(
        allow_commit=settings.allow_commit,
        ttl_s=settings.pending_ttl_s,
        policy=KeyPolicy.load(resolve_path(settings.key_policy_path, root)),
        **gate_kw,  # type: ignore[arg-type]
    )
    real = port or RealBridgePort(settings.wait_timeout_ms, settings.volatile_regions)
    service = SeanceService(settings, real, audit, gate)
    return build_server(service, registrar), service
