# tk4-builtins

`explore.seed.json` is the human seed (non-commit keys only, credential-like fields denied,
clock and terminal-name regions volatile).

`spirit-map.partial.json` is **not** the app's map. It is Agent A's first live run (2026-11-06,
`docs/handoff/a/live-runs/tk4-builtins/`), kept as evidence and promoted unmodified:

- 7 nodes, 12 edges, 17 frontier items, run status still `running` (A's watchdog stopped it).
- It was blocked by two bridge bugs, both since fixed on main: PF/PA keys sent in a form s3270
  rejects, and an unbounded wait on the next AID from a blank VTAM screen.
- Its welcome node `n_f8176b4718` embeds the terminal name `CUU0C1`; the id changes per connection.
  The seed now marks row 0, col 11, length 6 volatile, so the next run gets one stable welcome node.
- Six of the seven nodes are blank unformatted screens reached with CLEAR / PA1-3 / PF13-14.
- The `Logon ===>` field is in the frontier as `unsafe_field` (the USERID|LOGON deny worked).

A second live run with the fixed bridge is requested in
`docs/handoff/b/request-a-tk4-second-live-run.md`. Its output replaces this file as `spirit-map.json`.
