# Request: Agent D to Agent A, live end-to-end through the agent (tasks.md 8.3, REQ-032)

**From:** Agent D (`agent/`). **To:** Agent A (the only agent allowed to touch `gss-legacy`).
**When:** after `agent/d-seance-agent` is merged into `integration` (about 24 Nov). Not before.

## What I need

Run the agent against the live container three times in a row and tell me the result.
I have never connected to it and will not. Everything below is already tested against
FakeApp; this is the one thing only you can verify.

## Command

From a checkout that is allowed to touch the live container (your worktree, with
`.gss-live-ok` or `GSS_LIVE_OK=1` and your `TN3270_HOST` / `TN3270_PORT`):

```
cd agent
$env:GSS_LIVE_OK = "1"
$env:GSS_E2E_APP = "tk4-builtins"        # or seance-insurance once it has a tool pack
.venv\Scripts\python.exe -m pytest -m integration tests/test_live_e2e.py -q
```

`tests/test_live_e2e.py` is parameterised `run = 1, 2, 3`, each with a fresh
`connect_system`. It uses the `scripted` provider, `SEANCE_ALLOW_COMMIT=0`, and only
reads the screen. It asserts: the stream satisfies the ordering rules, a `screen{after}`
arrives, no `confirmation_required` appears, and no hidden-field value is present.

## Optional: the full UI path

```
.venv\Scripts\python.exe -m seance_agent        # with the same env as above
```

then point the web UI at `http://127.0.0.1:8000`, connect `tk4-builtins`, and ask it to
read the screen. If you have a business tool pack for `seance-insurance`, a lookup
(`Look up policy P0000003`) is the natural check.

## Expected artefact

Please commit your result to **your** paths, for example `docs/handoff/a/live-e2e-agent.md`:
the three pass/fail lines, the date, the TK4- and agent commit hashes, and any screen text
that surprised the parser. If anything fails, paste the first failing assertion and the
tail of `docs/audit/audit.jsonl`.

## Safety notes

- Leave `SEANCE_ALLOW_COMMIT=0`. Do not approve a commit on the live system unless you
  can run your reset afterwards (`legacy` reset, task 7.2). The test never proposes one.
- The agent refuses a live app without `GSS_LIVE_OK=1` (`error{live_not_allowed}`) before
  it builds any port. That refusal is itself tested.
- Only one 3270 session exists. Stop Kiro's own `green-screen-seance` MCP server while the
  agent is connected, or the two will fight over it.
- The test never writes `.env` and logs no credential.
