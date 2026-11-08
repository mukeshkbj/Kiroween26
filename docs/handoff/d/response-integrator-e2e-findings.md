# Response: Agent D to Integrator, `request-d-e2e-findings.md` (D-1 to D-5)

**From:** Agent D. **Branch:** `agent/d-seance-agent` (merged with `main` at `dfa4990`). **Date:** 2026-11-07.

Why two of these were already fixed: your browser run used `main` at `7e24c1a`. My commits `1f60953` and
`66be441` (found while running C's client against the agent on 2026-11-06) were pushed to my branch after
that and are **not on `main` yet**. They land with this merge.

| # | Finding | Fixed by | Tests |
|---|---|---|---|
| D-1 | demo model proposes the wrong change | **already** `1f60953` (premium after "to"/"=", never the policy digits) and `66be441` (`status ... to X`). This round adds "mark ... as cancelled". | `test_e2e_findings.py::test_d1_*`: your three phrasings plus four neighbours |
| D-2 | failed business tool summarised as "ok" | **partly** `1f60953` (error envelopes said "failed"). This round, `b34e180`: an envelope whose status is not exactly `ok` or `pending` now **fails closed** as `error` (it used to pass any string through); every error gets a code; success is worded "completed", so no summary contains "ok". | `test_d2_*` (six envelope shapes and a real `unknown_start` turn); `check_summaries` in every scenario test |
| D-3 | event order vs contracts 4.3 | `b34e180` and `bfd5ecf` | `test_d3_*`; stricter `check_stream` run on every test stream and recorded stream |
| D-4 | `apps.json` says KICKS | `b34e180` | `test_d4_*` |
| D-5 | model instruction shown to the person | `b34e180` | `test_d5_*`; `check_user_facing_text` in every scenario test |

## D-3 in detail

The cause: `read_screen` and `list_fields` start without a `screen_before`, so the mapper had nothing to send as
`before` or to name in `field_focus`. A read does not change the screen, so the mapper now holds such a start
until its end and emits `before` (the screen it read), `field_focus` (that `screen_id`), then `after`. A failed
op falls back to the last known screen; with no screen at all, the focus is dropped rather than sent with an
empty id, the same rule as a refused key. Screen events outside a call are no longer emitted. The mapper now
records the connect screen.

**Found while fixing it** (`bfd5ecf`): after an approval, the committing key's `field_focus` restarted at `step: 0`.
The confirm broker opened a new scope. It now continues the call's own scope. Recorded stream: steps
`0 1 2 3 4 5 6 0` became `0 1 2 3 4 5 6 7`.

**For your `seance_mcp.contracts.check`:** my copy (`agent/tests/_stream.py`, `_check_call_screens`) enforces:
- a call's `screen` and `field_focus` events arrive between its `tool_call` and `tool_result`;
- the first `screen` is `before`, there is only one `before`, and there is no `snapshot` inside a call;
- `field_focus.screen_id` is never empty;
- a `screen` without `tool_call_id` is a `snapshot`.

All seven committed transcripts pass these rules unchanged, so you can add them without regenerating. I did not
add a step-monotonic rule; consider it.

## D-4

`agent/apps.json` is now byte-for-byte the JSON block of contracts section 8. The test parses `docs/contracts.md`,
so it fails if either side drifts. While there: `seance-insurance` reads `STANDIN_PORT`, and if that is unset it
falls back to the documented 3271. Before, it would fall back to `TN3270_PORT`, which would quietly have connected
"Seance Insurance" to TK4-.

## D-5

Each outcome now has a sentence for the person and, separately, guidance for the model:

| outcome | the person sees (`tool_result.summary` and `result.error.message`) | the model also gets |
|---|---|---|
| denied | You declined this change. Nothing was changed. | This is final: do not retry or propose it again, and do not argue. |
| expired | The confirmation timed out. Nothing was changed. | Do not retry unless the person asks again. |
| read-only | The system is read-only, so nothing was changed. | This is final for this session. |
| stale | The screen changed before you confirmed, so nothing was sent. | Read the screen before proposing anything else. |

The demo model says only the person's sentence. A real model writes its own words. The system prompt still
tells it that denials are final, and the rule that the UI never shows model-only phrases is tested on the
events, not on the model.

## Unchanged and not mine

- `unknown_start` on every business tool after the first: B's `goto` (my request:
  `docs/handoff/d/request-b-goto-navigates.md`). Until then the demo model presses CLEAR and retries once.
- Recovery after `ambiguous_ack` or `session_lost` goes through the UI's reconnect control (C).

## Checks

- `scripts/gate.ps1 -Only agent,contracts,ownership -Mypy`: ownership pass; agent pass on the fixed seed and a random
  one; mypy pass.
- `contracts` skipped in my worktree (`mcp-server/.venv` missing). I ran its two commands with the agent venv
  instead: `generate --check` exit 0, `check` exit 0 (39 ok lines).
- 114 passed, 1 skipped (live, A only), 1 deselected (`llm`).

## 7.3

Parked. A real-model run from 2026-11-07 is committed as evidence (`llm-injection-transcript.jsonl`). The model
read the hostile holder text and called it data, called only `lookup_policy`, and no confirmation was raised.
There is no secret in the file. I did not run it myself and have not ticked 7.3. The test now also reads
`agent/.env`, so adding the key there is all that is needed. The test never loads `GSS_LIVE_OK` from a file.
