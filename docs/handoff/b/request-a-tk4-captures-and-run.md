# Request to Agent A: tk4-builtins captures, and a live exploration run

From: Agent B (spirit-map). Tasks 7.1 and 7.3. Only A touches `gss-legacy` (contracts 2.1); B uses FakeBridge.

## 7.1 — recorded captures (so B can test against real layouts without the container)

Please record `legacy/captures/tk4-builtins/<name>.json` in the `gss.capture/1` format (contracts 2.3; a worked example is `docs/contracts/examples/capture/capture.json`), reading the live app through the normal tools only. Screens that need no logon:

- `welcome` — the TK4-/VTAM welcome screen (the one shown before logon).
- `logon_rejected` — the screen after ENTER with a bogus userid (e.g. `XYZZY`), i.e. a logon-rejected message. No real credentials; a bogus id is fine and documented.

Transitions to record (read-only navigation only, no real logon):
- `welcome --CLEAR--> welcome`
- `welcome --ENTER (fills: logon=XYZZY) --> logon_rejected` (or whatever the welcome's input field is labelled; put the real label in `fills[].field`)
- `logon_rejected --CLEAR--> welcome` if that is what CLEAR does

Rules that keep the capture clean (a capture with any of these is a bug): no hidden-field value, no password, no real userid other than the documented bogus one. Put the clock spans in each screen's optional `volatile`: `[[0,64,16],[1,64,16]]` (the VTAM date/time, contracts config `TK4_CLOCK_REGIONS`); `FakeApp.from_capture` recomputes `screen_id` and fails if they are wrong, so this must match what the server masks.

B then loads them with `FakeApp.from_capture` and runs `explore`/`replay` against the real layouts (task 7.2), with **no** container access on B's side.

## 7.3 — the live exploration run (A or the integrator, with GSS_LIVE_OK=1)

Once the seed and captures agree, please run the marked live exploration and commit the resulting map:

```
# in A's or the integration worktree, container up, GSS_LIVE_OK=1 (or .gss-live-ok present)
python -m seance_spirit explore --app tk4-builtins --attach --stamp
```

- `--attach` starts from whatever screen the session shows (no logon driven by the explorer).
- Expected artefact: `docs/spirit-map/tk4-builtins/spirit-map.json`. The seed is already committed at `docs/spirit-map/tk4-builtins/explore.seed.json` (non-commit keys only, clock regions marked volatile, credential-labelled fields denied, nothing declared read-only — so the first live map is small and honest about its frontier).
- Safety: the explorer presses only read-only keys (CLEAR, PA1-3, PF13-24) and never fills a credential field. It will record the welcome screen and the frontier edges it did not take (ENTER is a frontier item, `denied_commit`, until a human declares it). Nothing commits.
- Please hand the resulting `spirit-map.json` back via `docs/handoff/a/` or commit it under `docs/spirit-map/tk4-builtins/` on the integration branch; B does not run it.

Nothing here blocks the fake-insurance milestone, which is complete.
