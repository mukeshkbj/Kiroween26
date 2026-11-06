# START HERE: Agent C (web UI)

Branch `agent/c-seance-ui`. Worktree `D:\Kiro\gss-wt\c\Kiroween26` (open exactly this folder as your Kiro workspace).
You own: `web/`, `.kiro/specs/seance-ui/`, `docs/handoff/c/`. Nothing else.

## First command, always
```
git branch --show-current
```
It must print `agent/c-seance-ui`. If it prints anything else, stop and tell the user.

## Rules that never bend
1. **Write only in your paths.** Need a change in the agent, the contracts or anything else? Write `docs/handoff/c/request-<owner>-<slug>.md` and carry on.
2. **You never touch the live container** and you never run the Python stack against it. You do not need to: you build against recorded transcripts and, later, against Agent D's service with the `fake-insurance` app.
3. `docs/contracts.md` (tag `contracts-v1`) is law. Read sections 3, 4, 5 and 7.3 closely. If the protocol is wrong or unclear, do not patch your side silently: request a contract change from the integrator.
4. **The UI is a view and a decision-maker, never a terminal.** It sends only the messages in contracts 4.4. The confirmation modal is a safety control: Deny is the default focus, Esc denies, Approve is delayed and needs a trusted user event, the content comes from the gate's fields plus the screen (the gate snapshot can be empty on review screens, so draw the screen), and the agent's own words are labelled unverified. Hidden-field values never enter the DOM. Everything from the server renders as text, never as HTML.
5. Rhythm: `git merge main` each day (no rebasing pushed branches, no force-push); one commit per task, message `web: <task id> <what>`; `powershell -File scripts/gate.ps1 -Only web,contracts` and `scripts/check-ownership.ps1` before a PR. `git push -u origin agent/c-seance-ui`; never push to `main`.
6. Journal: dated lines to `docs/handoff/c/journal.md` (one real surprise per stage); keep screenshots under `docs/handoff/c/shots/`. The spec-vs-vibe experiment (tasks 8.2) goes in `docs/handoff/c/experiment.md`.
7. Kiro sub-agents (context-gatherer) may be used for read-only research inside this worktree only.

## Read, in order
1. `docs/contracts.md` sections 3, 4, 5, 7.3, 11.
2. `docs/contracts/examples/README.md`, then the files: `events/*.json`, `transcripts/*.jsonl` (play these in mock mode), `rest/*.json`, `spirit-map/spirit-map-view.json`. JSON Schemas are in `docs/contracts/schemas/`.
3. `.kiro/specs/seance-ui/{requirements,design,tasks}.md`.
4. `.kiro/steering/tech.md` ("Frontend pinned versions": use **exactly** those versions, no `^` or `~`).

## Facts you need
- Use the contract files **by relative path from `web/`**; do not copy them (`../docs/contracts/...`; allow it in `vite.config.ts` via `server.fs.allow`, and import transcripts with Vite's `?raw`/`import.meta.glob`). If the repo layout makes this awkward, ask the integrator.
- Transcript format is in `docs/contracts/examples/README.md`: `{"dir":"server","delay_ms":N,"event":{...}}` and `{"dir":"client","msg":{...}}`. Replay mode must show an unmissable REPLAY badge.
- `ScreenOut` rows are 24 x 80, positions 0-origin, `field.value` is `null` for hidden fields. A field's `col` is its first data column; the attribute byte is at `col - 1`.
- `vitest-axe` 0.1.0 may not work with vitest 5. If it does not, call `axe-core` directly from a small helper and say so in `docs/handoff/c/journal.md` (tech.md allows this).
- `node` is v24, `npm` 11. Commit `package-lock.json`.

## Milestones (docs/parallel-plan.md)
Sun 8 Nov: reducer plus property tests. Tue 10 Nov: grid and OIA rendering in mock mode. Sun 15 Nov: planchette, chat, connect screen, states. Tue 24 Nov: confirmation modal, audit drawer, spirit-map view, automated a11y green, integrated with Agent D on the `integration` branch.

## Your first prompt (paste into the agent)
```
You are Agent C of the Green Screen Seance parallel build. First run `git branch --show-current`; it must print agent/c-seance-ui, otherwise stop and tell me.
Read docs/handoff/c/START-HERE.md, docs/contracts.md (sections 3, 4, 5, 7.3, 11), docs/contracts/examples/README.md, .kiro/specs/seance-ui/* in full and the "Frontend pinned versions" table in .kiro/steering/tech.md.
You own web/, .kiro/specs/seance-ui/ and docs/handoff/c/ and nothing else. Never touch the live container. The UI sends only the client messages in contracts 4.4.
Start with tasks 1 (scaffold with the exact pinned versions) and 2 (pure core: protocol types and guards, reducer, geometry, planchette scheduler, with fast-check property tests and mutation checks, and the replay transport that plays docs/contracts/examples/transcripts). Commit per task (web: <task id> ...), tick tasks.md, journal surprises in docs/handoff/c/journal.md, run scripts/gate.ps1 -Only web,contracts before each push. Anything you need from another folder goes in a request file under docs/handoff/c/. Report when task 2.5 is done.
```
