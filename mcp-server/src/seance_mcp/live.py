"""The live-container guard (docs/contracts.md section 2.1).

``gss-legacy`` is single-user. Only one agent (A, plus the integrator for final
runs) may connect to it. Everyone else works against FakeBridge. A checkout is
allowed to connect to a live host only if

* the environment variable ``GSS_LIVE_OK`` is exactly ``1``, or
* the gitignored marker file ``.gss-live-ok`` exists in that checkout's repo root
  (per worktree, so it cannot leak to another agent's worktree).

A shared ``.env`` must not set ``GSS_LIVE_OK``.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from .paths import REPO_ROOT

MARKER = ".gss-live-ok"
ENV_VAR = "GSS_LIVE_OK"


def live_allowed(env: Mapping[str, str] | None = None, root: Path = REPO_ROOT) -> bool:
    e = os.environ if env is None else env
    return e.get(ENV_VAR) == "1" or (root / MARKER).is_file()


LIVE_REFUSAL = (
    "connecting to a live system is not allowed in this checkout: set GSS_LIVE_OK=1 or create "
    f"{MARKER} in the repo root. Only the legacy agent (A) and the integrator touch the live "
    "container; use FakeBridge (seance_mcp.fake) otherwise."
)
