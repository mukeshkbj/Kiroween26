# Request to Agent D: findings from the full-stack browser run (2026-11-06)

From the integrator. Your code (`agent/`). D is merged on `main` (`7e24c1a`); fix on your branch and file a merge request as before. Evidence and the run are in `status-2026-11-06.md` ("Full-stack run").

The core held. The obedient-model thesis, oob approval, deny, chain and controller rules all worked in a real browser. The items below are wrong behaviour around that core, most important first.

## 1. The demo model proposes the wrong change for natural phrasing (fix before any demo)
`llm/scripted.py`: `_PREMIUM_RE = r"premium\D{0,15}(\d{1,7})"` matches the policy number's digits.
```
"Set the premium of policy P0000003 to 300"  -> premium = "0000003"   (should be 300)
"Set the status of policy P0000002 to L"     -> no status            (should be L)
"Set premium to 300 for P0000003"           -> premium = "300"       (ok)
```
The modal would still have shown the true values (it draws the screen), so nothing unsafe gets through. But on stage the agent would propose a premium of 3 for the most natural sentence. Fix: strip the policy number before matching, take the number after "to"/"=" when present, and accept `status ... to X`. Test: a table of phrasings including the two above.

## 2. A failed business tool is summarised as "ok"
`tools.py` `_summary()` returns `f"{name} ok"` for every non-pending status. A business envelope with `status: "error"` therefore produces `tool_result{status: "error", summary: "lookup_policy ok"}`. The UI shows it and the demo model repeats it ("That did not work: lookup_policy ok"). Fix: for `status == "error"` use the envelope's `error.message` (or `"<name> failed: <code>"`). Test: an error envelope never produces a summary containing " ok".

## 3. Event-order deviations from contracts 4.3
Seen on one lookup (seq numbers from a probe):
- `field_focus` step 0 (`mode: read`) has `screen_id: ""`. The contract says it is the screen the operation acts on; use the last known screen id (the service's `_last_screen_id`, or the previous `screen` event's id).
- `screen{phase:"after"}` (seq 13) is emitted **before** the call's `screen{phase:"before"}` (seq 14). The contract has one `before` at the start of the call's first operation, then `after`s. The first op is a `read`, which has no `screen_before`. Emit the `before` from the read's result (or from the cached last screen) before its `after`.
`check_stream` does not check these yet. I will add both checks to `seance_mcp.contracts.check` once you have fixed them, so neither side can drift.

## 4. `agent/apps.json` still says "Seance Insurance (KICKS)"
Contracts section 8 changed on 2026-11-06. The entry should be named `Seance Insurance (COBOL on TK4-)`, with description "Real COBOL on TK4-; the five screens are served by a labelled Python TN3270 stand-in." and `port_env: STANDIN_PORT`. The connect screen shows the KICKS name today, which is not true and a judge would see it.

## 5. Model-facing instruction text appears in the user's chat (minor)
After Deny, the step card shows: "The person declined this change. Nothing was changed. This is final: do not retry or propose it again." The last sentence is an instruction to the model. Show the user only the first two sentences, and keep the full text in the tool result sent to the model.

## Not a D bug (for your information)
- Every business tool after the first fails `unknown_start`. That is spirit-map's `goto` (request to B: `request-b-runtime-goto-navigate.md`). Your loop handles it correctly: an error result and no retry.
- After `ambiguous_ack`, `session_lost` and other errors, recovery depends on the UI's reconnect control (request to C).

Done when: 1 and 2 have tests, 3 passes the stricter `check_stream`, 4 matches contracts section 8, and `scripts/gate.ps1 -Only agent,contracts` is green. Then file a merge request.
