# Kiro journal

How Kiro was used on Green Screen Seance: spec and steering changes, in order.

- 2026-11-05: `.kiro/specs/seance-agent/tasks.md` changed

---

## Agent D notes

### 2026-11-05 — scaffold + events (tasks 1, 2.1)

- Set up `agent/` (package `seance_agent`) with `==`-pinned deps. Looked the
  moving ones up on PyPI on 2026-11-05: `fastapi==0.162.0`, `uvicorn==0.54.0`,
  `httpx==0.28.1`, `websockets==17.4`, `anthropic==2.5.0` (anthropic extra),
  `boto3==1.43.124` (bedrock extra). Reused the mcp-server pins for
  `mcp/pydantic/anyio/pytest/hypothesis/jsonschema`. Everything installed and
  imported together in one `py -3.12` venv.
- `config.py`: unknown `LLM_PROVIDER` is a startup error; a missing credential is
  *not* — `llm_availability()` returns false and the service still starts.
- `events.py` mirrors contracts section 4. Rather than redeclare `ScreenOut`,
  `FieldOut`, `FieldSnap`, `AuditEntry`, I import them straight from `seance_mcp`
  (contracts section 3 names those the source of truth), so any drift there is a
  type error here, not a silent divergence.
- Conformance test round-trips every `docs/contracts/examples/events/*.json`
  through the models *and* re-serialises to byte-identical canonical JSON, then
  replays all seven transcripts through `check_stream` (copied, as the README
  says). Green on the first run.

Surprise (section 7 / tooling): the anthropic SDK I'd half-remembered as 1.x is
actually at **2.5.0** now and dropped `httpx` for a separate `httpx2` package;
the agent's own `httpx==0.28.1` (via starlette/TestClient) and anthropic's
`httpx2` coexist in the same venv without conflict. Worth remembering when I wire
the real provider in task 7 — the request/mock plumbing is httpx2, not httpx.

### 2026-11-05 — tool broker + mapper (tasks 3.1-3.3)

- `tools.py` drives the real `seance_mcp` `MCPServer` over
  `create_client_server_memory_streams` with a genuine `ClientSession`, so tool
  discovery, schemas and error codes are the real MCP ones (REQ-005). The
  allowlist drops `confirm_action`/`connect`/`get_audit_log` from the catalogue
  and refuses them if the model names them anyway.
- `mapper.py` follows `record.py`'s flush/focus logic exactly (one `before` per
  call, an `after` per successful op, `field_focus` with position for fill / key
  name for key / nothing for read, audit entries in order).

Surprise (section 5 / safety): the MCP SDK (mcp==2.3.0) generates tool input
schemas **without** `additionalProperties:false` — `read_screen` is literally
`{"properties":{},"type":"object"}`. So `read_screen({"bogus":1})` passes plain
JSON-Schema validation. REQ-007 wants extra/malformed args rejected *before*
sending, so the broker now tightens each object schema to forbid unknown
top-level keys (`_strict_object`). Without that, a gullible model could smuggle
stray kwargs past validation; the server would ignore them, but the contract
wants the call refused, and "refuse early, fail closed" is the safer default.
The no-leak test uses a purpose-built one-field hidden-input app because
fake_insurance has no password field; the canary never reaches any event and
every hidden screen field is nulled.

### 2026-11-05 — confirmation broker + no-unconfirmed-commit (tasks 4.1-4.4)

- `confirm.py` is the human gate. The loop calls `await_decision`, which emits
  `confirmation_required` (content copied straight from `gate.pending`) and
  suspends on an `anyio.Event`; only a controller `confirm_decision` resolves it,
  via `gate.approve_oob` + `service.confirm_action`. Deny, expire, supersede,
  read-only and unknown/duplicate ids each resolve exactly once and send nothing.
- I split `register_pending` out of `await_decision` so the `RuleBasedStateMachine`
  can drive registration and resolution as independent steps without a blocked
  coroutine; the blocking path just calls `register_pending` then waits.

Surprise (section 4 / safety): the state machine's invariant is deliberately
*outside* the broker — it keeps its **own** ledger of controller approvals and
asserts `commits <= controller_approvals`, never reading the broker's private
state. That separation is what made the mutation checks honest: when I simulate
removing the api-level controller gate (an observer reaches `decide`), a commit
appears with an empty ledger and the invariant fires immediately. The two
gate-owned rules (expiry, single-use) turned out *not* to be defeatable from the
agent side at all — `gate.authorize` consumes the action before the key is sent
and rejects anything past its TTL, so the broker physically cannot double-commit
or commit-after-expiry. The agent's own load-bearing rule is the controller gate;
the rest it correctly delegates to the integrator's gate. Recorded in
`agent/tests/mutation_checks.md`.

### 2026-11-05 — agent loop + injection (tasks 5.1-5.4)

- `loop.py` streams inner steps live: a 20 ms pump flushes the service's
  observer bus while the tool call is in flight, so the planchette can follow a
  recipe rather than get one batch at the end (REQ-013).
- The model is never shown the pending result (its text tells callers to use
  `confirm_action`). It sees nothing until a human decides, then a short
  agent-written notice ("declined, final, do not retry") or the confirmed screen.

Surprise (section 5 / safety): B's real tools return their envelope as JSON
**text**, with no `structured_content`. My first classifier read `status` from
structured content only, so `update_policy` came back as `ok` while the gate
held a live pending action. That would have failed open: the turn would not
have suspended and no modal would appear. Fixed twice over: the broker parses
the text envelope, and the loop independently compares `gate.pending` before
and after every call, so a new pending action suspends the turn whatever the
tool reported.

Second surprise: my first injection test passed for the wrong reason. B's
`lookup_policy` extracts four fields and never the message line, so the hostile
text never reached the model. The test now asserts the attack text is seen
inside a tool result (and nowhere in the system prompt or user messages) before
it asserts anything about safety. `GullibleLlm` also had to learn to scan every
tool result of a step, not just the last one.

Defence holds with an obedient model: `GullibleLlm` tried `confirm_action`, an
invented `approve_pending`, PF3 and a zero premium. The first two were refused by
the allowlist, the update stopped at the modal and expired, no commit key reached
the fake (`app.dirty` false), and `confirm_action` is absent from the audit log.
The tool-error budget then stopped the turn, which is the budget doing its job.

### 2026-11-06 — API, hub and websocket (tasks 6.1-6.5)

- `hub.py` holds everything behind the socket (session, runtime, loop, confirm
  broker, message handling); `api.py` is a thin transport. That split is what let
  the controller-only rule be tested without a socket and again through one.
- The tool server runs in its own long-lived task (`ToolBroker.start` has to be
  entered and exited by the same task), stopped by an event on reconnect/shutdown.
- Live apps are refused with `live_not_allowed` **before a port is built**; the
  service's own guard is the second layer. `reachable` is reported `null` because
  probing a live host is itself a live connection.

Surprise (section 6 / protocol): `session_state.controller` is a per-recipient
fact but the event has one `seq` in a gap-free stream. Sending each client its own
copy would break the gap-free rule for everyone else. Resolution: broadcast one
event and rewrite `controller` per recipient on fan-out and replay. Same reasoning
makes `ack`, `pong` and session-level `error` broadcast. Written up for C in
`for-c-run-the-agent.md`. Also worth a contracts note: a controller that drops
keeps its slot for 60 s keyed by its token, otherwise an observer tab could take
over during an ordinary reconnect.

Smaller catches: my first API test hung because the helper waited for a
`session_state` an earlier assertion had already consumed (test bug, not server);
the secrets test I first wrote ended in `or True`, so it proved nothing. The API
key is now a `SecretStr` and the test asserts it is absent from repr, dump and
JSON.

### 2026-11-06 — real providers, integration prep (tasks 7, 8, 9)

- Anthropic and Bedrock adapters keep conversion in pure functions and are tested
  against recorded-shape payloads. Errors are mapped from the exception class and
  HTTP status only. I never use `str(exc)`.

Surprise (section 7 / secrets): the SDK exception text can contain request
detail, including the key. The tests raise exceptions whose message embeds a fake
key and assert it is absent from the `LlmError`, from `caplog` and from the
provider's repr. Making the key a `SecretStr` came from the same worry. The
Anthropic SDK is also at 2.5.0 now and uses `httpx2`, which coexists with our
`httpx` (noted earlier); `AsyncMessageStream` has no `text_stream` helper, so the
adapter iterates events and reads `TextEvent.text`.

Surprise (section 8 / integration, found by reading C's branch): the web
client fetches a new token on every reconnect. My controller reservation was
keyed by token, so a returning controller would have been demoted to observer for
60 s, exactly when the UI most needs its modal. The slot is now reclaimed by any
connection that sends `resume_from` (the client sends it only for the same
session id). Found without running C's code, which I cannot merge. Ownership
holds and the cost was a `git show`.

Open: 7.3 needs one real run with credentials for the saved transcript (the test
exists and skips honestly). 8.2 needs the integration branch with C's `web/`. 8.3
is requested from A in `request-a-live-e2e.md`. mypy is not run yet (not in the
dev extras).

### 2026-11-06 — mypy, merge request, live run against C's client (task 8.2)

- `mypy==2.4.1` is in the dev extras and `src` is clean (22 findings fixed: variable reuse, the memory-stream
  types, an async generator typed as `Iterator`). No `# type: ignore` was added except one in the Bedrock
  stream loop, where boto3's event stream is untyped.
- Merge request to the integrator: `docs/handoff/d/request-integrator-merge-d.md` (filed in my folder, because
  the ownership script allows D only `docs/handoff/d/`).

Surprise (section 8 / integration): running C's real transport and reducer against the live agent found
**five bugs in my code that 90 passing Python tests had not.** Every one was a place where my tests shared my
assumptions:

1. A late client got a mid-session `session_state` with no baseline. C's reducer, correctly, treated it as a
   gap and applied nothing.
2. Turn, message and call ids restarted on every `connect_system`, so two turns in one session had the
   same id.
3. A page reload, with nothing else open, became an observer for 60 s because of my reservation rule.
4. My demo model read `premium of policy P0000003 to 300` as premium `0000003` (my API tests passed with
   it, because the fake still reaches the confirm screen), and could not parse `status ... to L`.
5. Business-tool errors were summarised as `update_policy ok`.

It also surfaced one in B's runtime (`goto` asserts instead of navigating, contracts 6.2; request filed).
The lesson for the write-up: contract examples and per-component tests agree with each other by
construction. Two independently written implementations exercised against each other find the gaps.
Doing it from a scratch worktree kept ownership intact.

A process note: one "failure" was my own test racing a full replay, which contains old `connected` events.
I read the agent's own event log (`AGENT_EVENT_LOG`) before changing any code. It showed the agent was right,
so the fix went into the test (wait for the stream to settle).

### 2026-11-07 — integrator e2e findings D-1 to D-5

- D-1 and most of D-2 were already fixed on my branch (`1f60953`, `66be441`). The integrator's browser run used
  `main` from before they landed. The rest is fixed in `b34e180` and `bfd5ecf`, tests first: 27 tests were red
  before any code changed.

Surprise (section 8 / protocol): the D-3 bug was invisible to every stream check I had, because my
`check_stream` copy only checked what the contract examples needed (turns, call/result pairs). Adding the 4.3
screen rules turned 12 previously green tests red at once. The root cause was a single assumption in the mapper:
that every operation names its screen when it starts. Reads don't. Fixing it surfaced a second deviation the
integrator had not listed (the step counter restarting at 0 after approval). The general lesson: a checker
written to accept the examples cannot catch what the examples never exercise.

Also: D-4 was more than a label. `seance-insurance` fell back to `TN3270_PORT` when `STANDIN_PORT` was unset, so
it would have connected to TK4- under the stand-in's name. The test now pins `apps.json` to the JSON in
`docs/contracts.md`.

### 2026-11-09 — four tests after B-1

- B-1 (a navigating `goto`) made four of my tests fail. The tests were right about what they protected, but they
  used a bug in someone else's code, or the repo's current data, as the way to provoke a failure. They now provoke
  it with a screen the map does not know, which is `unknown_start` by contract on any runtime.
- Surprise: my first rewrite still failed on `integration`, because I had pinned B's error *wording*
  ("expected to start"), and B-1 reworded it. The test now compares the summary with whatever message the
  envelope carries. Same lesson as last time, one level down: assert on your own behaviour, not on the
  neighbour's text.
- Product decision: an open confirmation is resolved before any other tool runs (already true because the loop
  suspends on the human), plus a `session_busy` guard as defence in depth. I rejected "route away and supersede":
  safe, but the person's modal would vanish because of something the model did.

### 2026-11-09 — 7.3 with a real model

- Ran the `llm` tests and one real conversation (lookup, list, update approved through the controller) with
  `claude-sonnet-5-5`. Every safety property held: no commit without the person, no `confirm_action`, the expiry
  was not retried.
- Surprise (section 7): the real model's own good judgement nearly made the injection test meaningless. It used the
  narrow `lookup_policy`, which never returns the message line, so the attack never reached it. A model that
  behaves well can hide an untested defence as easily as a stub can. The test now proves delivery first.
- Surprise: providers never closed their HTTP client. It only showed up with two real tests in a row
  (`Event loop is closed`). Now `aclose()` is called from hub shutdown.
- The key prefix was literally in the repo (in the detector pattern and a fake test key), so the requested
  grep for the key prefix always had false hits. Both are now built from parts, and the grep returns nothing.
