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
