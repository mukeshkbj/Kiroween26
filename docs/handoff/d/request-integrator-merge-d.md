# Request: Agent D to Integrator, merge `agent/d-seance-agent` into `integration` and `main`

**From:** Agent D. **To:** Integrator. **Branch:** `agent/d-seance-agent` (pushed, tip `1065d73` or later).
Filed here because D may write only `docs/handoff/d/` (`scripts/check-ownership.ps1`); contracts section 12 names this form.

## Ask

Merge D into `integration`, then `main`. The seance-agent milestone is met except task 7.3, which needs a real API key (see Open items).

## Why it is safe to merge

- `scripts/check-ownership.ps1 -Branch agent/d-seance-agent`: all 54 touched files are in `agent/`, `.kiro/specs/seance-agent/`, `docs/handoff/d/`.
- `scripts/gate.ps1 -Only agent`: pass on the fixed Hypothesis seed and a random one. 81 passed, 1 skipped (live, A only), 1 deselected (`llm`, needs a key).
- `mypy` (pinned 2.4.1, now in the dev extras): `Success: no issues found in 19 source files`.
- `main` was merged into the branch on 2026-11-06; no conflicts. Nothing outside D's paths changed.
- No new contract text is required to merge. Contract examples and the seven transcripts round-trip through the agent's event models (`tests/test_events_conformance.py`).

## What it delivers (spec tasks 1 to 6, 7.1, 7.2, 7.4, 8.1, 8.3, 9)

- `python -m seance_agent`: FastAPI REST (contracts 5) and `WS /ws/seance` (contracts 4), origin check (4403), token (4401), controller and observers, 1000-event resume ring.
- In-process MCP server over an in-memory client, B's approved `fake-insurance` pack plus the four generic tools. `confirm_action`, `connect`, `get_audit_log` are never offered.
- The thesis, tested with an obedient model (`GullibleLlm`): no commit key reaches the fake app without a controller approval. A `RuleBasedStateMachine` with its own ledger and recorded mutation checks (`agent/tests/mutation_checks.md`).
- Anthropic and Bedrock providers (recorded-payload tests; keys never reach a log, event or error), plus an offline `scripted` demo model.

## Setup the integrator needs

A separate `agent/.venv` (Python 3.12) with `pip install -e ..\bridge -e ..\mcp-server[dev] -e ..\spirit-map -e .[dev]`. New pins are all in `agent/pyproject.toml`: `fastapi==0.162.0`, `uvicorn==0.54.0`, `websockets==17.4`, `httpx==0.28.1`, `mypy==2.4.1`; extras `anthropic==2.5.0`, `boto3==1.43.124`. `gate.ps1` already picks up `agent/.venv`.

## Open items (not blockers)

| Item | State |
|---|---|
| 7.3 real-model injection test | Written (`agent/tests/test_llm_real.py`, marked `llm`). Skips without credentials. The user will supply a key later; then run `python -m pytest -m llm tests/test_llm_real.py` and keep the transcript it writes to `docs/handoff/d/llm-injection-transcript.jsonl`. |
| 8.2 conformance with C's web app | In progress with C. Real agent streams are in `docs/handoff/d/streams/`. |
| 8.3 live end-to-end | Request to A: `docs/handoff/d/request-a-live-e2e.md`. A runs it after the merge. |

## Contract notes to consider (additive, `v: 1`; I did not change any contract text)

1. `session_state.controller` is per recipient: one broadcast event, rewritten for each connection on fan-out and replay (keeps `seq` gap-free).
2. A dropped controller keeps its slot 60 s; it is reclaimed by the same token or by any connection sending `resume_from` (C's client fetches a new token on each reconnect).
3. `ack`, `pong` and session-level `error` are broadcast with a `seq`; an observer's rejected message appears to everyone as `error{code:"observer_only", ref}`.
4. Websocket close codes beyond 4403: 4400 (first message not `hello`), 4401 (bad token), 4429 (client too slow or oversized frame). Worth listing in section 4.1.
5. B's business tools return their envelope as JSON text with no structured content. The agent parses it; an `output_schema` with structured content would be cleaner for generated tools.
