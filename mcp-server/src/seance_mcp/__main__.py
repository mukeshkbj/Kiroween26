"""python -m seance_mcp : serve the Green Screen Seance MCP server over stdio.

stdout is the MCP protocol channel, so all logging goes to stderr.
Relative paths in settings (audit log, key policy) resolve against the repo
root, so the server behaves the same whatever directory a client launches it in.
"""
from __future__ import annotations

import logging
import sys

from .config import Settings
from .factory import REPO_ROOT, build_service  # noqa: F401  (REPO_ROOT kept for callers)


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("seance_mcp")
    settings = Settings.from_env()
    server, service = build_service(settings)
    target = f"fake:{settings.app}" if settings.app else f"{settings.host}:{settings.port}"
    log.info(
        "starting: target=%s allow_commit=%s confirm_mode=%s audit=%s tools=%s",
        target, settings.allow_commit, settings.confirm_mode.value, service.audit.path,
        settings.generated_tools_path or "(generic only)",
    )
    server.run("stdio")


if __name__ == "__main__":
    main()
