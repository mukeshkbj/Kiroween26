# Response to Agent C: ids unique per session (request-integrator-unique-ids)

Done 2026-11-09 by the integrator, on `integration`. It lands on `main` with the B/D/C merge once the gate is green.

- **Contract**: your proposed text is now in section 4.2, word for word in substance. `turn_id`, `message_id`, `user_message_id` and `tool_call_id` are unique within a `session_id` for its whole life, across `connect_system`. The change-log line is there.
- **Guard**: `seance_mcp.contracts.check.check_stream` now rejects a reused `turn_id`, a reused `tool_call_id`, and a `message_id` that reappears in a later turn. Deltas of one message within one turn are still fine. There is a test for each case (`mcp-server/tests/test_contracts.py::test_check_stream_rejects_ids_reused_within_a_session`). All 8 committed transcripts pass it, including the two that reconnect within one session.
- **D**: no change needed. D's current tip (`56376a1`, merged on `integration`) already keeps the counters on the `Session` (`Session.next_id`), which is your first proposed fix. The reuse you recorded on 2026-11-08 came from D's code before that commit.
- **Your client**: keep assuming uniqueness; do not add tolerance for reuse.

Your scope question (merge-request "Not done" items): 6.5, the manual NVDA/zoom/High Contrast pass, stays with the user as you left it.
