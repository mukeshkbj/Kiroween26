# Merge request: `agent/b-spirit-map` — B-1, `goto` navigates (answers `request-b-runtime-goto-navigate.md`)

From: Agent B. Branch `agent/b-spirit-map`, main merged in first (52 commits). Touches only B's paths.

## The fix
`goto` no longer asserts the start screen; it routes to the node (contracts 6.2).

- **Where the route comes from:** the tool pack now carries a `navigation` object: every node id, and each
  **read-only, fill-free** edge between different nodes, taken from the map by the generator (no labels
  involved). The runtime does a deterministic shortest-path search over it.
  `docs/spirit-map/{fake,seance}-insurance/tools.json` were regenerated; for the fake it holds
  `CLEAR` and `PF3` from enquiry/list/update/confirm back to the menu.
- **Behaviour:** already on the target: nothing pressed. On a known screen: press the route's keys
  through `recipe_service.press_key`, check the landing node after each (`screen_mismatch` otherwise), treat a
  pending result as `unexpected_pending`. On a screen the map does not know, or with no route:
  `unknown_start` and **nothing is pressed**. A pack without `navigation` (an older one) behaves as before.
- **Budget and trace:** each routing press counts against `limits.max_steps` and appears in the trace as
  `{op: "goto", key: "PF3", node: ..., screen_id: ...}`, so the agent/UI can show it. Trace `step` is now a
  running index over all entries.
- **Safety:** no field is ever filled while routing, and only edges the explorer recorded as read-only are used.
  The gate still decides every press.

## Contract note (additive, for you)
`navigation` is a new optional top-level pack field: `{"nodes": [id], "edges": [{"from","key","to"}]}`.
`def_hash` covers tools only, so **no tool hash and no approval changed**
(`tool-approvals.json` for both apps is untouched). The ToolPack model ignores unknown fields, so
`seance_mcp.toolpack` and `contracts` need nothing; I have not edited `docs/contracts.md` (yours). You may
want a line in section 6 and `navigation` in `tools.json`'s example/schema.

## Tests (`tests/test_runtime.py`, 22 pass; spirit-map 143)
- Lookup then lookup, and lookup, lookup, list, update, in one session on one FakeApp: all succeed; the second
  tool's trace starts with a routing press (`CLEAR`/`PF3`); the update ends `pending`, nothing changed.
- `goto(home)` from each of the five nodes: ok, at most one key, only `Clear`/`PF3`, no fill, `dirty` false.
- A screen not in the map (the fake's logon screen): `unknown_start`, `pressed == []`, no fill.
- Routing presses count against the budget (`step_budget`).
- Older pack without `navigation`: fine on home, `unknown_start` elsewhere.
- Mutation: the old assert-only `goto` makes the back-to-back test fail.

## Verification
`gate.ps1 -Only spirit-map,contracts,ownership`: ownership pass, spirit-map pass (fixed and random seed).
`contracts` was skipped (no `mcp-server/.venv` in this worktree): please run the full gate and
`scripts/e2e-stack.mjs` (no workaround flag) on the integration branch. I could not run the browser stack myself.

## One thing to know
A pending commit left on the confirm screen is dropped when the next tool routes home with `PF3`/`CLEAR`
(cancel). That is the expected behaviour for a new request, but say so if you want the agent to refuse instead.
