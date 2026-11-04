"""python -m seance_mcp : serve the Green Screen Seance MCP server over stdio.

stdout is the MCP protocol channel, so all logging goes to stderr.
Relative paths in settings (audit log, key policy) resolve against the repo
root, so the server behaves the same whatever directory a client launches it in.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from .audit import AuditLog
from .config import Settings
from .port import RealBridgePort
from .safety import KeyPolicy, SafetyGate
from .server import build_server
from .service import SeanceService

REPO_ROOT = Path(__file__).resolve().parents[3]  # mcp-server/src/seance_mcp/__main__.py


def _abs(p: Path | None) -> Path | None:
    if p is None:
        return None
    return p if p.is_absolute() else REPO_ROOT / p


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("seance_mcp")
    settings = Settings.from_env()
    audit = AuditLog(_abs(settings.audit_log_path))  # type: ignore[arg-type]
    gate = SafetyGate(
        allow_commit=settings.allow_commit,
        ttl_s=settings.pending_ttl_s,
        policy=KeyPolicy.load(_abs(settings.key_policy_path)),
    )
    service = SeanceService(settings, RealBridgePort(settings.wait_timeout_ms), audit, gate)
    log.info(
        "starting: host=%s:%s allow_commit=%s confirm_mode=%s audit=%s",
        settings.host, settings.port, settings.allow_commit, settings.confirm_mode.value, audit.path,
    )
    build_server(service).run("stdio")


if __name__ == "__main__":
    main()
