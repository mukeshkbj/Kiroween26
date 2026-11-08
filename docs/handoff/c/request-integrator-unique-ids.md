# Request to the integrator: ids must be unique per session (contracts 4.2/4.3), and D reuses them

From Agent C, 2026-11-08. Type: **contract clarification (additive wording)** plus a **fix for Agent D**. Found in task
7 (live mode against D's service). Under seance-ui task 7.2 and START-HERE rule 3, I am not patching the UI around it.

## What

Within one `session_id`, after each `connect_system` (including Reconnect, and the reconnect that routes around
B-1), the agent restarts its turn, message and tool-call counters. Live run on 2026-11-08 (scripted provider,
fake-insurance), ids as sent, `kind:id@seq`:

```
turn:t_01@8   tool_call:c_01@10  message:m_03@32     <- first system connection
turn:t_01@40  message:m_02@44    tool_call:c_01@46  message:m_03@78     <- after connect_system #2
turn:t_01@86  message:m_02@90    tool_call:c_01@92  message:m_03@124    <- after connect_system #3
```

Cause (read-only look at D's code): `hub._start_live` builds a new `AgentLoop` per connection, and
`loop.py` counters `_n_turn = _n_msg = _n_call = 0` start again, while the `Session` (`session_id`, `seq`) lives on.

## Why it matters

The contract implies uniqueness but does not say it. Section 4.3 says "each `tool_call` is followed by exactly one
`tool_result` with the same `tool_call_id`", and the UI keys turns, messages and tool calls by id per `session_id`.
With reuse, in the live run:
- the reply to a new turn was written **into an earlier message**, drawn above the user message that caused it;
- the new `tool_call c_01` (`update_policy`) was treated as a duplicate of the earlier `c_01` (`lookup_policy`), so
  its step card showed the **old call's result**;
- `turn_finished` for a reused `t_01` lands on an already-finished turn.

It is **not a safety problem**. Confirmations key on the gate's `action_id` (a uuid4), and the modal draws only gate
fields and the screen. But it shows the user wrong history.

## Proposed contract text (section 4.2, after the `seq` sentence)

> `turn_id`, `message_id` (in `assistant_delta`/`assistant_message`), `user_message_id` and `tool_call_id` are unique
> within a `session_id` for its whole life, across `connect_system` calls. A consumer may treat a repeated id as the
> same object. `action_id` stays a uuid4 from the gate.

Optional: add a check to `check_stream` (no id reused within a `session_id`), and a transcript with two
`connect_system` in one session so both sides test it.

## Proposed fix for D

Keep the counters on the `Session` (or prefix ids with a per-connection epoch, e.g. `t_02_01`). Either satisfies the
text above; it is D's choice.

## Affected agents
- **D**: the fix.
- **C**: nothing to change once ids are unique; the reducer already assumes it. If you would rather have the client
  tolerate reuse (scope ids by the `connect_system` that preceded them), say so and I will do it, but it makes the
  UI guess where the protocol could just say.
