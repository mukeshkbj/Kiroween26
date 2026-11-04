# Spec: mcp-server

## Overview
Expose the `bridge` library as an MCP server, so any MCP-speaking agent (Kiro, Claude, others) can operate the TK4- legacy app. The server wraps generic, bridge-level tools now; spirit-map will register business-level tools (e.g. `lookup_policy`) alongside them later without changing this server's shape.

This spec covers only the **generic** tool surface and the safety/audit plumbing. Business-level tools are out of scope (spirit-map spec).

## Requirements

### Server
- REQ-001: An MCP server (official Python SDK, `mcp` 2.x, `MCPServer`) exposing tools over stdio, so it can be launched as a subprocess by an MCP client (including Kiro).
- REQ-002: The server holds exactly one `Bridge` session per server process (one legacy terminal = one 3270 session; TK4- is single-user for the demo). A tool call before `connect` returns a clear "not connected" error rather than crashing.
- REQ-003: The server is registered in `.kiro/settings/mcp.json` so Kiro itself can drive the green screen during development (judging criterion: "strongest story: Kiro using our MCP server to drive the green screen").

### Generic tools
- REQ-004: `connect(host, port)` — opens the bridge session. Idempotent: calling it again while already connected reconnects rather than erroring.
- REQ-005: `read_screen()` — returns the current `ScreenModel` as JSON (rows, cursor, fields, screen_id). Hidden field values are never included (per mainframe-safety steering; enforced by the bridge, re-asserted here with a test).
- REQ-006: `list_fields()` — returns just the field list of the current screen (position, length, protected, numeric, hidden, intensified; no `rows`), for a cheaper call when an agent only needs field metadata.
- REQ-007: `fill_field(field_ref, value)` — validates and types into a field via the bridge; returns the resulting `ScreenModel`. Does not press a key.
- REQ-008: `press_key(key)` — sends an attention key (ENTER, CLEAR, PA1-3, PF1-24).
  - REQ-008a: If the key is **not** commit-capable for the current screen (see REQ-010), it executes immediately and returns the resulting `ScreenModel`.
  - REQ-008b: If the key **is** commit-capable, the tool does not execute it. It returns a **pending action** `{action_id, screen_id, key, field_snapshot}` and executes only when the same action is confirmed via `confirm_action`.
- REQ-009: `confirm_action(action_id)` — executes a previously returned pending action and returns the resulting `ScreenModel`. Rejects (clear error, no side effect) an unknown, already-executed, or expired `action_id`. A pending action expires after a configurable TTL (default 5 minutes) so stale confirmations can never fire against a screen that has since changed.
- REQ-010: Commit-capable keys default to the bridge's `COMMIT_CAPABLE` set (ENTER, PF1-12), per screen-bridge design.md. A per-`screen_id` override table (read-only keys for a given screen, e.g. PF3/PF7/PF8 in ISPF-style apps) may mark specific keys as non-committing; spirit-map is expected to populate this later. Ships empty; behaviour without it is the safe default.
- REQ-011: `get_audit_log(limit=None)` — returns audit entries (see Audit below) as JSON, newest last.

### Safety (per mainframe-safety steering)
- REQ-012: The server is read-only by default: only `confirm_action` can cause a commit-capable key to reach the legacy session. There is no tool or parameter that bypasses confirmation for a commit-capable key.
- REQ-012a: **Operator switch.** Commits are additionally disabled unless the operator sets `SEANCE_ALLOW_COMMIT=1` in the server's environment. While it is off, `confirm_action` refuses with a clear "server is read-only" error and the pending action stays unexecuted (and is audited as `blocked_read_only`). This is the default; the demo run enables it explicitly. The model cannot set it: it lives in process environment, not in any tool argument.
- REQ-012b: **A human, not the model, confirms.** An agent calling `confirm_action` on its own proves nothing. The server therefore requires a human decision at confirm time, by one of (in order of preference, configurable via `SEANCE_CONFIRM_MODE`): (1) `elicit` — the server asks the connected client's user through MCP elicitation (the SDK's `Resolve`/`Elicit` mechanism) with the key, screen and field snapshot; (2) `client-approval` — the client's own per-call tool approval is the gate, and `confirm_action` must never be placed in a client auto-approve list (the committed `.kiro/settings/mcp.json` must not auto-approve it); (3) `oob` — confirmation arrives on an out-of-band channel (a local-only HTTP endpoint or CLI the web UI uses), and `confirm_action` over MCP only reports status. If the configured mode cannot be honoured (e.g. `elicit` but the client lacks elicitation), the server fails closed: no commit.
- REQ-013: Every tool call that reaches the 3270 session (`connect`, `read_screen`, `fill_field`, `press_key`, `confirm_action`) is written to an append-only audit log: timestamp, screen_id (before the action), field (if any), value (if any, with hidden-field values redacted — never the literal value), key pressed (if any), action_id (if applicable), who confirmed (the confirmation mode used plus the client name reported by the MCP handshake, e.g. `elicit:kiro`, or "n/a" for non-commit actions), and the outcome (ok / error / blocked_read_only / expired / rejected). Entries are hash-chained (each carries the hash of the previous one) so tampering with the file is detectable.
- REQ-014: Hidden (non-display) field values never appear in a tool result, in the audit log, or in any error message. A test asserts this for `fill_field` on a hidden field and for `read_screen` immediately after.
- REQ-015: Screen text returned by any tool is documented (in the tool description and in design.md) as untrusted data for the calling agent — the server does not interpret it, only structures it. A test feeds a screen containing "ignore previous instructions" through `read_screen` and asserts the server performs no action beyond returning it as plain field data.
- REQ-016: `press_key`/`confirm_action` never resends a key whose acknowledgement was ambiguous (bridge `KeyboardTimeoutError`): the tool surfaces the error to the caller instead of retrying.

### Resources
- REQ-017: An MCP resource exposing the current screen as plain text (24x80, protected/unprotected fields visually distinguishable, e.g. unprotected shown in brackets) for a client that wants to display it without parsing JSON.
- REQ-018: An MCP resource exposing the audit log (same content as `get_audit_log`, as a resource for clients that prefer resource subscriptions over polling a tool).

## Testing
- REQ-019: Unit tests using a fake/stub `Bridge` (no s3270, no TK4-) covering: tool happy paths, the pending-action/confirm flow (including TTL expiry and double-confirm rejection), hidden-value redaction, and the prompt-injection screen-text case.
- REQ-020: One end-to-end test against the live TK4- container (marked `@pytest.mark.integration`, skipped if TK4- isn't running): connect, read the welcome/logon screen through the MCP tool surface (in-process `Client(server)`, no subprocess transport needed), press a non-commit key, and drive a commit-capable key through the full pending → confirm flow.

## Non-goals
- No business-level tools (spirit-map spec).
- No LLM calls (seance-agent spec).
- No websocket/HTTP transport (stdio only; a future spec may add Streamable HTTP if the web UI needs to talk to the MCP server directly instead of through the agent).
- No multi-session / multi-user support.
