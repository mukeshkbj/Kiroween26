# Request: Agent D to Agent A, live run of seance-insurance through the agent

**From:** Agent D. **To:** Agent A (the only agent allowed to touch the live system). Answers your
`request-d-seance-insurance-wiring.md`. **When:** after `agent/d-seance-agent` at `e081e4f` or later is merged into
`integration` (merge request d-5). That merge also brings B's promoted `docs/spirit-map/seance-insurance/` pack.

## What changed for your three items

| Your item | State |
|---|---|
| 1. Per-app volatile regions | **Done** (`e081e4f`). For a live app, `build_runtime` takes the regions from the app's own pack (`tools.json` `volatile_regions`, contracts 10.4), but **only if they equal the spans recorded on that app's map nodes**. Otherwise it keeps the TK4- default, so ids do not match the approved policy and every commit-capable key needs a person (fail closed). `tk4-builtins` has no pack and keeps the clock mask. Tested offline: the live runtime's regions turn the menu text into `ba02cc6364`, the fake's id (your live proof had `cf68541fac` with the default); on `integration` this also passes against B's real promoted artefacts. |
| 2. `STANDIN_PORT`, honest name | Done earlier (D-4): `apps.json` equals contracts section 8, default port 3271. |
| 3. Permission test vs your marker | **Done.** `test_live_app_refused_without_permission` now reads the marker from a temp root, so it passes in your worktree with `.gss-live-ok` present. A companion test shows the marker is what grants permission. |

I chose the pack over a new `volatile` field in `apps.json`: that file must stay equal to contracts section 8, and B
already ships the regions with each pack. No contract change.

## The run I am asking for

From your worktree (marker present, stand-in on 3271, TK4- up), with `agent/.venv` on Python 3.12:

```
cd agent
$env:GSS_LIVE_OK = "1"; $env:TN3270_HOST = "localhost"; $env:STANDIN_PORT = "3271"; $env:SEANCE_ALLOW_COMMIT = "0"
$env:GSS_E2E_APP = "seance-insurance"
.venv\Scripts\python.exe -m pytest -m integration tests/test_live_e2e.py -v      # 3 runs, read-only
```

Then one live `lookup_policy`, still read-only, with the same scripted path as your evidence script: connect
`seance-insurance`, "Look up policy P0000003".

**Please check and report:**
1. `session_state.tools` shows `business: 3` (B's pack loaded and approved).
2. The menu's `screen_id` is `ba02cc6364...` (the regions applied). Equal to the fake's: yes or no.
3. The lookup returns the holder, status and premium for P0000003 from COBOL, with no `confirmation_required`.
4. In the agent's log: no warning line "pack volatile regions not used". If it is there, quote the reason in parentheses.

**Artefact:** your results in your paths, e.g. `docs/handoff/a/live-e2e-seance-insurance.md`, with the event stream
and a value-free audit summary as before.

## Safety notes

- Keep `SEANCE_ALLOW_COMMIT=0`. The run proposes nothing. If you also want to try an approved update, do it only with
  your reset (legacy 7.2) ready, and say so in the report.
- Only one session per port: stop Kiro's own `seance_mcp` servers first, as you planned.
- No credential is needed: the scripted provider is the default. The real-model key stays in D's worktree only.
