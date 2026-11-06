# For Agent B: captures are ready

Two capture files are committed under `legacy/captures/` (gss.capture/1,
contracts section 2.3), produced live by Agent A through the real bridge +
ScreenParser (so screen_ids, fields and labels are genuine):

## `legacy/captures/seance-insurance/capture.json`  (the demo app)
- Six screens: `menu`, `enquiry`, `enquiry_result`, `list`, `update`, `confirm`.
- Loads cleanly via `FakeApp.from_capture(...)` (every screen_id reproduces).
- Business data in it (e.g. `A. ROSE`, the 8 policies) is returned by the REAL
  COBOL `SEANCSVC` on TK4-; the 3270 presentation is the Python stand-in
  (`legacy/standin/`). Field names, keys and `VOLATILE_REGIONS` match contract
  section 10 and `seance_mcp.fake` exactly, so your explorer/labeller/generator
  treat it like a real KICKS app. `VOLATILE_REGIONS` is in
  `legacy/volatile-regions.txt`.
- Transitions cover: menu->enquiry/list/update (option 1/2/3), enquiry lookup,
  update->confirm, and all PF3/CLEAR backs.

## `legacy/captures/tk4-builtins/capture.json`  (your second target)
- Two REAL TK4- screens: `welcome` (live clock, declared volatile) and
  `logon_rejected` = `IKJ56420I USERID XYZZY NOT AUTHORIZED TO USE TSO` after
  the harmless non-existent test id `XYZZY`. No logon completed, no password.
- **Heads-up / known issue:** `FakeApp.from_capture` currently rejects this file
  with `welcome: field starts at the first cell`. The TK4- welcome has a field
  whose attribute byte is at buffer position 0, and
  `seance_mcp.fake._spec_from_screen_out` raises on `col-1 < 0`. The capture data
  itself is correct and real; it is the loader that cannot rebuild a top-left
  field. I have NOT edited the capture to work around it (that would falsify a
  real screen). I filed `request-integrator-tk4-welcome-topleft-field.md` asking
  the integrator to handle a position-0 field in the loader. Until then, use the
  `welcome` screen's `rows`/`fields` directly, or the `logon_rejected` screen,
  which has no top-left field.

Need a different screen, more transitions, or a re-capture after a layout change?
File `docs/handoff/b/request-a-...md` and I will run it live.

2026-11-05, Agent A.
