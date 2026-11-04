# spirit-map (`seance_spirit`)

Explore a legacy 3270 app read-only, label what was found, and generate typed,
business-level MCP tools from it.

> **The LLM names things. It never decides what is safe.**
> Which keys are read-only, which tools are `commit`, and what the explorer may
> press come from deterministic code plus a human-signed policy. Labels and screen
> text can only change strings, never keys, never policy, never tool kind.
> Only `spirit-map review --policy` (a person at a terminal) writes `key-policy.json`.

## Pipeline

`explore` -> `spirit-map.json` -> `label` -> `labels.json` -> `generate` -> `tools.json`
(+ `key-policy.proposed.json`, `app-description.md`) -> human `review` -> mcp-server.

Design and requirements: `.kiro/specs/spirit-map/`. Formats: `docs/contracts.md`.

## Setup

```
cd spirit-map
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ..\bridge -e "..\mcp-server[dev]" -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

Everything runs against `seance_mcp.fake` (`fake_insurance()`, `FakeApp.from_capture`).
This folder never connects to the live `gss-legacy` container.

## Markers

`integration` (live host, needs `GSS_LIVE_OK=1`) and `llm` (real provider) are skipped by default.
