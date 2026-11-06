# 🎃 Green Screen Séance

My entry for [Kiroween 2026](https://kiroween.devpost.com/) — built with [Kiro](https://kiro.dev) between 30 Oct and 4 Dec 2026.

> **Status:** parallel build in progress. Shared contracts frozen as `contracts-v1`; spirit-map (auto-discovery → generated tools) merged. See `docs/parallel-plan.md` for the schedule and `docs/kiro-journal.md` for how Kiro was used.

## Category
**Frankenstein** — a 1970s COBOL/3270 green-screen mainframe stitched to modern LLM agents via MCP. The legacy code is never rewritten; an AI layer drives the real screens.

## What it does
Point Green Screen Séance at a legacy IBM 3270 green-screen application and talk to it in plain English. It:

1. opens a real 3270 terminal session to the legacy app (a `bridge` library over `s3270`);
2. **learns the app** — an explorer navigates it read-only and records a *spirit map* (a graph of screens, fields and the keys between them), an LLM labels it with business meaning, and a generator turns it into **typed, business-level MCP tools** such as `lookup_policy(policy_number)`;
3. exposes those tools over an **MCP server** that any agent (including Kiro itself) can call;
4. runs a **chat agent** that fulfils requests by calling the tools, streaming each step to a **web UI** — a split screen with the glowing green terminal on the left and a "séance" chat on the right, and a planchette pointer that glides to the field the AI is reading or filling.

Anything that could change data goes through an explicit human confirmation and an append-only, hash-chained audit log. The default is strictly read-only.

## What is real, and what is a stand-in (read this before judging)
We are honest about which parts are a genuine mainframe and which are a demo convenience:

- **Real mainframe.** The legacy system is [TK4-](http://wotho.ethz.ch/tk4-/) (MVS 3.8j on the Hercules emulator) in Docker — real 1970s-era OS and real 3270 datastream. The `bridge`, the MCP server, the spirit-map explorer and the agent all drive it through a real `s3270` session. Kiro drives it live through our own MCP server during development.
- **Real COBOL.** The demo business logic (policy lookup/list/update) is a COBOL program compiled and run on TK4- via the proven COBUCLG route.
- **Stand-in (demo convenience).** Getting KICKS (a CICS clone, for BMS 3270 maps) installed on TK4- was time-boxed and **taken as a no-go early** (2026-11-05). So the five insurance **screens** are served by a clearly labelled Python TN3270 stand-in that front-ends the real COBOL logic, instead of KICKS BMS maps. The demo still shows the **real TK4- built-in screens live** (the VTAM/TSO logon screens), which the spirit-map explorer also maps — proving auto-discovery works on a real 3270 app, not only our own.
- **Simulated, for tests and offline demo.** A `FakeBridge` (`seance_mcp.fake`) reproduces the same five screens with genuine parsed field layouts, so the agent and UI can be built and the demo can run with no container at all. It is always labelled as simulated in the UI (a `REPLAY`/simulated badge).

Nothing claims to be production z/OS.

## Architecture
```
legacy/       TK4- in Docker, the COBOL app and the TN3270 stand-in         (Agent A)
bridge/       3270 session + screen parser — a pure, property-tested library (integrator)
mcp-server/   MCP server: generic tools + safety gate + hash-chained audit   (integrator)
spirit-map/   explorer → LLM labels → generated business-level MCP tools      (Agent B)
agent/        chat agent: LLM + MCP tool calling + FastAPI websocket          (Agent D)
web/          React + Vite split-screen UI with the planchette                (Agent C)
docs/         contracts, spirit-map artefacts, the Kiro journal
.kiro/        steering, specs, hooks, MCP config  (committed on purpose — hackathon rule)
```
Dependencies point one way: `bridge` ← `mcp-server` ← (`spirit-map`, `agent`); `web` talks only to `agent` over HTTP/WebSocket. The interface between every component is frozen in `docs/contracts.md`.

## How this was built: a parallel Kiro build
After the specs and a shared contract were agreed, the work was split across **git worktrees**, one per component, each driven in its own Kiro window (IDE or Kiro Crew):

| Branch | Owner | Folder |
|---|---|---|
| `agent/a-legacy` | A | `legacy/` |
| `agent/b-spirit-map` | B | `spirit-map/` |
| `agent/c-seance-ui` | C | `web/` |
| `agent/d-seance-agent` | D | `agent/` |
| `main` / `integration` | integrator | shared code, contracts, merges |

Isolation is by folder: an ownership check (`scripts/check-ownership.ps1`) rejects a branch that touches another owner's files, and a merge gate (`scripts/gate.ps1`) runs every component's tests (with a fixed and a random Hypothesis seed) plus contract conformance before anything lands. Only Agent A ever touches the live container; everyone else uses `FakeBridge`. See `docs/parallel-plan.md`.

## Safety (non-negotiable)
Read-only by default; a commit-capable key is never sent without a human confirming it on the same screen within a time limit. The model has no tool that confirms. Every action is in an append-only, hash-chained audit log. Hidden (password) field values never leave the bridge — not in a tool result, a log, a prompt, an event or the DOM. All screen text is treated as untrusted data (there is a prompt-injection test). Full list: `.kiro/steering/mainframe-safety.md` and `docs/contracts.md` section 11.

## Run it
_Per-component READMEs: `bridge/`, `mcp-server/`, `legacy/`, `spirit-map/`, `agent/`, `web/`. A one-command `docker-compose` + run-everything guide lands with the demo. Coming soon._

Drive the demo app from an MCP client with no mainframe:
```powershell
C:\Python312\python.exe -m venv mcp-server\.venv
mcp-server\.venv\Scripts\python.exe -m pip install -e bridge -e "mcp-server[dev]" -e spirit-map
$env:SEANCE_APP = "fake-insurance"
$env:GENERATED_TOOLS_PATH = "docs/spirit-map/fake-insurance/tools.json"
$env:KEY_POLICY_PATH = "docs/spirit-map/fake-insurance/key-policy.json"
mcp-server\.venv\Scripts\python.exe -m seance_mcp
```

## How Kiro was used
The `.kiro/` directory is intentionally committed (required by the hackathon rules — do **not** gitignore it). A running account with dated surprises is in `docs/kiro-journal.md`.

| Kiro feature | Where | Notes |
|---|---|---|
| Steering docs | `.kiro/steering/` | product, tech, structure, mainframe-safety, judging — always-on project rules |
| Specs | `.kiro/specs/` | six specs (requirements → design → tasks) drive every component |
| Agent hooks | `.kiro/hooks/` | journal on spec/steering save, pytest on bridge/mcp-server save, safety review on mcp-server/agent save |
| MCP | `.kiro/settings/mcp.json` | Kiro drives our own green screen through our MCP server during development |
| Kiro Crew / sub-agents | worktrees | the parallel build above; one agent per component |
| Property-based testing | `bridge/`, `mcp-server/`, `spirit-map/` | Hypothesis for the parser, the commit gate, explorer safety and spirit-map replay — real invariants, mutation-checked |

## Licence
[MIT](LICENSE). TK4- and KICKS are third-party and are **not** redistributed in this repo; setup scripts fetch them.
