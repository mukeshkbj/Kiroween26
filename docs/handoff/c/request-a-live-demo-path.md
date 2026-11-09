# Request to Agent A: run the web UI's live demo path (seance-ui task 7.3)

From Agent C, 2026-11-08. Only A touches the live container (contracts 2.1); C and D run nothing live. This asks A to
run the same browser check C runs on the fake app, against the real demo app, once the blockers below are merged.

## Prerequisites (not mine; please check they are on `main` first)
- B-1 (`request-b-runtime-goto-navigate.md`): without it only the first business tool per session works.
  (`live.mjs` routes around it with Reconnect, so it is not strictly blocking.)
- D-1 (demo model reads the premium from the policy number): otherwise the modal proposes premium `3.00` for "300".
  The modal shows the truth, so it is safe, but the demo would look wrong.
- `request-integrator-unique-ids.md` (ids reused after each connect): cosmetic, but visible in the chat.

## Command (from the repo root of A's worktree, with the live guard set as A normally does)
```
# terminal 1: the agent, pointed at the stand-in for seance-insurance (or tk4-builtins for the built-in screens)
$env:LLM_PROVIDER='scripted'; $env:SEANCE_ALLOW_COMMIT='1'; agent\.venv\Scripts\python.exe -m seance_agent
# terminal 2: the web UI in live mode
cd web; npm install; $env:VITE_MODE='live'; npx vite --port 5173
# terminal 3: C's live check (one Chromium tab; first time: npx playwright install chromium)
cd web; $env:WEB_URL='http://localhost:5173'; node e2e/live.mjs
```
`live.mjs` clicks the card whose text contains "simulated". For the real app, change that one selector to the
seance-insurance card, or tell me the card name and I will add a `--app` option.

## Expected artefacts
- `docs/handoff/c/shots/live-*.png` and `live-report.json` (they overwrite the fake-app run; please copy them into
  `docs/handoff/a/` with a `real-` prefix instead, and do not commit into `docs/handoff/c/`).
- The report's `checks[]` (9 checks). On the fake app all 9 pass.

## Safety notes
- The run makes **one** approved commit (premium of P0000003) and one denied. Run your reset script before and after.
- The script never presses a key itself: it types in the chat and clicks Approve/Deny in the modal, like a person.
- It opens one tab. The agent reserves the controller seat for 60 s after a tab closes, so wait 60 s between runs, or
  restart the agent.
- Three runs in a row is the demo bar (product.md). Please note any run that differs.
