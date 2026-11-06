# seance-agent — Tasks

Owner: **Agent D**. Folder: `agent/`, `.kiro/specs/seance-agent/`, `docs/handoff/d/`. Branch: `agent/d-seance-agent`. Read `docs/contracts.md` first. Never touch `web/`, `spirit-map/`, `legacy/`, `bridge/`, `mcp-server/`, and never touch the live container.

Ordered so the safety properties are proven with scripted models before any real LLM is attached.

## 0. Prerequisites (integrator, parallel-plan P0; blocked until done)
- [x] 0.1 `seance_mcp.fake` (`FakePort`, `FakeApp`) importable.
- [x] 0.2 `build_service(...)`, `SafetyGate.deny_oob`, `SeanceService.observe`, `AuditLog.subscribe`.
- [x] 0.3 Contract examples and transcripts in `docs/contracts/examples/`.

## 1. Scaffold (by 9 Nov)
- [x] 1.1 `agent/` package: `pyproject.toml` (Python >=3.12; pin `fastapi`, `uvicorn`, `pydantic`, `anthropic`, `websockets`/test deps, `pytest`, `hypothesis`, `httpx`; `boto3` as extra). Install `../bridge`, `../mcp-server` editable.
- [x] 1.2 `.env.example` with every variable in design.md (placeholders only); `.env` stays gitignored.
- [x] 1.3 `config.py` with validation (unknown provider is an error, not a fallback; missing key -> `llm.available=false`, no crash).
- [x] 1.4 Markers `integration`, `llm` skipped by default.

## 2. Events and session (REQ-001, REQ-003, REQ-004, REQ-026, REQ-030)
- [x] 2.1 `events.py`: pydantic models for every server event and client message from contracts section 4; JSON round trip; conformance test against `docs/contracts/examples/events/*.json`.
- [x] 2.2 `session.py`: seq, ring buffer, resume, observers vs controller, bounded queue, optional event log.
- [x] 2.3 Property test: stream shape invariants (seq gap-free, replay suffix equality) over generated event sequences.

## 3. Tool broker and mapper (REQ-005 to REQ-007, REQ-013, REQ-014)
- [x] 3.1 `tools.py`: in-memory MCP client over the in-process server; allowlist; JSON Schema validation; error mapping to stable codes.
- [x] 3.2 `mapper.py`: observer -> `screen` before/after, `field_focus` (read/fill/key), `audit_entry`; redaction.
- [x] 3.3 Tests: hidden sentinel never in any event (REQ-028); `confirm_action`/`connect`/`get_audit_log` never offered; invalid args never sent.

## 4. Confirmation broker (REQ-015 to REQ-019, REQ-027)
- [x] 4.1 `confirm.py`: pending registry, approve/deny/expire/supersede, exactly-one `confirmation_resolved`, resume future.
- [x] 4.2 Controller-only check, observer rejection, unknown/expired/duplicate ids.
- [x] 4.3 `RuleBasedStateMachine` (REQ-027) with own ledger, success-path weighting; mutation checks run and recorded in `agent/tests/mutation_checks.md` (controller/observer gate removal -> illegal commit; gate-enforced expiry and single-use verified load-bearing via `tests/_mutation_checks.py`).
- [x] 4.4 Read-only (`SEANCE_ALLOW_COMMIT=0`) path: `blocked_read_only` shown, not silent.

## 5. Agent loop with scripted LLM (REQ-008, REQ-010, REQ-012, REQ-019, REQ-025) (by 12 Nov)
- [x] 5.1 `llm/base.py`, `llm/scripted.py` (`ScriptedLlm`, `GullibleLlm`).
- [x] 5.2 `prompts.py` (system prompt, untrusted wrapper) and `loop.py` (budgets, cancel, suspend on pending, no dangerous retries).
- [x] 5.3 Unit scenarios from REQ-025 over `FakeApp`; stub two-tool tool pack until spirit-map merges.
- [x] 5.4 Injection tests (REQ-029a) with `GullibleLlm`; record in the journal that the defence holds with an obedient model.

## 6. API (REQ-001, REQ-002, REQ-022 to REQ-024) (by 16 Nov)
- [ ] 6.1 `api.py`: routes, CORS, origin check, `/api/session` token, websocket handshake (`hello`), observer/controller.
- [ ] 6.2 `apps.py` + `apps.json`: fake and live registry; `GSS_LIVE_OK` guard; spirit-map view loader (`SpiritMapView`) with fixtures from the contract until B delivers.
- [ ] 6.3 `__main__.py`: `python -m seance_agent`; logs to stderr; startup line prints provider/model only.
- [ ] 6.4 WS tests: origin refused, token required, second connection observer, resume after drop, session lost.
- [ ] 6.5 Milestone: Agent C can run the UI against `python -m seance_agent` with the scripted provider and `fake-insurance` (handoff note in `docs/handoff/d/`).

## 7. Real providers (REQ-009, REQ-011, REQ-029b) (by 20 Nov)
- [ ] 7.1 `anthropic_provider.py` with recorded-payload tests; no key in logs (test greps log output).
- [ ] 7.2 `bedrock_provider.py` (Converse tool use); same tests.
- [ ] 7.3 `llm`-marked injection test with a real model; save one transcript to the journal.
- [ ] 7.4 `llm_unavailable` path tested.

## 8. Integration (by 24 Nov)
- [ ] 8.1 Merge spirit-map tool pack runtime; swap the stub; rerun everything.
- [ ] 8.2 Conformance run against the real UI build on the integration branch (with Agent C).
- [ ] 8.3 Handoff request to Agent A for the live end-to-end (REQ-032): scripted provider, `gss-legacy`, three runs in a row.

## 9. Docs and journal
- [ ] 9.1 `agent/README.md`: run, env, trust model in plain words (the model cannot confirm), origin/token.
- [ ] 9.2 Journal entries to `docs/handoff/d/journal.md`: one surprise per section 4, 5 and 7.
