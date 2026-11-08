# Green Screen Séance: web UI

React + Vite + TypeScript. Left: the 3270 screen as a 24x80 phosphor grid with a planchette that glides to the field the
agent is reading or filling. Right: the séance chat. The UI is a **view and a decision-maker, never a terminal**: it
sends only `connect_system`, `user_message`, `confirm_decision`, `cancel_turn` and `ping` (docs/contracts.md 4.4), and
the only thing it can do to the legacy system is let a person approve or deny a pending action.

## Run

```
cd web
npm install        # exact pinned versions, see .kiro/steering/tech.md
npm run dev        # http://localhost:5173 (live)
npm run dev:mock   # same, replaying recorded sessions (no backend)
```

| Variable (`.env.example`) | Meaning |
|---|---|
| `VITE_MODE` | `live` (default): talk to the agent. `mock`: replay recorded sessions, no backend needed. |
| `VITE_AGENT_URL` | Agent base URL, default `http://127.0.0.1:8000`. Not a secret. |
| `VITE_REPLAY_SPEED` | Mock playback speed multiplier, default `1`. |

**Mock mode** plays the transcripts in `docs/contracts/examples/transcripts/` through the same transport interface as
the websocket. It is labelled `REPLAY` in the header and the status line so it can never pass for a live session.
Pick a scenario in the header or with `/?scenario=<name>`: `lookup`, `commit-approve`, `commit-deny`, `commit-expire`,
`read-only`, `injection`, `session-lost`. The page tells you what the recording is waiting for ("press Deny", "send a
message"). Systems, audit log and spirit-map come from the committed REST examples.

**Live mode** talks to the agent service (`agent/`, Agent D). To check the whole UI against it in a real browser
(scripted provider, fake-insurance, nothing live):

```
# terminal 1, repo root (see agent/README.md for the venv)
$env:LLM_PROVIDER='scripted'; $env:SEANCE_ALLOW_COMMIT='1'; agent\.venv\Scripts\python.exe -m seance_agent
# terminal 2
$env:VITE_MODE='live'; npx vite --port 5173
# terminal 3
node e2e/live.mjs        # 9 checks; report and live-*.png in docs/handoff/c/shots/
```

The agent keeps the controller seat for 60 s after a tab closes, so a new tab inside that window is an observer
(controls disabled, reason shown). `live.mjs` waits that out. Once connected, the header has **Change system** and
**Reconnect**.

## Test

```
npm test                  # vitest --run: unit, component, property-based, axe
npm run typecheck
powershell -File test/mutation-check.ps1         # the reducer's tests must fail when it is weakened
powershell -File test/mutation-check-modal.ps1   # same for the confirmation modal's safety rules
```

The contract examples in `docs/contracts/examples/` are read by relative path, never copied. A guard that rejects any
of them, or a reducer that cannot play any transcript, fails the suite (REQ-030).

## Real-browser screenshots and checks

```
# terminal 1
npm run dev:mock
# terminal 2 (first time: npx playwright install chromium)
npm run shots
```

Writes PNGs and `browser-checks.json` to `docs/handoff/c/shots/` and runs axe-core (with colour contrast) in Chromium.
It plays recordings only; it never touches a backend or the live container.

## Keyboard shortcuts

Every shortcut needs `Alt+Shift`; none works as a bare key.

| Keys | Action |
|---|---|
| `Alt+Shift+A` | Toggle the audit log |
| `Alt+Shift+M` | Switch between screen and spirit-map |
| `Alt+Shift+C` | Move focus to the chat |
| `Alt+Shift+S` | Move focus to the screen |
| `Alt+Shift+E` | Cycle effects: Full, Low, Off |
| `Alt+Shift+R` | Toggle reduced motion |
| `Alt+Shift+T` | Toggle screen as text |

In the chat: `Enter` sends, `Shift+Enter` adds a line, `Esc` cancels the running turn. On the splitter: arrows resize,
`Home`/`End` snap. In the confirmation dialog: **Deny has focus when it opens, and `Esc` means Deny.**

## Safety behaviour worth knowing

- Approve is disabled for 600 ms after the dialog opens and only a trusted user activation can trigger it.
- The dialog shows the key, the screen, the fields and the time left from the gate and the screen. The agent's own
  description sits in a separate block labelled "The agent says (unverified)".
- Nothing a user sent or decided is ever re-sent automatically. If the socket is down the message is marked as not
  sent.
- Everything from the server is rendered as text. Hidden-field values never reach the state or the DOM.

## Accessibility

Designed to meet WCAG 2.2 AA: keyboard-only operation, skip links and landmarks, live regions, reduced motion (OS and an
in-app toggle), `prefers-contrast` and `forced-colors` handling, rem font sizes, no fixed widths that block 400% zoom.
Automated results, computed contrast values, known limits and the **manual checks that are still open** (NVDA, zoom,
real-browser trusted-event check) are in [`A11Y.md`](./A11Y.md). We do not claim conformance.

## Layout

```
src/protocol/   types, guards (runtime validation), transports (websocket, replay), REST, mock data
src/state/      the pure reducer, selectors, and the store that wires a transport to it
src/terminal/   grid, status line, geometry, palette/contrast, typing reveal
src/planchette/ pure scheduler and the animated pointer
src/chat/       chat, composer, step cards, safe markdown
src/connect/    system list, state banners
src/confirm/    confirmation modal, focus trap
src/audit/      audit drawer
src/map/        spirit-map graph (dagre layout), table, preview
src/a11y/       announcer, skip links, reduced motion, accessibility tests
src/layout/     splitter and shortcut logic
```
