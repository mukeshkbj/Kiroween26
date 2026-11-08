# Request to the integrator: add Playwright to the frontend pins (tech.md)

From: Agent C. Date: 2026-11-06. Type: dependency record (no contract change).

**What.** `web/package.json` now has one more dev dependency, pinned exactly:

| Package | Version |
|---|---|
| `playwright` | 1.65.0 |

**Why.** The user approved it on 2026-11-06 to take real screenshots and to run checks that jsdom cannot do (real colour
contrast with axe-core, the `event.isTrusted` safety check, real reduced-motion behaviour, zoom/reflow overflow). It is
used only by `web/e2e/shots.mjs` (`npm run shots`), never by the app bundle or the vitest suite. It drives Playwright's
own downloaded Chromium (`npx playwright install chromium`, about 120 MiB, outside the repo) against `npm run dev:mock`,
which plays recorded transcripts. It does not connect to any backend or to the live container.

**What to change.** Add the row `playwright | 1.65.0` to the "Frontend pinned versions" table in
`.kiro/steering/tech.md`. The lockfile is committed.

**Affected agents.** None.
