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

## The human-in-the-loop widening cycle

The explorer only ever presses keys that are read-only by default (CLEAR, PA1-3, PF13-24) or
that a human declared in `explore.seed.json`. `generate` then proposes *candidate* read-only
keys with evidence (`key-policy.proposed.json` + `key-policy.evidence.json`). A person reads the
evidence and runs `review --policy` to promote some into `key-policy.json`. Re-running `explore`
with the approved policy as input reaches further. **No code ever widens the policy; only a
person at a terminal writes `key-policy.json`.**

## Commands

```
python -m seance_spirit explore  --app fake-insurance --fake fake-insurance
python -m seance_spirit label    --app fake-insurance
python -m seance_spirit generate --app fake-insurance
python -m seance_spirit review   --app fake-insurance            # show approval status
python -m seance_spirit review   --app fake-insurance --tools --by you   # approve tools
python -m seance_spirit review   --app fake-insurance --policy --by you  # promote key policy
python -m seance_spirit replay   --app fake-insurance --fake fake-insurance
```

## How to review

`review` with no flags prints a diff-friendly summary: each tool's name, kind, `def_hash`, and
whether it is `approved`, `STALE` (edited since approval) or `unreviewed`. Read
`app-description.md` (screens, a Mermaid flow, tools, the frontier of unexplored/denied edges)
and `key-policy.evidence.json` before approving. Editing a tool changes its hash and un-approves
it automatically; mcp-server then skips it.

## Markers

`integration` (live host, needs `GSS_LIVE_OK=1`) and `llm` (real provider) are skipped by default.

## Tool pack registration (task 6.1 spike)

`mcp` 2.3.0 derives a tool's advertised schema from the Python signature. `register` builds a
handler whose signature matches the tool's input schema, then overrides the advertised schema
with the strict one. The SDK enforces required/types; `run_tool` enforces `maxLength`, `pattern`,
`enum` and `additionalProperties` itself. The one SDK-private seam is isolated in `runtime.register`.
