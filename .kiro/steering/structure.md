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
