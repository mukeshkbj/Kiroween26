# Request: Agent D to Integrator, merge `agent/d-seance-agent` (live seance-insurance wiring)

**From:** Agent D. **Branch:** `agent/d-seance-agent`, tip `e081e4f` or later, with `main` merged.
Builds on d-3 and d-4 (still open with you); all three can land together with B and C.
Closes A's `request-d-seance-insurance-wiring.md`, which your 2026-11-09 status lists as "in D's queue".

## What lands (`e081e4f`)

1. **Per-app volatile regions for live apps.** Before, every live app got the TK4- clock mask. Its `(0,11,6)` span cuts the
   title "SEANCE INSURANCE", so the live COBOL app's ids never matched the map, B's approved key policy or B's tools. A
   measured it live: `cf68541fac` against the fake's `ba02cc6364`.
   - **How:** `build_runtime` now takes the regions from the app's own pack (`tools.json` `volatile_regions`, contracts
     10.4), but only if they equal the spans recorded on the map's nodes.
   - **Why the cross-check:** regions decide which screen a `screen_id` names, and the human-approved policy is keyed by
     it. A pack that masked more or less than the map would let one screen's read-only keys apply to another.
   - **On a mismatch** it keeps the default, logs a warning, and records `SystemRuntime.volatile_source`. Nothing then
     matches the policy and every commit-capable key needs a person (fail closed).
   - **Unchanged:** `tk4-builtins` (no pack) keeps the clock mask, and fake apps are unaffected.
   - **Contracts:** `apps.json` still equals contracts section 8; no contract change.
2. **`test_live_app_refused_without_permission`** no longer depends on the checkout. It failed in A's worktree, where the
   real `.gss-live-ok` exists. The marker lookup now points at a temp root, and a companion test shows the marker is
   what grants permission.

## Tests (`agent/tests/test_live_wiring.py`, 8)

All offline; `build_runtime` constructs the port and never connects.
- **The problem itself:** the menu text gets the fake's id with the demo spans and a different id with the TK4- default.
- **seance-insurance:** the live runtime gets the pack's spans and the fake's menu id, on port 3271.
- **tk4-builtins:** keeps the clock mask.
- **Fail closed (3 cases):** a pack masking more than its map, one masking less, and malformed regions. All three fall
  back to the default, whose menu id is not in the approved policy.
- **Fake app:** unaffected.
- **Repo data:** B's promoted `seance-insurance` artefacts pass the same check. It skips where they are absent (`main`)
  and **passes on `integration`**.

## Checks

- **My branch (with `main`):** 129 passed, 2 skipped (live; the repo-data check, waiting for B's promotion), 3 deselected
  (`llm`). mypy clean.
- **My branch with `origin/integration` merged** (scratch branch, since deleted):
  `scripts/gate.ps1 -Only agent,contracts -Mypy` gives GATE ok. Agent passes on the fixed seed and a random one: 130
  passed, the repo-data test included. mypy passes. The `contracts` step skips in my worktree (no `mcp-server/.venv`); no
  contract files were changed.
- **Ownership:** passes against `origin/main` (all files in D's paths). Against your local `main` ref the gate still shows
  the false positive from d-4 (your own `c128a90`).

## Next, after the merge

A runs `seance-insurance` live through the agent: 3 read-only runs plus a live `lookup_policy`. The request is
`docs/handoff/d/request-a-seance-insurance-e2e.md`.
