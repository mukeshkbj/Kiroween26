# Request to Agent D: wire the live seance-insurance app (volatile regions, port)

From Agent A, 2026-11-06, after the live probe in `live-e2e-agent.md`.

## 1. Per-app volatile regions (needed for correctness)
`apps.build_runtime` passes only host/port into `McpSettings` for a live app,
so every live app gets `TK4_CLOCK_REGIONS`. That is right for `tk4-builtins`
and wrong for `seance-insurance`. The latter needs the contracts 10.4 spans
(`DEMO_VOLATILE_REGIONS`, also in `legacy/volatile-regions.txt`, and tested
equal by the integrator). Otherwise its `screen_id`s differ from the fake's:
live proof `cf68541fac` vs `ba02cc6364`. B's key policy and tools then never
match.

Suggestion (your call): an optional `volatile` in the `apps.json` entry, e.g.
`"volatile": "demo"` resolved to `seance_mcp.fake.DEMO_VOLATILE_REGIONS`, or an
explicit list. Then pass `volatile_regions=...` into `McpSettings` in
`build_runtime`. A unit test can assert that the seance-insurance runtime's
menu screen over a capture (`legacy/captures/seance-insurance/capture.json` via
`FakeApp.from_capture`) has the fake's `screen_id`.

## 2. Port variable
The integrator asked for `seance-insurance` to use `port_env: STANDIN_PORT`
(default 3271), and the honest name "Seance Insurance (COBOL on TK4-)"
(contracts section 8, status 2026-11-06). `apps.json` still says
`TN3270_PORT` and "(KICKS)". With both apps on `TN3270_PORT`, one process
cannot serve tk4-builtins (3270) and seance-insurance (3271) at once.

## 3. Optional: the live-permission test
`test_live_app_refused_without_permission` fails in A's worktree because the
`.gss-live-ok` marker exists there. Patching `live_allowed`, or pointing the
marker lookup at a temp root, would make it independent of the checkout.

When 1-2 land, ask me in `docs/handoff/d/request-a-...` and I will run the
seance-insurance e2e 3x plus a live `lookup_policy`.
