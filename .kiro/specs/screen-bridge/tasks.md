# screen-bridge — Tasks

Tasks are ordered so the go/no-go de-risks as early as possible: parser first (no TK4- needed), then the integration test once legacy-environment exists.

## 1. Scaffold the package
- [x] 1.1 Create `bridge/` package with `pyproject.toml` (Python ≥3.12), pin deps: `pydantic`, dev: `pytest`, `hypothesis`.
- [x] 1.2 Add `.env.example` with `TN3270_HOST`, `TN3270_PORT`, `WAIT_TIMEOUT_MS` placeholders. Gitignore `.env`.
- [x] 1.3 Add `pytest` config + `@pytest.mark.integration` marker registration; integration tests skipped when `TN3270_HOST` unset.

## 2. Data models + parser (no emulator needed)
- [x] 2.1 Implement `Field` and `ScreenModel` pydantic models.
- [x] 2.2 Implement `attrs_from_byte(b) -> FieldAttrs` (decode protected/numeric/hidden/intensified/MDT from attribute byte).
- [x] 2.3 Implement `ScreenParser.parse(buffer) -> ScreenModel`: walk SBA/SF/SFE/IC orders into the 24×80 grid; map fields; null-out hidden values.
- [x] 2.4 Implement `screen_id`: SHA-256 over field positions/lengths/attrs + protected chars; exclude unprotected values; unit test determinism + value-invariance.

## 3. Property-based tests (Hypothesis) — de-risk before TK4-
- [x] 3.1 Write a `buffer_strategy` generating valid in-bounds, non-overlapping fields with random attributes + hidden fields.
- [x] 3.2 Assert invariants: parse never raises; fields in-bounds & non-overlapping; rows are 24×80; `screen_id` deterministic & value-invariant; hidden values never in output.
- [x] 3.3 Add explicit cases: empty buffer, single field, fully-protected screen, a buffer containing the literal text "ignore previous instructions" (assert it stays inert data).

## 4. Session controller (needs s3270)
- [x] 4.1 Implement `Session.connect/disconnect` wrapping the `s3270` subprocess.
- [x] 4.2 Implement `read_buffer()` (s3270 `ReadBuffer`), `send_string(s)`, `cursor_move(r,c)`.
- [x] 4.3 Implement `wait_unlock(timeout)` via s3270 status polling; raise `KeyboardTimeoutError` on expiry, never resend.
- [x] 4.4 Implement reconnect with bounded backoff → `SessionError` on failure. *(reconnect: pending integration verification)*

## 5. Bridge facade
- [x] 5.1 `read_screen()`: `Session.read_buffer()` → `parse_readbuffer_ascii()` → `ScreenParser.parse()`.
- [x] 5.2 `fill_field(ref, value)`: resolve ref, validate (protected/numeric/length), `cursor_move` + `send_string`; return updated `ScreenModel`.
- [x] 5.3 `press(key)`: send key, `wait_unlock`, return `ScreenModel`; flag `may_commit` for Enter/commit-capable PFs.
- [x] 5.4 Map `Key` enum to s3270 commands (ENTER, CLEAR, PA1–3, PF1–24).

## 6. Integration test — the go/no-go
- [x] 6.1 Integration test: connect to TK4-, read TSO logon screen, assert stable `screen_id` over two reads, assert ≥1 unprotected field. *(written; runs only with TN3270_HOST set)*
- [ ] 6.2 Run it once the legacy-environment container is up. **If green → proceed to mcp-server. If not → diagnose root cause before continuing.**

## 7. Docs
- [x] 7.1 `bridge/README.md` with quick-start, the screen_id contract, and the integration-test instructions.
