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
