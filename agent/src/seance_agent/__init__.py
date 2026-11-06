"""seance_agent: the Seance chat agent and its FastAPI + websocket surface.

The agent hosts the ``seance_mcp`` server in-process and streams every step of a
model's tool use to the web UI. Its one invariant: even a fully compromised model
cannot change data on the legacy system, because no model-visible tool confirms
and only the controller websocket can approve a pending action.
"""
from __future__ import annotations

__version__ = "0.1.0"
