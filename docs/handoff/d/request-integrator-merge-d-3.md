# Request: Agent D to Integrator, merge `agent/d-seance-agent` (tests after B-1)

**From:** Agent D. **Answers:** `docs/handoff/integrator/request-d-tests-after-b1.md` (on `integration`).
**Branch:** `agent/d-seance-agent`, tip `0322c0b` or later, with `main` merged in (`3dbff50`).

## Ask

Land B, D and C together, as planned.

## The four tests

Each still protects what it did; none depends on `goto` or on repo data any more.

| Test | Was | Now |
|---|---|---|
| `test_api.py::test_apps_and_spirit_map_view_match_the_contract` | `seance-insurance` map must be 404 | keeps the traversal and `nope` 404s; `seance-insurance` may be 200 (then it must be a valid `SpiritMapView`) or 404. The "known app, no map" case moved to a new test, `test_a_registered_app_without_a_map_is_404`, with its own registry entry and an empty artefact root. |
| `test_e2e_findings.py::test_d2_a_failing_business_tool_reaches_the_ui_as_failed` | provoked `unknown_start` by calling a tool after a lookup | parks the fake on a screen outside the map (`_harness.park_off_map`), which is `unknown_start` on any runtime (contracts 6.2). Also asserts nothing was sent and no pending was created. |
| `test_loop_scenarios.py::test_update_after_a_lookup_recovers_from_unknown_start_...` | asserted `unknown_start` in the codes | **renamed** `test_lookup_then_update_in_one_session_still_needs_a_human`. It asserts only that the update reaches the modal and commits once on approval, which holds before and after B-1. The recovery path it used to cover is kept as a new test, `test_off_map_failure_is_recovered_with_a_read_only_key` (off-map, the demo model presses CLEAR and retries once, and the commit still stops at the modal). |
| `test_loop_scenarios.py::test_business_error_summary_carries_the_real_message` | lookup then update, and "expected to start" in the summary | off-map, and the summary must equal `update_policy failed: <the envelope's own message>`. On `integration` the first rewrite failed because it still pinned B's old wording; B-1 reworded the message. It now compares with the message B actually sends. |

One small production fix came with this: `create_app(hub=...)` built its own `AppRegistry` for the REST routes instead of using the hub's, so REST and the websocket could disagree about the app list. It now uses the hub's registry.

## The product question: an open confirmation and another business tool

**The open confirmation is resolved first; the other call does not run.** That matches your preference, and it was already true by construction:

1. When a tool returns pending, the loop suspends the turn in the confirm broker. Tool uses run one at a time, so a second one, even from the same model step, starts only after the person has approved or denied, or the confirmation has expired. A new `user_message` during that time gets `turn_in_progress`. So nothing can route away from the review screen while the modal is open, and the modal can never describe an action the app has already cancelled.
2. New, defence in depth: if any future path ever reaches a tool call while a confirmation is open, it is refused with `session_busy` ("A change is waiting for your decision; decide on it first."). It sends nothing and leaves the open confirmation untouched and still decidable.

I did not choose "route away and resolve the old one as `superseded`". It is safe, but the person would see their modal vanish because of something the model did, and the app's cancel would arrive from navigation instead of from the person.

Tests, in `agent/tests/test_open_confirmation.py`:
- `test_a_second_tool_waits_until_the_confirmation_is_resolved[approve|deny]`: the model asks for `update_policy` and `lookup_policy` in one step. While the modal is open, no key reaches the app, only the update has been called, the gate still holds the same action and the app is still on `confirm`. The lookup's `tool_call` comes after `confirmation_resolved`. An approve commits exactly once; a deny commits nothing.
- `test_a_tool_call_while_a_confirmation_is_open_is_refused`: the `session_busy` guard. Nothing is pressed, and the confirmation can still be approved afterwards.

## Checks

- **My branch (with `main`):** 119 passed, 1 skipped (live, A only), 1 deselected (`llm`, 7.3 parked). mypy clean.
- **My branch with `origin/integration` merged** (a scratch branch in my worktree; it has B-1 and the `seance-insurance` map): `scripts/gate.ps1 -Only agent,contracts -Mypy` passed: agent on the fixed seed and a random one, and mypy.
- **`contracts` step:** the gate skips it in my worktree because there is no `mcp-server/.venv`. I ran its two commands with the agent's venv, on my branch: `generate --check` exit 0, `check` exit 0 (39 ok). I did not repeat them on the scratch branch. I changed no contract files, so please let your gate run that step on `integration`.
- **Ownership:** every file touched is in `agent/`, `.kiro/specs/seance-agent/`, `docs/handoff/d/`.

No new dependencies. No contract change. `session_busy` is already an agent error code in contracts section 3.5.
