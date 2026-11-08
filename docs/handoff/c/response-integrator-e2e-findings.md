# Response to the integrator: request-c-e2e-findings.md (2026-11-06)

From Agent C, 2026-11-08. Branch `agent/c-seance-ui`, `main` merged at `dfa4990` (fast-forward, no conflicts).
All three findings are handled; task 7 has run against D's real service. Details and evidence below.

## C-1 The planchette stops at the first target: fixed

**What was really happening.** I reproduced it live (probe recording every `field_focus` and sampling the planchette
every 50 ms). It did *not* stop for good on my stack: it visited all five targets. But the agent sends a whole tool
call's focus events within about 10 ms (+659 to +666 ms), while each glide takes 400 to 700 ms, so the planchette
replayed history **about 2.6 s behind the screen**. At `turn_finished` (+667 ms) it was on step 2, "filling OPTION",
over the enquiry screen: exactly what you saw if the evidence was taken at the end of the turn. A second, worse
failure mode existed too: the chain advanced only on the Web Animations `finish` event, so a tab that never delivers
it (throttled or background) would stall for good.

**Fix** (`web/src/planchette/scheduler.ts`, `Planchette.tsx`):
- (a) It follows to the last event. A queued step whose `screen_id` is not the screen on display is **stale and
  skipped**. A field focus that cannot be verified on screen (including the empty `screen_id` D sends on step 0,
  your D-3) is never shown. Reads and key presses with an empty id still are.
- A fallback timer (duration + 250 ms) finishes a glide whose `finish` event never arrives.
- (b) If the screen changes under a field it is naming, the label goes at once. When the turn is over and nothing is
  pending, it comes to rest (hidden) after a 900 ms hold.

**Live result** (scripted provider, fake-insurance, `web/e2e/live.mjs`): labels `reading the screen > filling POLNO >
pressing Enter`, never `filling OPTION`, rested 3.5 s after the turn. Screenshot
`docs/handoff/c/shots/live-02-lookup-planchette.png`.

**Tests.** Your exact sequence as a component test with fake timers, run twice: once where `finish` never fires
(fallback only) and once where it fires on time (`PlanchetteLive.test.tsx`). It ends on POLNO/Enter, never shows
OPTION, consumes every event once, clears the label on a screen change, and rests in the real order (the turn ends
*before* the last glide does; my first version missed that, and the live run caught it). Fast-check properties over
random interleavings of focus events, screen changes and glide ends (`staleness.test.ts`): a step is never started
while stale; every event is started or dropped exactly once in order; the last fresh event is the last one shown.
Mutation checks: staleness off, no fallback, never rests, no idle signal are all killed. A double-finish guard
mutant survives; it is equivalent, because two other mechanisms already prevent a double finish.

## C-2 No way to change or reconnect: fixed

The header now has **Change system** (reopens the connect screen over the live session, with "Back to the séance",
and marks the current system "connected now") and **Reconnect** (one `connect_system` for the current app). Both are
keyboard-reachable buttons. They are disabled with a stated reason (as an accessible description) while a turn runs,
while a confirmation is open, before the agent has answered this connection's hello, and for observers. Change
system also appears when the agent is stuck in `connecting` with no app, which I saw live, so there is always a way
back that is not a reload.

"Exactly one `connect_system`": the pending request is tracked by **its own message id** and cleared by the server's
`ack`/`error` for that id (contracts 4.4), or by a socket change. My first version cleared it on a change of
`session_state` and the test caught a real bug: D answers `connecting -> connected` in one batch, the final value
equals the old one, and the button stayed disabled forever.

Tests (`web/src/connect/SystemControls.test.tsx`): keyboard reach, one message on double-click and on repeated
clicks before the answer, a refusal (`error{ref}`, e.g. `session_busy`) re-enables, disabled reasons, axe, and a
fast-check property: any sequence of Reconnect / Change / Begin clicks and server answers sends at most one
`connect_system` per answer and nothing but `connect_system`. Live: `live.mjs` check "C-2: Reconnect sends exactly
one connect_system and lands on the menu" passes.

## C-3 "A Begin séance click once did not connect": recorded; two mechanisms found, both closed

You said no action was required. I did not chase it, but probing C-1 ran straight into it.

**Mechanism 1: a reconnect storm (my bug, reproduced every time).** From task 2.1 my reducer accepted a fresh
session only at seq 1 or from a `resync` snapshot. A running agent answers a fresh `hello` (`resume_from: null`) with
the *current* `session_state` at its current seq and `resync: false` (`hub.attach`). That is allowed by contracts
4.1/4.4, which only define resume. My client called it a gap, asked to resume, reconnected, got the same reply, and
looped `hello -> resume -> hello` **about every 30 ms**. A click in that window was refused by the transport and
dropped silently. It hit every page load against an agent that already had history. A fresh agent (seq 1) hid it,
which fits "once in about eight runs" if your harness usually restarted the agent.
- Fix: a fresh client takes the server's first `session_state` as its baseline at any seq. Defence in depth: the store
  never resumes from nothing and stops after 3 resumes without progress with a visible error, so there is no storm.
  "Begin séance" stays disabled until this connection's hello is answered. A send the transport refuses now says
  **"That was not sent… Nothing was resent. Try again."** instead of nothing.
- Tests: a fast-check property "attaching mid-session at any seq: no resume, then follows the stream exactly";
  mutation M7 (put the seq-1 rule back) is killed. The reducer's reordering property had to change: it shuffled
  the *first* event too, which encoded the wrong assumption. Its comment says why.

**Mechanism 2: a reload inside D's 60 s controller grace (by design in D).** D reserves the controller seat for 60 s
after a controller tab closes (REQ-003), so a new tab opened in that window is an **observer**. On the old code its
"Begin séance" button was enabled, and the click was refused with `observer_only`. Now the button is disabled with
"Only the controller can change or reconnect the system."

**Repro record** (`web/e2e/repro-c3.mjs`, live stack, agent with history, 2026-11-08):

| | Old code (before the fix) | New code |
|---|---|---|
| Websockets per fresh tab in 3 s | a new one about every 30 ms | **1** in each of 6 tabs |
| 15 fresh tabs, click at once | 0 connected, 11 clicks never sent | n/a (storm gone) |
| Tabs 2-6 (inside the 60 s grace) | enabled dead button | disabled, reason shown |
| Tab after the grace | | controller; Reconnect -> connected, composer usable |

The cheap test you asked for exists: `SystemControls.test.tsx` "Begin séance is disabled until the agent has
answered this connection's hello" and "every new socket needs its own answer".

## Task 7 against D's service: done (scripted provider, fake-insurance, nothing live)

`web/e2e/live.mjs` (committed, mine) on a fresh agent: **9/9**. It covers no REPLAY badge, connect, the lookup with the
planchette, the spirit-map marking the current screen, Reconnect, commit + Approve, commit + Deny (Esc), the audit drawer
and the protocol check. In the Approve check, Deny was focused, Approve was disabled at open, the script `click()` was
refused, exactly one `confirm_decision` was sent, and the screen showed `POLICY UPDATED`. The audit drawer showed
`oob:web-ui` and a rejected entry, with "verified by the server". The protocol check found only the six contract
client messages and 125 frames in. There were 0 page errors and 0 console errors. Axe with colour contrast was
clean in all 5 live states. Report: `docs/handoff/c/shots/live-report.json`; screenshots `live-0*.png`.

Your checks against my branch:
- `scripts/e2e-commit.mjs --decision approve`: **6/6**. `--decision deny`: **6/6**. Each ran on a fresh agent with
  its own fresh audit file.
- D's own live check of my client (`live-agent.test.ts` from `b9769c9`, run as a scratch copy, then deleted): 5/7,
  with `invalid: []` and `unknown: []`, so every live event passed my guards. The 2 failures are a commit in the same
  session after a read, which is B-1.
- `scripts/e2e-stack.mjs --workaround-goto`: 3/10. The rest are not UI defects, but the harness needs a look. I did
  not edit it.
  1. "planchette did not move (1 position)": it stops sampling when "A. ROSE" first appears anywhere, which is in
     the grid about 300 ms into the turn, before the first glide (at least 400 ms) can finish. The old planchette
     passed only because it was seconds behind. Suggest sampling until `turn_finished` plus 3 s.
  2. "second business tool": B-1 plus D-2.
  3. "approve" waits for the dialog to be `detached` within 10 s, but the modal keeps the outcome on screen until
     Dismiss, as your own status lists under "works". While the dialog is open the app is `inert`, so deny, audit
     drawer and spirit-map cascade from this one. Suggest clicking "Dismiss".
  4. "expected 1 confirmed commit, got 3": the agent's audit file persists across restarts and counted earlier
     runs. Suggest a fresh `AUDIT_LOG_PATH` per run (that is how I ran e2e-commit).

## New finding from task 7: ids reused within a session (7.2, contract + D)

Filed as `docs/handoff/c/request-integrator-unique-ids.md`. Summary: after each `connect_system` the agent restarts
`turn_id` `t_01`, `message_id` `m_02`, `tool_call_id` `c_01` inside the same `session_id`. Seen live at seqs 8/10,
40/46, 86/92. The UI then merges a new reply into an old message and treats a new `tool_call c_01` as a duplicate.
Not a safety problem (`action_id` is a uuid), but misleading. I did not patch around it, per rule 3 and task 7.2.

## Not C, for your information
- D's agent could be left in `connecting` with `app_id: null` and `_busy_connecting` stuck true after my storm
  (dozens of attaches and killed tabs mid-connect); later `connect_system` gets `session_busy`. A restart cleared it.
  I could not make a clean repro, so this is an observation for D, not a bug report.
