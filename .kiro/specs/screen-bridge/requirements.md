# Spec: screen-bridge

## Overview
A Python library that opens a 3270 terminal session and turns each screen into a structured, deterministic model. This is the **core feasibility component** for Green Screen Séance: if the integration test passes against a real TK4- session, the whole project idea works. If it doesn't, the project must pivot.

The library has no agent, network-API, or UI dependencies. It is pure, isolated, and built to be property-tested hard.

## Requirements

### Session management
- REQ-001: `connect(host, port)` SHALL open a 3270 session via `s3270`/`py3270` and return a session handle.
- REQ-002: `disconnect()` SHALL close the session cleanly and free resources.
- REQ-003: The library SHALL detect a dropped session and attempt a bounded reconnect, surfacing a clear error if reconnect fails (no silent swallow).
- REQ-004: After a key press, the library SHALL wait until the keyboard unlocks (system available) before returning, with a configurable timeout. It SHALL NOT resend a key whose acknowledgement is ambiguous (per mainframe-safety steering).

### Screen model
- REQ-005: `read_screen()` SHALL return a `ScreenModel` (pydantic) containing:
  - `text`: the full 24×80 grid as a list of 24 strings of length 80.
  - `cursor`: `(row, col)` position.
  - `fields`: a list of fields, each with `row`, `col`, `length`, `protected`, `numeric`, `hidden` (non-display), `intensified`, and current `value`.
- REQ-006: `screen_id` SHALL be a stable hash derived from the **protected** text and field layout only, so the same screen is recognised regardless of the values typed into unprotected fields.
- REQ-007: Hidden (non-display) field values SHALL NOT be returned in `ScreenModel` and SHALL NOT be logged (per mainframe-safety steering). Their presence and position may be reported, but never their value.

### Field operations
- REQ-008: `fill_field(field_ref, value)` SHALL validate the field's length, numeric-only, and protected constraints before typing, raising a typed error on violation.
- REQ-009: `field_ref` SHALL accept either a field index or a `(row, col)` reference, resolved against the current `ScreenModel`.

### Keys
- REQ-010: `press(key)` SHALL support ENTER, CLEAR, PA1–PA3, and PF1–PF24, and SHALL return the resulting `ScreenModel`.
- REQ-011: Pressing Enter or a commit-capable PF key SHALL be treated as a potential data-change action by callers (the bridge itself does not enforce confirmation — that lives in the MCP server/agent per safety steering).

## Testing
- REQ-012: Property-based tests (Hypothesis) on the screen parser: for any generated 3270 buffer, parsing MUST NOT crash, fields MUST NOT overlap, field positions MUST be inside the 24×80 grid, `screen_id` MUST be deterministic and invariant under changes to unprotected values, and hidden values MUST NEVER appear in the parsed output.
- REQ-013: An integration test against the live TK4- container SHALL connect, read the TSO logon screen, and assert a stable `screen_id`. It SHALL be marked and skipped when the container is not running.

## Non-goals
- No agent/LLM logic here.
- No HTTP/websocket layer.
- No confirmation enforcement (delegated upstream).
- No real z/OS; TK4- only.
