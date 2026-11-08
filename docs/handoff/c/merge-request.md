# Merge request: `agent/c-seance-ui` -> `integration` (Agent C, web)

Date: 2026-11-06. Branch tip: see `git log origin/agent/c-seance-ui -1`. `main` merged in at `fe1ca58` (no conflicts).

## Summary

The seance-ui spec, tasks 1 to 6 and 8, built and tested in **mock/replay mode** against the committed contract
examples. Task 7 (live mode against Agent D's service) is **not done**: `agent/` is not on `origin/main` yet (checked
repeatedly through 2026-11-06; last `origin/main` is `0263f4d`). I did not merge D's branch into mine, because only the
integrator merges agent branches and C's work must not depend on D's unmerged code.

What is in it:
- **Protocol:** TS mirror of contracts 3, 4, 5, 7.3 (`web/src/protocol/types.ts`), fail-closed runtime guards, both
  transports (websocket with hello/token/resume/backoff, and replay of the transcripts), REST client.
- **State:** one pure reducer, property-tested with fast-check, with mutation checks (`web/test/mutation-check*.ps1`).
- **Views:** 24x80 grid + OIA, CRT effects with Off/Low/Full, planchette, typing reveal, chat with step cards and safe
  markdown, connect screen, state banners, confirmation modal, audit drawer, spirit-map graph + table + preview, app
  shell with landmarks, skip links, splitter, narrow layout and Alt+Shift shortcuts.
- **New since the last status:** `ambiguous_ack` as its own state as you asked (banner with the exact wording, a step
  note, "Reconnect to <system>" that sends one `connect_system` and nothing else, proven by a spy-transport test);
  plain wording for `live_not_allowed`; `ScreenOut.volatile` mirrored in types and guards.

## Tested

- `scripts/gate.ps1 -Only web`: **pass** (tsc clean, vitest 27 files / 384 tests). `scripts/check-ownership.ps1`: all
  124 touched files in C's paths. The `contracts` gate step is skipped in this worktree (no `mcp-server/.venv`).
- Conformance: the guards accept every file in `docs/contracts/examples/` after your 2026-11-05/06 regeneration, and
  the reducer plays all seven transcripts.
- Real browser (Chromium 158 via Playwright, `npm run shots`): axe-core with colour contrast **0 violations in 8
  states**; 0 px horizontal overflow at 390 and 320 px; script `click()` on Approve does not approve, a real click does;
  0 Web Animations with reduced motion. Screenshots in `docs/handoff/c/shots/`, numbers in `browser-checks.json`, record
  in `web/A11Y.md` section 1b.
- Spec-vs-vibe experiment (8.2): `docs/handoff/c/experiment.md`.

## Not done / blocked (please read)

| Item | Status |
|---|---|
| **Task 7 (live mode with D)** | Blocked on D being on `main`. Ready to do: `VITE_MODE=live` already uses the websocket transport and REST client; D's own live check (`agent/scripts/c_live_check/live-agent.test.ts` on D's branch) already drives my transport, guards and reducer against D's server. Once `agent/` is on `main` I merge `main` and run it. |
| **6.5 manual pass (NVDA, zoom, Windows High Contrast)** | Left unticked on purpose: the user will do it by hand. Checklist in `web/A11Y.md` section 3. |
| 7.4 live screenshots | Depends on task 7. |

## Requests to you (integrator)

1. **Add `playwright` 1.65.0** to the Frontend pinned versions table in `.kiro/steering/tech.md`. Approved by the user on
   2026-11-06; details in `docs/handoff/c/request-integrator-playwright.md`. Dev only, never in the bundle.
2. **A transcript for `ambiguous_ack`** in `docs/contracts/examples/transcripts/` (connected -> commit tool ->
   `tool_result{error_code: ambiguous_ack}` -> `session_state{session_lost}`), so mock mode can show and replay the new
   state. Until then it is covered only by unit tests with hand-built events.
3. **Ping C when D is on `main`**, and I will do task 7 the same day.

## Dependencies added in this branch

All exact, all from tech.md's table except `playwright` (request 1). Lockfile committed.

## Notes for D (no action from you)

- In live mode C sends only `hello`, `connect_system`, `user_message`, `confirm_decision`, `cancel_turn`, `ping`.
- The store never re-sends; a send that fails is shown as "not sent".
- The UI ignores unknown fields and logs unknown event types once.
