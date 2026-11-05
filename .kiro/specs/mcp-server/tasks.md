# mcp-server — Tasks

Ordered so the safety layer is built and proven against a fake bridge first (no emulator), then wired to the real bridge, then driven live from Kiro.

Prerequisite: screen-bridge go/no-go is green (done: 3 consecutive passes against `gss-legacy`). Known gaps carried over from screen-bridge: reconnect (its task 4.4) and field wraparound (8.9). Neither blocks this spec; `session_lost` is surfaced instead of reconnecting.

## 1. Scaffold
- [x] 1.1 Create `mcp-server/` package (`pyproject.toml`, Python >=3.12, `src/seance_mcp/`). Pin with `==`: `mcp` (2.x), `pydantic`, `anyio` as needed; dev: `pytest`, `hypothesis`, `pytest-asyncio` or `anyio`'s pytest plugin. Install `../bridge` editable.
- [x] 1.2 `.env.example` with `TN3270_HOST`, `TN3270_PORT`, `WAIT_TIMEOUT_MS`, `SEANCE_ALLOW_COMMIT=0`, `SEANCE_CONFIRM_MODE=elicit`, `PENDING_TTL_S=300`, `AUDIT_LOG_PATH`, `KEY_POLICY_PATH`. Gitignore the audit log directory.
- [x] 1.3 `config.py`: env -> `Settings` (pydantic), safe defaults, validation (e.g. unknown confirm mode is an error, not a silent fallback).
- [x] 1.4 Register the `integration` marker; integration tests skip unless `TN3270_HOST` is set (same convention as bridge).

## 2. Audit log (REQ-013, REQ-014)
- [x] 2.1 `audit.py`: `AuditEntry`, `AuditLog.append/read/verify`; append-only file, `fsync`, hash chain.
- [x] 2.2 Redaction inside `append`: hidden fields -> `<hidden>`, credential-like names -> `<redacted>`.
- [x] 2.3 Property tests: chain verifies for any operation sequence; any single-byte tamper is detected; redaction idempotent and never leaks the original value.

## 3. Safety gate (REQ-008b, REQ-009, REQ-010, REQ-012, REQ-012a, REQ-012b, REQ-016)
- [x] 3.1 `safety.py`: `PendingAction`, `may_commit(key, screen_id)` with the key-policy override table (ships empty), injected clock.
- [x] 3.2 `SafetyGate`: propose / confirm / expire / stale-screen check / single pending action / `needs_resync` after ambiguous ack / `SEANCE_ALLOW_COMMIT` block.
- [x] 3.3-spike Elicitation spike done; results and decisions in design.md ("Elicitation spike results").
- [x] 3.3 `Confirmer` interface (as built: `decide_elicit/decide_client_approval/decide_oob`; MCP resolver wiring is in 4.2) with `elicit`, `client-approval`, `oob` implementations. **Spike first:** write a 20-line server and check whether Kiro's MCP client answers elicitation (`Resolve`/`Elicit`, and `ctx.elicit()` for legacy). Record the result in design.md and pick the default accordingly. Fail closed when the mode cannot be honoured.
- [x] 3.4 Stateful Hypothesis test (`RuleBasedStateMachine`) on the gate: no commit-capable key ever reaches the fake bridge without exactly one matching, unexpired, same-screen confirmation.
- [x] 3.5 Unit tests: double confirm, expiry, stale screen, read-only block, elicit declined, ambiguous ack sends the key exactly once.

## 4. Port + tools (REQ-001, REQ-002, REQ-004 to REQ-011)
- [x] 4.1 `port.py`: `BridgePort` Protocol; real adapter running `Bridge` calls in a worker thread under one `anyio.Lock`; `FakeBridge` for tests.
- [x] 4.2 `tools.py` + `server.py`: `connect`, `read_screen`, `list_fields`, `fill_field`, `press_key`, `confirm_action`, `get_audit_log` as typed tools with the untrusted-screen-text line in each description. Stable error codes.
- [x] 4.3 Screen text sanitising (strip control characters) applied at the single point where `ScreenModel` becomes tool output.
- [x] 4.4 Unit tests with `FakeBridge`: every tool's happy path, `not_connected`, field validation errors surfaced as `field_invalid`.
- [x] 4.5 Tests: hidden-value redaction end to end (result, audit file, errors); prompt-injection screen ("ignore previous instructions") returns as data only with zero extra bridge calls.
- [x] 4.6 Property test: bridge `arbitrary_buffer` sentinel never appears in any tool output or audit file.

## 5. Resources + entrypoint (REQ-001, REQ-017, REQ-018)
- [x] 5.1 `render.py` and the `screen://current` resource; `audit://log` resource.
- [x] 5.2 `__main__.py`: `python -m seance_mcp` serves stdio; logs go to stderr only (stdout is the protocol channel).
- [x] 5.3 `mcp-server/README.md`: run, env vars, the confirmation trust model in plain words, the Windows/POSIX launch commands.

## 6. Live + Kiro (REQ-003, REQ-020)
- [x] 6.1 Integration test against `gss-legacy` via in-process `Client(server)`: connect, read the welcome screen, list fields, CLEAR executes, `fill_field` + ENTER returns a pending action and leaves the screen unchanged, confirm with a test confirmer executes it, disconnect. Never completes a TSO logon. Must pass 3 runs in a row.
- [x] 6.2 Add the server to `.kiro/settings/mcp.json`; `autoApprove` only `read_screen`, `list_fields`, `get_audit_log`. Verify Kiro lists the tools. **Config written to `mcp-server/kiro-mcp.json`** (a permission rule blocks the agent from writing `.kiro/settings/`; the user copies it in). The launch line was verified from the repo root against live TK4-: 7 tools listed, welcome screen read, ENTER pending, confirm refused `read_only`, all audited. The user copied it to `.kiro/settings/mcp.json` (commit `865fd11`) and Kiro loaded all 7 tools. Still unverified: whether Kiro wants raw or `mcp_<server>_<tool>` names in `autoApprove`.
- [x] 6.3 **Closed 2026-11-05 by spirit-map's approved policy** (B's request `docs/handoff/b/request-integrator-register-fake-insurance`). The `gss-fake-insurance` server (`SEANCE_APP=fake-insurance`, `GENERATED_TOOLS_PATH`/`KEY_POLICY_PATH` pointing at `docs/spirit-map/fake-insurance/`) registers the three generated tools and loads `key-policy.json`, which is byte-identical to the golden policy, so enquiry, the list and navigation run without confirmation and only ENTER on the confirm screen needs it. Verified in-process (`test_toolpack.py::test_configured_pack_with_spirit_package_registers_through_the_real_register`) and by a stdio launch. No hand-written policy was needed in the end; the generated one dropped straight in. Prior finding (`449b425`): `RealBridgePort` built `Bridge` without `volatile_regions`; `Settings.volatile_regions` now flows to the bridge (`tests/test_volatile.py`). App selection added here: `SEANCE_APP` + `factory._port_for` + `fake.FAKE_APPS`.
- [x] 6.4 Drive the green screen from Kiro (read the welcome screen, find the logon field) and capture a screenshot plus one surprise in `docs/kiro-journal.md` for the write-up. Done (`a132562`): welcome screen read, logon field found (index 143, row 22, col 11). **Elicitation in the Kiro IDE is still untested**: the server was read-only, so the gate refused before any elicitation. No screenshot yet; retake with `SEANCE_ALLOW_COMMIT=1`.

## 7. Hooks and docs
- [x] 7.1 Safety-review hook (playbook hooks table): on save of a file in `mcp-server/`, check the change against mainframe-safety steering and flag any commit path without confirmation.
- [ ] 7.2 Tick tasks as they complete; keep design.md in step with what was actually built (as done for screen-bridge in review-01).
