# seance-agent

The chat agent for Green Screen Seance (package `seance_agent`). It is the only
backend the web UI talks to. It hosts the `seance_mcp` server **in-process**,
calls its tools through an in-memory MCP client on behalf of an LLM, and streams
every step to the browser over a websocket.

## The one property that matters

> **Even a fully compromised model cannot change data on the legacy system.**

The model is never offered a tool that confirms (`confirm_action`, `connect` and
`get_audit_log` are withheld). It cannot name the confirmer and it does not write
the confirmation modal's content. Only the controller websocket can approve a
pending action, out of band, through the `ConfirmBroker`. Screen text reaches the
model only inside tool results marked `trust: "untrusted-screen-data"`. Safety
does not depend on the model behaving: the test suite drives it with an obedient
`GullibleLlm` that executes whatever it reads on screen, and asserts no commit
key is ever sent without a human approval.

## Layout

```
src/seance_agent/
  __main__.py   python -m seance_agent (uvicorn)
  config.py     env -> Settings; unknown provider is an error, missing key -> llm.available=false
  api.py        FastAPI app, routes, origin + token checks, CORS, websocket
  session.py    Session: controller/observers, seq, ring buffer, resume, event log
  events.py     pydantic models for every websocket event and client message (contracts section 4)
  loop.py       AgentLoop.run_turn(): model <-> tools, budgets, cancel, suspend on pending
  prompts.py    system prompt and the untrusted-screen-data wrapper
  llm/          LlmProvider protocol; scripted (+ GullibleLlm), anthropic, bedrock
  tools.py      ToolBroker: list/filter tools, validate args, call via the MCP client
  confirm.py    ConfirmBroker: pending registry, approve/deny/expire, resume the turn
  mapper.py     EventMapper: service OpEvent/audit observers -> screen/field_focus/audit_entry
  apps.py       app registry (apps.json), connect_system, spirit-map view loader
```

## Setup (worktree: this folder)

```
cd agent
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ..\bridge -e ..\mcp-server[dev] -e .[dev]
```

## Run

```
.venv\Scripts\python.exe -m seance_agent
```

Defaults bind to `127.0.0.1:8000`. With `LLM_PROVIDER=scripted` the agent needs no
keys and no network; it is the offline demo fallback and what CI uses.

## Environment

Every variable is listed in `.env.example` with placeholder values only. `.env`
is gitignored and never committed. No key, host or credential lives in the repo.

Key variables:

- `LLM_PROVIDER` = `anthropic` | `bedrock` | `scripted`. Unknown value -> startup error.
- `AGENT_ALLOWED_ORIGINS` = comma-separated origins allowed to reach the REST and
  websocket endpoints (default `http://localhost:5173,http://127.0.0.1:5173`).
- `SEANCE_CONFIRM_MODE=oob` (the UI is the human gate).
- `SEANCE_ALLOW_COMMIT=0` makes the server read-only: a proposed action still shows
  in the UI, but approval ends `blocked_read_only` instead of silently doing nothing.
- `GSS_LIVE_OK` must be `1` before the agent will connect to a live host. It is never
  set in a shared `.env`; a live run is Agent A's job.

## Tests

```
.venv\Scripts\python.exe -m pytest
```

`integration` (live container) and `llm` (real provider) tests are skipped by
default. Everything else runs against `seance_mcp.fake` with a scripted model: no
network, no credentials, no mainframe.
