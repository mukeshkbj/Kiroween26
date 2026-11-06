# seance-ui — Tasks

Owner: **Agent C**. Folder: `web/`, `.kiro/specs/seance-ui/`, `docs/handoff/c/`. Branch: `agent/c-seance-ui`. Read `docs/contracts.md` first. Never edit `agent/`, `spirit-map/`, `legacy/`, `bridge/`, `mcp-server/`, and never touch the live container or run anything against it. The UI is built against transcripts first and against Agent D's service only on the integration branch.

Ordered so the pure, testable core (protocol, reducer, geometry, scheduler) exists before the look.

## 0. Prerequisites (integrator, parallel-plan P0; blocked until done)
- [x] 0.1 `docs/contracts/examples/` has event examples, transcripts (`lookup`, `commit-approve`, `commit-deny`, `commit-expire`, `injection`, `session-lost`, `read-only`) and `SpiritMapView`/audit REST examples.
- [x] 0.2 New dev dependencies (`fast-check`, `vitest-axe`, `dagre`, Testing Library) approved by the user 2026-11-04; exact versions in `.kiro/steering/tech.md`.

## 1. Scaffold (by 9 Nov)
- [x] 1.1 Vite + React + TypeScript (strict) in `web/`; pin all versions exactly; Vitest, Testing Library, `vitest-axe`, `fast-check`, `dagre`.
- [x] 1.2 `config.ts` (`VITE_AGENT_URL`, `VITE_MODE=live|mock`), `.env.example` (no secrets), `strings.ts`.
- [x] 1.3 `protocol/types.ts` and `guards.ts` from contracts sections 3 and 4; conformance test over all committed examples (REQ-030).

## 2. Pure core (REQ-011, REQ-023, REQ-026, REQ-027) (by 11 Nov)
- [x] 2.1 `state/reducer.ts` and `selectors.ts`; `test/arbitraries.ts` generative grammar for event sequences.
- [x] 2.2 Property tests (fast-check): reducer invariants (REQ-026). Record mutation checks (remove seq de-dup, remove supersede rule, store a hidden value -> test fails).
- [x] 2.3 `terminal/geometry.ts` + property tests (round trip, containment, no overlap).
- [x] 2.4 `planchette/scheduler.ts` + property tests (REQ-027).
- [x] 2.5 `ReplayTransport` and `WebSocketTransport` (hello, token, resume, backoff) behind the `Transport` interface; transport tests with a fake WebSocket.

## 3. Terminal (REQ-002 to REQ-006) (by 13 Nov)
- [x] 3.1 `Grid`, `Row`, `FieldSpan`, `Oia`; hidden-field rendering; cursor; `ScreenAsText`.
- [x] 3.2 CRT tokens and overlay with `Full/Low/Off`; contrast arithmetic test over the token pairs at each level.
- [x] 3.3 `Planchette` with gestures, queue, reduced-motion path.
- [x] 3.4 Typing reveal.
- [x] 3.5 Screenshots for the journal: dormant, populated screen, planchette mid-glide.

## 4. Chat and connect (REQ-007 to REQ-012) (by 15 Nov)
- [x] 4.1 `Chat`, `Message`, `SafeText` (sanitised markdown subset), `Composer` (Enter/Shift+Enter/Esc).
- [x] 4.2 `StepCard` with redacted arguments, business/generic badge, untrusted legacy data style.
- [x] 4.3 `ConnectScreen` + `SystemCard`; REST client for `/api/apps`.
- [x] 4.4 Empty and error states from REQ-012, each with its next action; `Announcer`.
- [x] 4.5 Run the whole flow in mock mode with the transcripts: lookup, session lost, injection screen.

## 5. Confirmation, audit, spirit-map (REQ-013 to REQ-017) (by 19 Nov)
- [x] 5.1 `ConfirmModal` + `useFocusTrap`; REQ-029 tests (Deny first, Esc denies, 600 ms, untrusted click, one decision, expired).
- [x] 5.2 Modal transcripts: approve, deny, expire, read-only, superseded.
- [x] 5.3 `AuditDrawer` with filter, export, chain badge ("unknown" after live appends).
- [x] 5.4 `layout.ts` (dagre, deterministic) + `SpiritMap` SVG + `MapTable` + `NodePreview`; current-node tracking and path trail.
- [x] 5.5 Unknown-screen ("uncharted") state tested with a screen id absent from the map.

## 6. Accessibility and motion (REQ-018 to REQ-022, REQ-028, REQ-031) (by 22 Nov)
- [x] 6.1 Landmarks, skip links, shortcuts, splitter keyboard support, tab order test.
- [ ] 6.2 `vitest-axe` over every view and state; keyboard-only flow test.
- [ ] 6.3 `useReducedMotion` (OS + in-app); verify every animation honours it (a test that fails if an animation runs with reduce on).
- [ ] 6.4 `prefers-contrast: more`, `forced-colors`, 200%/400% zoom checks.
- [ ] 6.5 Manual pass recorded in `web/A11Y.md`: NVDA, keyboard-only, zoom, contrast values, reduced motion. Note anything not done. No conformance claim beyond "designed to meet".

## 7. Integration with the agent (by 24 Nov)
- [ ] 7.1 Switch to `VITE_MODE=live` on the integration branch against Agent D's service with the scripted provider and `fake-insurance`.
- [ ] 7.2 Fix protocol mismatches by amending the **contract through the integrator**, not by patching one side.
- [ ] 7.3 Handoff request to Agent A for the live demo path (A runs the container; C and D run nothing live).
- [ ] 7.4 Screenshots for the journal: connect, lookup with planchette, confirmation modal, graph, audit drawer, session lost.

## 8. Polish (25 Nov to 1 Dec)
- [ ] 8.1 Visual polish pass: motion timing, glow levels, copy; re-run a11y suite after each change.
- [ ] 8.2 Spec-versus-vibe experiment (judges ask for it): build the audit drawer a second time by vibe coding in a throwaway branch, record time, bugs, rework against the spec-built one in `docs/handoff/c/experiment.md`.
- [ ] 8.3 `web/README.md`: run (live, mock), keyboard shortcuts, accessibility statement linking `A11Y.md`.
- [ ] 8.4 Journal entries to `docs/handoff/c/journal.md`: one surprise per section 3, 5 and 6.
