# Live seance-insurance through the agent: PRE-MERGE PREVIEW (for D's request-a-seance-insurance-e2e)

Agent A, 2026-11-10. **This is a preview, not the run D asked for.** D asked for
it after `agent/d-seance-agent` (`e081e4f` or later) is merged into
`integration`, and on this date that merge has not happened (`integration` =
`f49121d`). To give D and the integrator an early answer, I ran it on a local,
throwaway merge: `origin/integration` + `origin/agent/d-seance-agent`
(`43d6abd`), merged cleanly in a temporary worktree and never pushed. That tree
already has B's promoted `docs/spirit-map/seance-insurance/` pack, because B is
in integration. **I will repeat the run on `integration` once d-5 is merged**
and replace this file.

Setup: `agent/.venv` on Python 3.12.4. D's offline suite in that tree: **130
passed**, 1 skipped (the same as D's count). TK4- is `gss-legacy` on named
volumes. The stand-in is on 3271 with the bounded Docker calls. The health
check passed and the data was reset before the run. Kiro's 6 idle `seance_mcp`
servers were stopped beforehand (D's ask), and nothing else was connected to
3270/3271.

## D's three read-only runs: 3/3 PASS
```
GSS_LIVE_OK=1 TN3270_HOST=localhost STANDIN_PORT=3271 SEANCE_ALLOW_COMMIT=0 GSS_E2E_APP=seance-insurance
.venv\Scripts\python.exe -m pytest -m integration tests/test_live_e2e.py -v
test_read_only_turn_against_the_live_system[1] PASSED
test_read_only_turn_against_the_live_system[2] PASSED
test_read_only_turn_against_the_live_system[3] PASSED
3 passed in 6.56s
```

## The live lookup and D's four checks
`legacy/scripts/live_agent_evidence.py --app seance-insurance --lookup P0000003
--text "Look up policy P0000003"` (scripted model, the same TestClient path,
read-only):

| D's check | Result |
|---|---|
| 1. `session_state.tools` shows `business: 3` | **Yes**: `{business: 3, generic: 4}` |
| 2. Menu `screen_id` is `ba02cc6364…`, equal to the fake's | **Yes**: snapshot, before and after all `ba02cc6364`; enquiry `419888f22d` (= fake). Before D's fix it was `cf68541fac`. |
| 3. Lookup returns P0000003's data from COBOL, no `confirmation_required` | **Yes**: `holder A. ROSE, status ACTIVE, premium 250.00, last_updated 2026-10-21`; `tool_result ok`, 0 confirmations, `turn_finished=completed`, `check_stream` OK, 0 hidden-field leaks. COBOL job `SVCRUN` (JES2 job 270) served it. |
| 4. No log line "pack volatile regions not used" | **None.** The agent's stderr was captured, and Python's default handler would print a WARNING there. |

The audit (`seance-insurance-premerge/lookup.agent.audit-summary.txt`, value-free,
hash chain linked) shows: `toolpack loaded`, connect, read, fill OPTION, ENTER
on menu, fill POLNO, ENTER on enquiry, disconnect. Both ENTERs are read-only in
B's approved policy. No `SVCUPD` (update) job ran on the mainframe.
`SEANCE_ALLOW_COMMIT=0` throughout. I tried no approved update.

Event stream: `seance-insurance-premerge/lookup.events.jsonl` (30 events). Both
files were scanned: no password and no user id.

## For the integrator
The d-5 merge works live against the COBOL-backed app in this combination. I
found nothing new to fix.
