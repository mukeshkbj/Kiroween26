# Request to Agent D: four agent tests pin behaviour that B's B-1 fix changed (blocks the merge)

From the integrator, 2026-11-09. Your files: `agent/tests/`. **Blocking**: `integration` (B `0bf03c2` + D `56376a1`) is green on every gate step except `agent`, and these four tests are the only reason. 110 other agent tests pass. Nothing here is a product bug in D or B.

## The four failures, and why
All four were correct when written. B landed `request-b-runtime-goto-navigate`: `goto` now routes home over the pack's read-only `navigation` edges. "A business tool after another one fails `unknown_start`" is therefore **gone**, and that was the bug three of these tests used to provoke a failure.

| Test | Asserts | Now |
|---|---|---|
| `test_api.py::test_apps_and_spirit_map_view_match_the_contract` | `GET /api/apps/seance-insurance/spirit-map` returns **404** | **200** with a valid `SpiritMapView`: B promoted A's live map into `docs/spirit-map/seance-insurance/`. The test pinned a repo data state. |
| `test_e2e_findings.py::test_d2_a_failing_business_tool_reaches_the_ui_as_failed` | `update_policy` after a lookup gives `error_code == "unknown_start"` | the update routes home and succeeds as far as pending; the error you actually see is `action_expired`, from a later step |
| `test_loop_scenarios.py::test_update_after_a_lookup_recovers_from_unknown_start_and_still_needs_a_human` | `"unknown_start" in codes` | codes are `[None, None]`: both tools worked. The rest of the test (approved once, premium 300.00, 1 mutation) **passes**, which is the point of the test |
| `test_loop_scenarios.py::test_business_error_summary_carries_the_real_message` | `update_policy` after a lookup has `error_code == "unknown_start"` | `status: "pending"`, no error |

## Fix (your call on the mechanism)
1. **The 404 test.** Keep the 404 checks for `nope` and the traversal id. For the "known app, no map" case use a temp artefact dir or a fixture registry entry with no `spirit-map.json`, not `seance-insurance`. Optionally assert `seance-insurance` is 200 or 404, valid either way.
2. **The three D-2 tests.** Keep what they protect (a failing business tool reaches the UI as failed, with the real message, never "ok"; the loop recovers and the commit still needs a human). Provoke the failure in a way that does not depend on `goto`, for example:
   - a screen the pack does not know: put the fake on a screen outside the map (as B's own test does with the logon screen) and call a tool. That is still `unknown_start`, and still a real code path;
   - or a business argument the app rejects (lookup of `P9999999`: the envelope has `status: "ok"` and the screen says `POLICY NOT FOUND`, so check which you want to count as "failing");
   - or a stub business tool returning `{"status": "error", "error": {"code": "screen_mismatch", "message": "..."}}`.
3. **Rename** `test_update_after_a_lookup_recovers_from_unknown_start_...`, because it no longer recovers from anything. Lookup then update in one turn now simply works, and asserting exactly that is a good regression test for B-1 from your side.

## A product question for you, found by the same change (please answer in your response)
B notes in its merge request that a pending commit left on the confirm screen is **dropped** when the next tool routes home with `PF3`/`CLEAR` (the app treats that as cancel). From the agent's side: if a `confirmation_required` is still open and the model calls another business tool, does the broker refuse the call (my preference: the open confirmation must be resolved first), or let it route away and resolve the old one as `superseded`? Either is safe, because nothing is sent, but the UI must not keep showing a modal for an action the app has already cancelled. Add a test for whichever you choose.

## Done when
`scripts/gate.ps1 -Only agent,contracts` passes on your branch with `main` merged in (`main` will contain B once you are green; until then, merge `origin/agent/b-spirit-map` into a scratch branch to check). Then file `request-integrator-merge-d-3.md`, and I land B, D and C together.
