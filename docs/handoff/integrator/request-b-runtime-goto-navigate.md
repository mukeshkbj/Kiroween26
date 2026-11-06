# Request to Agent B: `goto` must navigate, not only assert (blocks the demo)

From the integrator, found in the full-stack browser run on 2026-11-06 (`status-2026-11-06.md`, "Full-stack run"). **Highest priority of all open items.** Your code (`spirit-map/src/seance_spirit/runtime.py`).

## What happens
In any real conversation **only the first business tool works**. Every later one fails `unknown_start`:
```
> Look up policy P0000003   -> ok, A. ROSE              (session starts on the menu)
> Look up policy P0000005   -> error unknown_start      (session is still on the enquiry screen)
> Set premium to 300 ...    -> error unknown_start
```
Reproduced in the browser, over the websocket without a browser, and in-process with `build_service` + your pack. Starting the second lookup from the menu makes it pass, so `goto` is the only cause.

## Why
`_goto(service, node_id, screen)` (runtime.py ~line 96) only **checks** `_nid(screen.screen_id) == node_id` and raises `unknown_start` otherwise. Contracts section 6.2 says `goto` moves to the node **by the shortest path of read-only edges from the current screen**, and `unknown_start` is only for a current screen the map does not know. Your tests always start a tool on `home`, so the gap never showed.

The map already has every edge needed: `enquiry -PF3-> menu`, `list -PF3-> menu`, `update -PF3-> menu`, `confirm -PF3-> menu` and `* -CLEAR-> menu`, all `read_only: true`.

## Fix
1. `goto`: if the current node is the target, done. Else, if the current `screen_id` is a known node, take the shortest path over **read-only edges without fills** (`graph.py` already has the shortest read-only path) and press each key through `recipe_service.press_key`. After every press, check the landing node; a mismatch is `screen_mismatch`. A `pending` result is `unexpected_pending` (it cannot happen on read-only edges, but keep the guard). If the current screen is not in the map: `unknown_start`, as now.
2. Count goto's presses against the step budget and add each one to the `trace`, so the agent and UI can follow it (the planchette shows the key presses).
3. Never fill a field while routing, and never use an edge that is not read-only. The explorer's safety rules apply.

## Tests (please include)
- Two business tools in a row on one `FakeApp` session (lookup then lookup; lookup then update) both succeed, and the trace of the second starts with the routing presses.
- From every node in the fake-insurance map, `goto(home)` succeeds, using only read-only keys (property test over start nodes).
- Starting on a screen not in the map still gives `unknown_start` and presses nothing.
- Mutation check: replace navigation with the old assert, and the two-in-a-row test fails.

## After the fix
Tell me in `docs/handoff/b/`. I re-run `scripts/e2e-stack.mjs` (no workaround flag). Today it passes 4 checks and the rest fail only because of this.
