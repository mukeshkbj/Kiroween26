# Request to Agent C: findings from the full-stack browser run (2026-11-06)

From the integrator. Your code (`web/`). C is merged on `main` (`eda6cf0`). D is on `main` too, so **task 7 (live mode) is unblocked**: `git merge main` and go. Evidence: `status-2026-11-06.md` ("Full-stack run"), screenshots in `docs/handoff/integrator/e2e-2026-11-06/`.

In live mode against the real agent, these work: the connect screen, the 24x80 render, streaming chat with step cards, the business/generic badge, "may change data" tagging, the confirmation modal (draws the confirm screen with OLD/NEW, Deny focused, Approve delayed, untrusted click refused, unverified agent text, Dismiss after the outcome), approve and deny outcomes, the audit drawer with an honest chain badge, and the spirit-map view. There were 0 page errors and 0 console errors across all runs. Well done.

## 1. The planchette stops at the first target (live mode)
In one lookup the agent sent these `field_focus` events (probe, in order): `read` (no position), `fill OPTION ===> (7,15)` on the menu, `key Enter`, `fill POLNO ===> (3,13)` on the enquiry screen, `key Enter`. After the turn the planchette rested at **(7,15) labelled "filling OPTION"** over the enquiry screen's `UPDATED:` line. It never moved to POLNO, and the label referred to a field on a screen no longer shown.
Likely causes to check: the scheduler waits for an animation `finish` that never arrives when the next event replaces the target, or a `screen` event between focuses resets the queue. Your property test (REQ-027) proves the scheduler in isolation; this is about the component and live timing.
Asks:
- (a) Follow the events to the last one (REQ-027 "ending with the last event").
- (b) When the turn ends, or when the current `screen_id` differs from the target's `field_focus.screen_id`, move the planchette to rest (or hide it). Never leave a label naming a field that is not on screen.
Test: a component test that feeds this exact sequence with real timers (or fake timers advancing past each animation) and asserts the final target is POLNO, plus that a later `screen` with another `screen_id` clears the label.

## 2. No way to change or reconnect the system once connected
After `connect_system` the connect screen is gone and there is no control to return to it or to reconnect. Your `ambiguous_ack` and `session_lost` banners offer "Reconnect"; the normal connected state offers nothing. A demo that needs a fresh session (or a judge who wants the TK4- screens after the insurance app) has to reload the page. Please add a "Change system" (and "Reconnect") control in the header or OIA, keyboard-reachable. It sends exactly one `connect_system`, like your banner button.

## 3. Unconfirmed: a "Begin séance" click once did not connect
In one of about eight runs the first click right after page load left the page on "Choose a system", disconnected, with no "not sent" notice. I could not reproduce it in the next seven runs. Each needed one click. It may have been my harness reloading while the agent was restarting. No action required. If you have a cheap test that `connect_system` is never sent before `hello` is acknowledged (or is queued until then), that would close it.

## Not C bugs (for your information)
- "Seance Insurance (KICKS)" on the third card comes from D's `apps.json` (request to D).
- Every business tool after the first fails with "That did not work: lookup_policy ok". The failure is spirit-map's `goto` (request to B), and the "ok" summary is D's (request to D).

Done when: 1 and 2 have tests, `scripts/gate.ps1 -Only web,contracts` is green, and task 7 has been run against the real agent (scripted provider). Then file a merge request. `scripts/e2e-commit.mjs` and `scripts/e2e-stack.mjs` on `main` are the integrator's browser checks; you may run them, but do not edit them (request changes instead).
