# Merge request: `agent/b-spirit-map` (live follow-ups)

From: Agent B. Branch `agent/b-spirit-map`, based on main at `8bd8f0c` (merged in at the start of this work).
Touches only B's paths (`scripts/check-ownership.ps1`: pass).

## What is in it (one commit per task)
- **9.1** `explore` / `replay` ignore `TN3270_HOST` / `TN3270_PORT` unless `--from-env`; `--host`, `--port`, `--audit` flags; default `localhost:3270`. A's bug report (host/port never passed to the explorer) is fixed: they are now always passed. `tests/test_cli.py`.
- **9.2** `tk4-builtins` seed: `(0,11,6)` added to `volatile` (the `CUU0Cx` terminal name).
- **9.3 + 8.3** A's live results promoted: `docs/spirit-map/seance-insurance/` (live map identical to fake-insurance, plus labels/tools/policy/description generated here) and `docs/spirit-map/tk4-builtins/spirit-map.partial.json` (evidence, with a README saying it is not the map).
- **5.5** `tests/test_llm_real.py` (`llm` marker, skips without credentials).
- **9.4** request to A for a second tk4-builtins live run: `docs/handoff/b/request-a-tk4-second-live-run.md`.

## Verification
`gate.ps1 -Only spirit-map,contracts,ownership`: spirit-map 133 passed (fixed and random seed), ownership pass.
`contracts` was **skipped** here because this worktree has no `mcp-server/.venv`; please run the full gate on the integration branch.

## Needs a person, not me
- `docs/spirit-map/seance-insurance/tool-approvals.json` and `key-policy*.json` are the fake-insurance approvals copied unchanged (tool hashes and policy are identical). Re-sign with `python -m seance_spirit review --app seance-insurance --tools --by <you>` (and `--policy`) if you want an approval specific to that app.

## Still open on the spirit-map task list
- 5.5 real labelled run: needs an LLM API key.
- 7.4 stretch: needs a human logon on the live system.
- 9.4 second tk4-builtins run: waiting for A.
