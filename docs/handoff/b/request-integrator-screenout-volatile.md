# Request to the integrator: expose the volatile mask on ScreenOut (additive)

From: Agent B (spirit-map). Not blocking; a nice-to-have for task 7 (live TK4- maps).

**What.** `seance_mcp.screens.ScreenOut` has no `volatile` field, although the bridge's `ScreenModel.volatile`
(flat positions masked out of `screen_id`) exists. Add an optional `volatile: list[tuple[int, int, int]]`
(row, col, length runs) to `ScreenOut`, 0-origin, additive within `v: 1`.

**Why.** Contracts section 10.4 says B "treats the volatile spans reported per node as part of node identity".
Through the service the explorer cannot see them, so today the human seed lists the regions
(`explore.seed.json` -> `volatile`), copied from `DEMO_VOLATILE_REGIONS` for the fake and from
`TK4_CLOCK_REGIONS` for TK4-. That works, but the seed can silently disagree with the server's
`VOLATILE_REGIONS`, and a wrong list changes which protected fields count as output fields.

**Sections affected.** 3.1 (`ScreenOut`), the generated schemas/examples under `docs/contracts/`.
Consumers must already ignore unknown fields (section 12.3).

**Until then.** The seed's `volatile` list is authoritative for spirit-map. Nothing else is blocked.
