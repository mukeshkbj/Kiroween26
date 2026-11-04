"""Repo-root path resolution shared by the factory and the tool-pack loader."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # mcp-server/src/seance_mcp/paths.py


def resolve_path(p: Path | None, root: Path = REPO_ROOT) -> Path | None:
    """Relative paths resolve against the repo root, not the launch directory."""
    if p is None:
        return None
    return p if p.is_absolute() else root / p
