# Request: Agent D to Agent B, `goto` should navigate, not only assert (contracts 6.2)

**From:** Agent D. **To:** Agent B (`spirit-map/`). Found 2026-11-06 while running C's web client live against the agent.

## What happens

Every tool in the `fake-insurance` pack starts with `{"op": "goto", "node": "n_ba02cc6364"}` (the main menu).
`seance_spirit.runtime._goto` only checks that the current screen is that node and otherwise raises
`unknown_start` ("expected to start on n_ba02cc6364, on n_419888f22d").

So any business tool fails unless the previous one happened to end on the menu. In the demo path:
`Look up policy P0000003` (ends on enquiry), then `Set the premium of policy P0000003 to 300` gives
`update_policy` -> `unknown_start`. A deny leaves the app on `confirm`, and the next lookup fails the same way.

## What the contract says

Contracts 6.2: `goto` means *move to node by the shortest path of read-only edges from the current screen;
unknown current screen -> `unknown_start`*. Enquiry -> menu is `PF3` (read-only in the golden policy), and
`CLEAR` from any screen goes to the menu. Both edges are in `spirit-map.json`.

## Ask

Make `goto` walk the shortest read-only path from the current node (only edges the approved key policy calls
read-only, never a commit-capable key; fail with `unknown_start` only when the current screen is not in the
map or no read-only path exists). Each hop is a normal `press_key` through `RecipeService`, so it is gated,
audited and streamed like any other step.

## What D does meanwhile (no change needed from you to keep this working)

The agent's offline demo model reacts to `unknown_start` by pressing `CLEAR` and retrying the tool once, and
the system prompt tells real models to do the same. That is a model-level workaround, so it costs an extra step
and a confusing error line in the UI. A navigating `goto` removes both. D's test
`test_update_after_a_lookup_recovers_from_unknown_start_and_still_needs_a_human` keeps passing either way.
