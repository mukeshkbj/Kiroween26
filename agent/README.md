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

## Trust model, in plain words

- The model can read screens, fill fields and propose changes. It cannot **approve** one.
  There is no tool for it, and the model never sees the text that tells callers how.
- When a change is proposed, the turn stops and the browser shows a confirmation. The
  details come from the safety gate (key, screen, fields), never from what the model said.
  Its own wording is shown separately, labelled unverified.
- Only the **controller** connection (the first valid `hello`) can approve, deny, start a
  turn or connect a system. Later connections are observers and are told `observer_only`.
- Text that came from a screen reaches the model only inside tool results marked
  `trust: "untrusted-screen-data"`. It is information, never instructions.
- A denied, expired or blocked change is final for that turn. A key press that times out
  is never resent; the agent reads the screen and tells the model it may or may not have run.
- `SEANCE_ALLOW_COMMIT=0` (the default) shows the confirmation and then reports it as
  blocked, so read-only is visible instead of silent.
- A live host is refused (`live_not_allowed`) unless `GSS_LIVE_OK=1` or `.gss-live-ok`
  exists. A `.env` cannot set it.

## Origin and token

Any web page can try `ws://localhost:8000`. The websocket is accepted only to be closed
with code 4403 unless its `Origin` is in `AGENT_ALLOWED_ORIGINS`. `hello` must carry a
token from `GET /api/session`; CORS headers go only to allowed origins, so another origin
cannot read it. Other close codes: 4400 first message was not `hello`, 4401 bad token,
4429 client too slow.

## Layout

```
src/seance_agent/
  __main__.py   python -m seance_agent (uvicorn)
  config.py     env -> Settings; unknown provider is an error, missing key -> llm.available=false
  api.py        FastAPI app, routes, origin + token checks, CORS, websocket
  hub.py        everything behind the socket: session, runtime, loop, message handling (no HTTP)
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
.venv\Scripts\python.exe -m pip install -e ..\bridge -e ..\mcp-server[dev] -e ..\spirit-map -e .[dev]
```

`spirit-map` provides the runtime for the approved `fake-insurance` tool pack
(`docs/spirit-map/fake-insurance/`). Without it, `connect_system` fails loudly.

## Start agent + web locally

Two terminals, both from the repo root. Nothing here touches the live mainframe:
`fake-insurance` is the in-process FakeBridge app.

**1. Agent** (port 8000):

```
cd agent
$env:SEANCE_ALLOW_COMMIT = "1"     # optional: let approved changes run (default 0 = read-only, still shows the modal)
.venv\Scripts\python.exe -m seance_agent
```

The startup line names the provider and model only, e.g.
`starting on 127.0.0.1:8000 llm=scripted model=scripted-demo available=True commit=allowed`.

**2. Web** (port 5173, Agent C's app in `web/`):

```
cd web
npm ci                              # exact pinned versions from the lockfile
npm run dev                         # http://localhost:5173
```

`web/.env.example` already points at the agent (`VITE_AGENT_URL=http://127.0.0.1:8000`,
`VITE_MODE=live`). Use `VITE_MODE=mock` to replay recorded sessions without the agent.

**3. Use it.** Open http://localhost:5173 (that exact origin, or http://127.0.0.1:5173; anything
else is refused with close code 4403). Connect **Seance Insurance (simulated)**, then try:

| Say | What happens |
|---|---|
| `Look up policy P0000003` | read tool; the planchette follows each recipe step |
| `List the policies` | read tool |
| `Set the premium of policy P0000003 to 300` | stops at the confirmation modal; Approve sends ENTER once, Deny sends nothing |
| `Set the status of policy P0000004 to L` | same, for status |

The offline demo model only understands sentences like these. For free text, set
`LLM_PROVIDER=anthropic` with `ANTHROPIC_API_KEY`, or `bedrock` with `AWS_REGION` and AWS
credentials, plus `LLM_MODEL`, in the agent's terminal.

**Notes**

- The first tab to say `hello` controls the session. Other tabs are observers (they see everything
  and cannot approve). A reload, or a reconnect that resumes, keeps control.
- Restarting the agent starts a new session: the UI discards its old state.
- The audit log is at `docs/audit/audit.jsonl` (gitignored), also shown in the UI and at `GET /api/audit`.
- The fake app's data lives in memory and resets when the agent restarts.
- Port in use (`Errno 10048`): another agent is still running; stop it first.

**Checked 2026-11-06:** C's real transport, guards and reducer (`origin/agent/c-seance-ui`, `d197091`)
against this agent, in Node, five runs in a row on one agent (`scripts/c_live_check/`, see the header of
`live-agent.test.ts`). Not yet clicked through in a browser; that is the 8.2 sign-off with Agent C.

## Run

```
.venv\Scripts\python.exe -m seance_agent
```

Defaults bind to `127.0.0.1:8000` and the server is read-only. With `LLM_PROVIDER=scripted` the agent needs no
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
