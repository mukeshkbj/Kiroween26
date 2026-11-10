# To Agents A, B and C (and D after its next merge request): `git merge main` now

From the integrator, Tue 10 Nov 2026. `main` = `4293301` (pushed). B, C and D are on it, and the gate is fully green on both seeds. The browser acceptance conversation passed 3 of 3. Details: `status-2026-11-10.md`.

## Do this, in your own worktree
```
git branch --show-current        # must print your branch
git fetch origin
git merge origin/main            # never rebase, never force-push
powershell -File scripts/gate.ps1 -Only <yours>,contracts
git push
```
If the merge conflicts in a file outside your paths, stop and ask in `docs/handoff/<you>/`; do not resolve it by editing someone else's file.

## What changes for you
| Agent | Note |
|---|---|
| **A** | Nothing of yours changed. You now have the live stack on `main`, so when D's `seance-insurance` wiring fix lands (your `request-d-seance-insurance-wiring`), `docs/handoff/d/request-a-live-e2e.md` can run on the COBOL-backed app. |
| **B** | Your B-1 is on `main`. Your three routed items are still open (`request-b-explore-host-port.md`, `request-b-tk4-volatile-terminal-id.md`, the tk4-builtins re-run). The tool-pack `navigation` field goes into contracts section 6 shortly (integrator). |
| **C** | Your live mode is on `main`. Contracts 4.2 now states your unique-ids text (`response-c-unique-ids.md`). D added `session_busy` ("A change is waiting for your decision; decide on it first."). It should be rare, because tool calls wait for the decision, but show it as a plain notice, not a tool failure. |
| **all** | The user changed `.kiro/` on `main` (steering scope, safety review on demand, idle MCP off). Re-open your Kiro window if your steering or tools look stale. |
