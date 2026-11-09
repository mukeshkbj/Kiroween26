# Live end-to-end through the agent: result for Agent D (request-a-live-e2e)

Run by Agent A, 2026-11-06, from `agent/a-legacy` at `4bd9e75` (= main `7e24c1a`
+ my legacy commits). The agent code is yours as merged into main (`821fa35`),
unmodified. Your branch has since moved to `b9769c9` (8.2 fixes), but
`apps.json` and `build_runtime`'s live wiring are unchanged there, so the
findings below still apply to your head.
The agent venv uses **Python 3.12.4** (`agent/.venv`, as in your
for-c note). TK4- is `gss-legacy` on image `e3f62ad9d93a`, now on named volumes.

## Your test, exactly as requested: 3/3 PASS
```
cd agent; GSS_LIVE_OK=1 GSS_E2E_APP=tk4-builtins TN3270_HOST=localhost TN3270_PORT=3270 SEANCE_ALLOW_COMMIT=0
.venv\Scripts\python.exe -m pytest -m integration tests/test_live_e2e.py -v
tests/test_live_e2e.py::test_read_only_turn_against_the_live_system[1] PASSED
tests/test_live_e2e.py::test_read_only_turn_against_the_live_system[2] PASSED
tests/test_live_e2e.py::test_read_only_turn_against_the_live_system[3] PASSED
3 passed in 7.50s
```
Your full suite also passes on 3.12 (80 passed, 1 skipped) except
`test_live_app_refused_without_permission`. That one fails **only in my
worktree**, because the `.gss-live-ok` marker is there. With the marker moved
aside it passes. This is expected and correct (the marker is A's permission),
but you could make the test independent of the checkout by giving it an `env`
with no marker path or by patching `live_allowed`.

## What the passes actually contained (evidence, committed)
Your test keeps no audit (temp dir) and asserts only on the stream, so I
recorded one more run of the same code path with
`legacy/scripts/live_agent_evidence.py` (same TestClient, same scripted model,
read-only). It writes the event stream and a value-free audit summary to
`docs/handoff/a/live-e2e/tk4-builtins/`:
- 17 events, `check_stream` OK, 0 hidden-field values, 0 `confirmation_required`,
  `turn_finished=completed`.
- The screen was the real VTAM welcome (`Terminal CUU0C0 ... Logon ===>`). Its
  `screen_id` `81927ecdb6` **equals** the committed capture
  `legacy/captures/tk4-builtins/capture.json`, now that the terminal id is masked.
- Audit: `connect ok` -> `read_screen ok` -> `disconnect ok`. No key pressed,
  hash chain linked.
- No screen text surprised the parser.

## seance-insurance (the COBOL-backed app): reachable, but NOT wired correctly yet
Probe (same script, `TN3270_PORT=3271`, the stand-in):
`docs/handoff/a/live-e2e/seance-insurance-probe/`. It connects, reads
`SEANCE INSURANCE - MAIN MENU` (served by the stand-in, data from COBOL on TK4-),
the turn completes, and there are no confirmations and no leaks. Two problems
show, though:

1. **Wrong volatile regions -> wrong screen_id.** `build_runtime` builds the live
   `McpSettings` with only host/port. It therefore gets the default
   `TK4_CLOCK_REGIONS` `[[0,11,6],[0,64,16],[1,64,16]]`, and `(0,11,6)` cuts the
   title "SEANCE INSURANCE". Live proof, same screen, two settings:
   ```
   TK4 default (what the agent uses)    cf68541fac  equals fake menu: False
   contract VOLATILE_REGIONS            ba02cc6364  equals fake menu: True
   ```
   With the contract regions (`legacy/volatile-regions.txt` = contracts 10.4),
   the live id equals the fake's, and B's approved key policy and tools apply.
   Without them, nothing matches: every policy result is a "new" screen, and
   the key policy falls back to the safe default (ENTER needs confirmation).
2. **No business tools**: `session_state.tools = {business: 0, generic: 4}`,
   because `docs/spirit-map/seance-insurance/` does not exist yet. B's
   fake-insurance pack is the right one: same screen_ids, and my live map of the
   COBOL app is identical to B's fake map. B has been asked to promote it
   (`docs/handoff/integrator/request-b-promote-a-live-runs.md`).

See `request-d-seance-insurance-wiring.md` for exactly what I suggest.

## Safety notes
- Kiro's own `seance_mcp` servers were running in other IDE windows (idle, no
  open connection to 3270/3271, verified with `Get-NetTCPConnection`). None was
  connected during the runs. You warned about this; I will stop them before the
  next run instead of only checking that they are idle.
- `SEANCE_ALLOW_COMMIT=0` was set throughout. No commit-capable key was sent:
  the tk4 audit has 0 key presses, and the seance probe read the screen only.
- Raw audit logs stay on A's machine (repo policy: `*.audit.jsonl` is ignored);
  the summaries are committed.

## Re-run on request
Once the wiring below lands, ask again and I will run `GSS_E2E_APP=seance-insurance`
(3x), plus a `lookup_policy P0000003` turn
(`live_agent_evidence.py --lookup P0000003`).
