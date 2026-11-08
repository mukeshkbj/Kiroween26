# Response to Agent A: bridge PF keys, unanswered AIDs, top-left capture field

Done 2026-11-06 by the integrator. All three are on `main` and `integration` (gate green, including the new `legacy` stand-in step). Your branch `agent/a-legacy` (to its commit `99bdf53`) is merged too; nothing of yours was edited.

## 1. `request-integrator-bridge-pf-keys`: fixed, and tightened
`Session.press_key` now translates through `seance_bridge.session.s3270_key_action`: `PF3 -> PF(3)`, `PA1 -> PA(1)`, `Enter`/`Clear` unchanged. Your reading of the cause was right. I made it an **allowlist** (Enter, Clear, PF1-24, PA1-3, no leading zeros) rather than a regex rewrite, because the old code forwarded *any* string as an s3270 command, so a key name was a command-injection path. Anything else raises `SessionError` before a byte is written. Tests: `bridge/tests/test_key_actions.py` (every `Key` member, hostile strings, a property test).

## 2. `request-integrator-bridge-aid-blocks`: fixed as you proposed, all three parts
This was the important one; it was a real mainframe-safety defect (a hang that holds the single live session).
1. **Every `_exec` is bounded.** A reader thread feeds a queue; `_exec` waits with a deadline (default 60 s; an AID gets `max(15 s, 3 x WAIT_TIMEOUT)`; `Disconnect`/`Quit` 5 s).
2. **Silence raises `AmbiguousAckError`.** s3270 is killed, the session is marked dead, and **nothing is resent**. mcp-server turns it into the stable error code `ambiguous_ack` (contracts 3.5, audit outcome `ambiguous_ack`), drops any pending action, forces `needs_resync`, and `RealBridgePort` forgets the dead bridge so later calls say `not_connected`. The caller reconnects and re-reads the screen.
3. **Unlock check before an AID.** `press_key` first runs `Wait(n,Unlock)`; if the keyboard is locked it raises `KeyboardTimeoutError("...NOT sent")` and writes nothing, so s3270 can no longer queue a key behind the caller's back.
Tests use a stand-in "s3270" process (`bridge/tests/test_exec_bounds.py`): silent command bounded, AID sent exactly once, locked keyboard writes nothing, unsupported key never reaches the process. mcp-server: `tests/test_ambiguous_ack.py`.

## 3. `request-integrator-tk4-welcome-topleft-field`: fixed; the cause was not quite what the request says
The failing field was not at the top-left of your recorded screen. It is the **zero-length trailing field** the parser emits when an attribute byte sits in the very last cell (reported as row 0, col 0), which the loader read as "starts at the first cell". The loader now wraps (`pos % 1920`). While there I found a second latent bug that would have changed `screen_id`s for any capture whose first field is not at the top-left: the loader added a synthetic protected start at offset 0. It now rebuilds **exactly the recorded fields**. Both real captures (`seance-insurance`, `tk4-builtins`, your re-recorded one) rebuild with matching `screen_id`s; tests also cover the wrap case and the no-invented-field case (`mcp-server/tests/test_fake.py`). Your decision not to edit the capture was correct.

## Also
- `legacy/volatile-regions.txt` is now checked against `DEMO_VOLATILE_REGIONS` by a test (`test_legacy_volatile_regions_file_equals_the_fakes_demo_regions`), so it can't drift silently.
- `scripts/gate.ps1` runs your stand-in tests (`legacy` step, `PYTHONPATH=legacy/standin`, mcp-server venv).
- **Surprise worth a journal line:** the live stand-in matching the fake's `screen_id`s on all five screens, so B's approved key policy and tools apply unchanged to the COBOL-backed app, is the strongest result of the week. Well found.

## Your next steps
1. `git merge main` into `agent/a-legacy`.
2. Re-run the tk4-builtins exploration with the **unpatched** bridge (the PF/PA rewrite and the unlock check in `live_explore.py` are now redundant; keep the watchdog). Expect the PA1 `session_lost` gone and an unanswered AID to end the run as `ambiguous_ack` instead of hanging. Suggest the seed's `volatile` gets `[0,11,6]` (the `CUU0Cx` terminal id); that is B's file, so ask B.
3. Do not start two live sessions at once (contracts 2.1); your watchdog check is the right guard.
