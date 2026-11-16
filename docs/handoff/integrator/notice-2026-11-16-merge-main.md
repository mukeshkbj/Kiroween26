# To Agents A, B, C and D: `git merge main`, then your item
From the integrator, Mon 16 Nov 2026. `main` = `integration` = the commit printed by `git rev-parse --short origin/main` after you fetch. It holds everyone's work. The gate is green on both Hypothesis seeds and the browser acceptance conversation passed 3 of 3. Details: `status-2026-11-16.md`.
## Everyone, in your own worktree
```
git branch --show-current        # must print your branch
git fetch origin
git merge origin/main            # never rebase, never force-push
powershell -File scripts/gate.ps1 -Only <yours>,contracts
git push
```
If the merge conflicts in a file outside your paths, stop and write it up in `docs/handoff/<you>/`. Do not resolve it by editing someone else's file.
Two shared changes arrive with this merge (both additive, no tool hash or approval changed):
- **Contracts section 6:** the tool pack has an optional top-level `navigation` field (`{"nodes": [...], "edges": [{"from","key","to"}]}`), B's B-1. It is now in the pydantic model, `toolpack.schema.json` and the example pack.
- **`check_stream`** (`seance_mcp.contracts.check`) now also enforces D's screen and focus rules of contracts 4.3: a call's `screen`/`field_focus` events fall between its `tool_call` and `tool_result`; its first `screen` is `before` and there is exactly one `before`; a `screen` outside a call is `snapshot`; `field_focus.screen_id` is never empty.
## Per agent
| Agent | What to do |
|---|---|
| **A** | **Repeat your live `seance-insurance` run on the merged tree**, as you offered: D's `agent/tests/test_live_e2e.py` (3 read-only runs, `SEANCE_ALLOW_COMMIT=0`) and your `legacy/scripts/live_agent_evidence.py --app seance-insurance --lookup P0000003`. Then replace `docs/handoff/a/live-e2e-seance-insurance.md` with the real result (no longer a pre-merge preview). Check D's four points again: `business: 3`, menu `screen_id` `ba02cc6364`, lookup from COBOL, no "pack volatile regions not used" warning. Run read-only. Do **not** approve an update on the live system; ask the user first. Stop Kiro's idle `seance_mcp` servers before you start, as last time. After that, C's `docs/handoff/c/request-a-live-demo-path.md` (the browser live demo) is next if the user wants it. |
| **B** | Three routed items are still yours: `request-b-explore-host-port.md` (explore/replay honour `TN3270_HOST`/`PORT`), `request-b-tk4-volatile-terminal-id.md` (terminal id `[0,11,6]` volatile in the tk4-builtins seed) and the tk4-builtins re-run with the fixed bridge (`request-b-promote-a-live-runs.md`, section 2; A runs it, you promote). One new check: your packs now sit next to a schema that knows `navigation`. Run `python -m seance_mcp.contracts.check` and validate `docs/spirit-map/*/tools.json` against `docs/contracts/schemas/toolpack.schema.json`. Tell me if a real pack fails. |
| **C** | Nothing new for you to build. Re-run `gate.ps1 -Only web,contracts`. If your mock replay or `live.mjs` records a stream, it must now pass the stricter `check_stream`. The manual accessibility pass (seance-ui 6.5: NVDA, zoom, High Contrast) is the user's. If you have the checklist ready for them, put it in `docs/handoff/c/`. |
| **D** | Your d-3, d-4 and d-5 are all on `main`. Nothing left in the queue. The integrator's `check_stream` now contains your screen/focus rules, so the comment in `agent/tests/_stream.py` ("stricter than the integrator's copy for now") is out of date. Update the docstring when you next touch the file, or drop your copy in favour of the integrator's. Re-run `gate.ps1 -Only agent,contracts`. |
