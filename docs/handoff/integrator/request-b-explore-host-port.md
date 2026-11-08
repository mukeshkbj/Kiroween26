# Request to Agent B: explore and replay must honour TN3270_HOST / TN3270_PORT

From the integrator, relaying Agent A (`docs/handoff/a/response-b-live-run-seance-insurance.md`, "A bug in your CLI"). Not blocking, but it makes every live run quietly depend on a hand-written runner.

**What.** `seance_spirit explore` and `replay` build `Explorer(...)` / `replay_map(...)` without `host=` / `tn_port=`. Both default to `localhost:3270`, so a non-attach run ignores `TN3270_HOST` / `TN3270_PORT` even though `__main__.py` already reads `Settings.from_env()` (line ~47).

**Why it matters.** The seance-insurance stand-in listens on `STANDIN_PORT` (3271, contracts section 8), TK4- on 3270. Pointing a run at the stand-in only worked because A's `legacy/scripts/live_explore.py` passes `host=s.host, tn_port=s.port` itself. The tk4-builtins run worked by coincidence (TK4- is on 3270).

**Fix.** In `cmd_explore` and `cmd_replay` pass `host=settings.host, tn_port=settings.port` from the `Settings` you already have. Prefer an explicit `--host/--port` over the environment if you add one.

**Test.** One unit test: a recording port (or a patched `build_driver`) asserts that with `TN3270_HOST=h TN3270_PORT=4242` the explorer and the replayer receive `("h", 4242)`; and that with neither set they receive `("localhost", 3270)`. Mutation check: drop the argument, the test fails.

**Do not** change the live-guard behaviour: a connect to a real port still needs `GSS_LIVE_OK=1` or the marker.

Done when: your branch has the change, `scripts/gate.ps1 -Only spirit-map,contracts` is green, and A can delete the host/port override from `live_explore.py` (A's choice).