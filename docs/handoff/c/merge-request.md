# Merge request: `agent/c-seance-ui` -> `integration` (Agent C, web)

Date: 2026-11-08. `main` merged in at `dfa4990` (fast-forward, no conflicts). Supersedes the 2026-11-06 request.
Answers `docs/handoff/integrator/request-c-e2e-findings.md` in full: `docs/handoff/c/response-integrator-e2e-findings.md`.

## Summary

| Item | Status |
|---|---|
| **C-1** planchette stops at the first target | **Fixed**: it follows to the last event, skips steps about a screen that is not shown, has a fallback for lost `finish` events, and rests after the turn. Live: `reading > filling POLNO > pressing Enter`, never OPTION. |
| **C-2** no way to change or reconnect | **Fixed**: header **Change system** and **Reconnect**, keyboard-reachable, one `connect_system` per action (ack-tracked), disabled with a stated reason. |
| **C-3** dropped first click | **Recorded with a repro**; two mechanisms found and closed: my reconnect storm against an agent with history, and a reload inside D's 60 s controller grace turning the tab into an observer. |
| **Task 7** live mode against D | **Done**: `web/e2e/live.mjs` 9/9 on a fresh agent; your `e2e-commit` approve 6/6 and deny 6/6. |
| **Task 7.2** new protocol finding | **Filed**, not resolved: `request-integrator-unique-ids.md` (turn/message/tool-call ids restart after each connect). |
| **Task 7.3** live demo path | **Filed** for A: `request-a-live-demo-path.md`. |
| 6.5 manual NVDA pass | Left unticked on purpose (the user does it by hand). |

## Commits since the last request
- `ee3170c` web: C-1 planchette
- `0168bf8` web: C-2 controls, C-3 fresh-attach baseline, resume guard, hello gate, "not sent" notice
- one docs/e2e commit: `live.mjs`, `repro-c3.mjs`, write-ups, `tasks.md`, journal, A11Y.md, README

## Tested
- `scripts/gate.ps1 -Only web,contracts`: **pass**. The contracts step really ran this time ("fresh + valid"),
  using `mcp-server/.venv`, which I created in my worktree (gitignored, no tracked changes under `mcp-server/`).
  Web: 30 files, 422 tests. `scripts/check-ownership.ps1`: all files in C's paths.
- New fast-check properties: planchette staleness (never starts a stale step; every event started or dropped once,
  in order; ends on the last fresh event); attaching mid-session at any seq never resumes; the system controls send
  at most one `connect_system` per server answer.
- Mutation checks: reducer 7/7 killed (new M7 puts the seq-1 rule back). Planchette: staleness off, no fallback,
  never rests, no idle signal are all killed; one equivalent mutant (double-finish guard) survives and is explained.
- Live (scripted provider, fake-insurance, never the container): `live.mjs` 9/9, 0 page or console errors, axe clean
  with colour contrast in 5 live states, only the six contract client messages sent. Your `e2e-commit`: approve 6/6,
  deny 6/6. D's live check of my client (scratch copy of `b9769c9`, deleted after): 5/7 with zero invalid or unknown
  events; the 2 failures are B-1.

## Please look at (your files, not edited by me)
`scripts/e2e-stack.mjs --workaround-goto` gives 3/10 on this branch. The response file explains each failure:
1. the planchette sampler stops ~300 ms in, before any glide can finish;
2. B-1 / D-2;
3. it waits for the dialog to be detached, but the outcome stays until Dismiss (your status lists that as
   working), and the inert app then cascades into deny, audit and spirit-map;
4. the server audit counts earlier runs.

## Requests
1. `request-integrator-unique-ids.md`: contract wording (ids unique per `session_id`) and a fix for D.
2. Still open from 2026-11-06: add `playwright` 1.65.0 to tech.md (`request-integrator-playwright.md`).
3. The `ambiguous-ack.jsonl` transcript arrived on `main`: thank you. My guards accept every line of it (the
   conformance test runs over every transcript). The mock scenario picker lists it already (it reads every transcript). The
   reducer playthrough tests still use a fixed list of seven, so adding it there is a small follow-up on my side.

## Dependencies
None added since 2026-11-06.
