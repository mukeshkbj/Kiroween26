# Request to Agent B: add the terminal id to the tk4-builtins volatile regions

From the integrator, relaying Agent A (`docs/handoff/a/response-b-live-run-tk4-builtins.md`, surprise 1). Your file (`docs/spirit-map/tk4-builtins/explore.seed.json`), so you make the change.

**What.** Row 0 of the TK4- VTAM welcome screen shows the terminal device (`CUU0C0`, `CUU0C1`, ...). It changes per connection, so every other connection produced a new welcome node (`n_a713...` versus `n_f817...` in A's runs) and a different `screen_id` for the same screen.

**Fix.** Add `[0, 11, 6]` (row, col, length, 0-origin: the `CUU0Cx` text) to the seed's `volatile` list: `[[0,11,6],[0,64,16],[1,64,16]]`.

**Also check, in the same change.**
1. `mcp-server/src/seance_mcp/config.py` has `TK4_CLOCK_REGIONS = ((0, 64, 16), (1, 64, 16))`. The server must mask the terminal id too or its `screen_id` will disagree with your map. That file is mine: this request is also my to-do (I will add `(0, 11, 6)` there and regenerate the contract examples; see `request` status in `status-2026-11-06.md`). Until I confirm, do not change `VOLATILE_REGIONS` anywhere else.
2. A's captures use `[[0,64,16],[1,64,16]]` for `volatile`; A will re-record.

**Why not just trust the data.** A map keyed on a screen_id that includes the terminal id is silently wrong on the next connection. This is the same class of bug as contracts 10.4.

Done when: the seed has the new region, a test (or the existing seed test) asserts it, and your gate is green.