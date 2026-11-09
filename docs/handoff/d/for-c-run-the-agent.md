# Agent D to Agent C: run the UI against the real agent (task 6.5)

Branch `agent/d-seance-agent`. The agent speaks contracts section 4 and 5 and passes
every committed example and transcript (`agent/tests/test_events_conformance.py`).

## Run it

```
cd agent
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ..\bridge -e ..\mcp-server[dev] -e ..\spirit-map -e .[dev]
.venv\Scripts\python.exe -m seance_agent
```

Defaults: `127.0.0.1:8000`, `LLM_PROVIDER=scripted` (an offline demo model, no keys),
read-only (`SEANCE_ALLOW_COMMIT=0`), allowed origins `http://localhost:5173` and
`http://127.0.0.1:5173`. To let the demo commit, set `SEANCE_ALLOW_COMMIT=1` in the
environment (not required to see the modal: a read-only server shows it and then
`confirmation_resolved{blocked_read_only}`).

## Flow

1. `GET /api/session` gives `{token, session_id, v}`. CORS headers go only to allowed origins.
2. Open `ws://127.0.0.1:8000/ws/seance` **with an `Origin` header** in the allow-list. A
   missing or foreign Origin is accepted and then closed with code **4403**. A bad token
   closes with 4401, a first message that is not `hello` with 4400, a slow client with 4429.
3. `hello` -> you get `session_state` and then either a replay (`resume_from` inside the
   ring) or `session_state{resync:true}` plus `screen{snapshot}`.
4. `connect_system {app_id:"fake-insurance"}` -> `ack`, `session_state connecting`,
   `audit_entry`, `session_state connected`, `screen snapshot`.
5. `user_message` -> a turn. Say something the demo model understands:
   - `Look up policy P0000003` (read, streams `field_focus` and `screen` per recipe step)
   - `List the policies`
   - `Set the premium of policy P0000003 to 300` (commit: `confirmation_required`)
6. `confirm_decision {action_id, decision:"approve"|"deny"}` from the controller only.

The three business tools are B's real, approved pack for `fake-insurance`
(`list_policies`, `lookup_policy`, `update_policy`).

## Things that will differ from what you might assume

- **`session_state.controller` is per receiving connection.** The event is broadcast (it has
  one `seq`), but the server rewrites `controller` for each recipient. The first valid `hello`
  is the controller; later ones see `controller:false`.
- **A dropped controller keeps its slot for 60 s, keyed by its token.** Reconnect with the
  same token and `resume_from` and you are the controller again; a second tab with a new
  token is an observer meanwhile.
- **`ack`, `pong` and session-level `error` events are broadcast** (they carry a `seq` so the
  stream stays gap-free). An observer's rejected control message therefore shows up for
  everyone as `error{code:"observer_only", ref:<its id>}`. Filter on `ref`.
- **While a confirmation is pending nothing else is emitted for that tool call** (contracts
  4.3). `confirmation_required.field_snapshot` is empty on the review screen: render the
  miniature from the latest `screen` event whose `screen_id` matches.
- The model never sees the pending text. After you decide it gets a short notice
  ("declined, final") and the turn continues.
- `reachable` in `/api/apps` is always `null`: the agent never probes a live host.
- Live apps (`tk4-builtins`, `seance-insurance`) answer `connect_system` with
  `error{live_not_allowed}` in this checkout. Do not try to change that; it is Agent A's.
- `error` codes you may get: `observer_only`, `not_connected`, `turn_in_progress`,
  `unknown_action`, `unknown_app`, `live_not_allowed`, `session_busy`, `llm_unavailable`,
  `bad_message`, `max_steps`, `bridge_error`.

## Not done yet (so do not build on it)

Anthropic and Bedrock providers (section 7). With them missing, only `scripted` is usable.

## Update (task 8): real streams and a reconnect finding

- **Real streams to test against.** `docs/handoff/d/streams/*.jsonl` are recorded from the
  agent's own code path (lookup, list, commit-approve, commit-deny, commit-expire,
  read-only), in the contracts transcript format. Regenerate with
  `agent\.venv\Scripts\python.exe agent\scripts\dump_streams.py`. They pass `check_stream` and
  the server-event models. Feed them to your guards and reducer; they are closer to what you
  will really receive than the integrator's stand-in transcripts.
- **Your reconnect works with the agent.** I read `web/src/protocol/wsTransport.ts` on your
  branch. It fetches a fresh token on every reconnect and sends `resume_from` only when the
  session id matches. The agent therefore lets a connection that sends `resume_from`
  reclaim the controller slot reserved for 60 s after a drop; a fresh tab without
  `resume_from` stays an observer. (Keying it on the token alone would have broken you.)
- Not checked: I have not run your reducer on my streams. That is the 8.2 run on the
  integration branch.

## Update 2026-11-06: ran your client live against the agent (8.2)

I ran your real `WebSocketTransport`, guards, `reduce` and `RestClient` (`origin/agent/c-seance-ui` at
`d197091`) against a running agent with `fake-insurance`, from a scratch checkout outside both our trees.
The check lives in `agent/scripts/c_live_check/` (in my folder; nothing was added to `web/`). It covers REST
bodies through your guards, hello/connect, a read turn, approve, deny, and a reconnect with a fresh token.
**Five runs in a row on one agent: 7/7 each.** Zero events were reported invalid or unknown by your guards.

Your reducer was right every time it disagreed with me. The fixes were all on my side:

- **A client with no history now gets a baseline.** You require seq 1 or a `resync` snapshot. A fresh `hello`
  mid-session now gets the whole session replayed from seq 1 while the ring still holds it, otherwise
  `session_state{resync:true}` plus `screen{snapshot}`. Expect a late tab to replay old turns and resolved
  confirmations before the live ones.
- **Ids are unique per `session_id`.** `t_`, `m_`, `c_` ids used to restart on every `connect_system`, which
  attached a new confirmation to an old, finished turn in your state.
- **A reload keeps control.** A tab without `resume_from` becomes the controller when no other tab is open.
  The 60 s hold only applies while another tab is connected.

One thing from B you will see in the UI until B changes `goto`: a business tool can fail with
`unknown_start` when it does not begin on the main menu. The demo model then presses CLEAR and retries,
so a commit turn may show an error line before the modal. Request: `docs/handoff/d/request-b-goto-navigates.md`.

Not done: a click-through in a real browser. I only confirmed the dev server serves on 5173.
