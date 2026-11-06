"""``python -m seance_agent``: run the agent with uvicorn.

Logs go to stderr. The startup line names the provider and model only, never a key.
A ``.env`` next to this package is read for convenience, but ``GSS_LIVE_OK`` is
ignored there: contracts section 2.1 forbids a shared ``.env`` from granting live access.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import uvicorn

from .api import create_app
from .config import Settings, llm_availability

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
NEVER_FROM_DOTENV = {"GSS_LIVE_OK"}


def load_dotenv(path: Path = ENV_FILE) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if k in NEVER_FROM_DOTENV or k in os.environ:
            continue
        os.environ[k] = v.strip().strip('"').strip("'")


def main() -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()
    try:
        settings = Settings.from_env()
    except ValueError as exc:
        print(f"seance-agent: configuration error: {exc}", file=sys.stderr)
        return 2
    logging.getLogger("seance_agent").info(
        "starting on %s:%s llm=%s model=%s available=%s commit=%s",
        settings.host, settings.port, settings.llm_provider.value, settings.llm_model,
        llm_availability(settings), "allowed" if settings.allow_commit else "read-only")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
