---
inclusion: always
---

# Structure — Green Screen Séance

## Repo layout
```
/
├── legacy/          # docker-compose + TK4- setup + demo business app install scripts
├── bridge/          # 3270 session control + ScreenModel parser (the core library)
├── mcp-server/      # MCP server exposing generic + spirit-map-generated tools
├── agent/           # seance chat agent (LLM + tool calling + websocket)
├── web/             # React + Vite + TypeScript frontend (split-screen UI)
├── docs/            # spirit-map output, generated app description, kiro-journal
└── .kiro/
    ├── steering/    # these docs
    ├── specs/       # spec requirements/design/tasks
    └── hooks/       # agent hooks
```

## Principles
- `bridge/` is a pure library with no network/agent dependencies — easy to test in isolation.
- `mcp-server/` depends on `bridge/`. `agent/` depends on `mcp-server/` (via MCP client) and `bridge/` types.
- `web/` talks only to the FastAPI backend (HTTP + websocket), never directly to the 3270 session.
- Each component is independently runnable and testable.
- Specs live under `.kiro/specs/<name>/` (requirements.md, design.md, tasks.md).

## Addendum (2026-11-04): spirit-map, scripts, contracts, ownership
- `spirit-map/` (package `seance_spirit`) is the explorer, labeller, generator and tool-pack runtime. It depends on `bridge/` and `mcp-server/`; it never imports `agent/` or `web/`. Its artefacts live in `docs/spirit-map/<app_id>/`.
- `scripts/` holds the merge gate (`gate.ps1`, `check-ownership.ps1`), the journal hook and setup helpers. `docs/contracts.md` and `docs/contracts/` (generated schemas and examples) are the shared interface contracts.
- Folder ownership for the parallel build is in `docs/contracts.md` section 1 (A `legacy/`, B `spirit-map/`, C `web/`, D `agent/`, integrator everything shared). Nobody edits another owner's folder; ask with a request file in `docs/handoff/<letter>/`.
- Only Agent A touches the live `gss-legacy` container; everyone else uses `seance_mcp.fake` (`docs/contracts.md` section 2).
