# Contracts â€” Green Screen Seance

**Status:** v1, approved. **Applies to:** every agent (A legacy, B spirit-map, C web, D agent) and the integrator.
**Precedence:** this document beats any spec on interface questions (formats, ownership, who may touch what). Safety rules in `.kiro/steering/mainframe-safety.md` beat this document. If you think a contract is wrong, do not work around it: file a request (section 12).

Words: **MUST** and **MUST NOT** are rules a reviewer will check. **Integrator** is the main session / the user who owns shared code and merges.

---

## 1. Ownership

One folder, one owner. Nobody edits another owner's folder, not even for a typo. Ask (section 12).

| Path | Owner | Notes |
|---|---|---|
| `legacy/` | **Agent A** | docker-compose, TK4-, KICKS, demo app source, `legacy/captures/` |
| `spirit-map/` | **Agent B** | package `seance_spirit` |
| `web/` | **Agent C** | React app |
| `agent/` | **Agent D** | package `seance_agent`, `agent/apps.json` |
| `.kiro/specs/legacy-environment/` | A | |
| `.kiro/specs/spirit-map/` | B | |
| `.kiro/specs/seance-ui/` | C | |
| `.kiro/specs/seance-agent/` | D | |
| `docs/spirit-map/**` | B | generated artefacts per app (section 7) |
| `docs/handoff/a/`, `b/`, `c/`, `d/` | the same letter | requests, notes, per-agent journal, experiments |
| `docs/handoff/integrator/` | Integrator | weekly status, answers to contract requests |
| `bridge/`, `mcp-server/` | **Integrator** | finished libraries; agents depend on them, change them only via request |
| `.kiro/steering/`, `.kiro/hooks/`, `.kiro/settings/` | Integrator | |
| `docs/contracts.md`, `docs/parallel-plan.md`, `docs/contracts/**` | Integrator | |
| `docs/kiro-journal.md`, `docs/audit/` | Integrator | audit is runtime data, gitignored |
| repo root files (`README.md`, `.gitignore`, `.gitattributes`, `LICENSE`), `scripts/` | Integrator | |
| `.kiro/specs/screen-bridge/`, `.kiro/specs/mcp-server/` | Integrator | finished specs; task 6.3 of mcp-server stays open until B delivers a policy |

Note: `.kiro/steering/structure.md` does not yet list `spirit-map/`. The integrator updates it in P0.

Rules:
1. **Write only inside your paths.** A diff that touches another path is rejected at merge, whatever the reason.
2. **Dependencies point one way** (structure.md): `bridge` <- `mcp-server` <- `spirit-map`, `agent`; `agent` reads `spirit-map` artefacts and uses its runtime only through mcp-server's registration hook; `web` depends on nothing in Python and talks only to `agent` over HTTP/WS.
3. **Journals:** do not edit `docs/kiro-journal.md`. Write dated notes in `docs/handoff/<letter>/journal.md`; the integrator merges them. (`.gitattributes` marks `docs/kiro-journal.md` `merge=union`, P0.)
4. **Tests live with their code.** Each owner's tests must pass without any other agent's unmerged work (use the doubles in section 2).
5. **No secrets** in any file, log, event, fixture or screenshot (tech.md). `.env` is gitignored; `.env.example` is committed.
6. **Pin dependencies** exactly (`==` or exact npm versions). A new dependency is named in the PR description with the requirement it serves.

---

## 2. The live container and FakeBridge

### 2.1 Only Agent A touches `gss-legacy`
`gss-legacy` (TK4- on Hercules) is a single-user system with one 3270 session and a console. Two agents using it corrupt each other's work and the demo state.

- **Only Agent A** may start, stop, reset, `docker exec` into, connect to port 3270 or 8038 of, or run any marked live test against `gss-legacy`.
- Agents B, C, D and the integrator MUST NOT connect to it, including "just a read". This includes Kiro's own `green-screen-seance` MCP server pointed at `127.0.0.1:3270`: it is a live connection. Do not call its `connect` from B, C or D sessions.
- Live tests are marked `integration`, skip when the container is not up, and additionally skip unless `GSS_LIVE_OK=1`. Only A (and the integrator for the final runs) sets `GSS_LIVE_OK=1`, or creates the gitignored marker file `.gss-live-ok` in the repo root of its own worktree (the marker is per worktree, so it cannot leak to other agents). `mcp-server` (live guard, P0.6) and `agent/` refuse to connect to a live host without one of the two (`live_not_allowed`). A shared `.env` MUST NOT set it.
- **Live work for others is done by A on request** (section 12): "run spirit-map exploration against tk4-builtins", "run the agent end-to-end three times". A reports results and commits artefacts to *its own* paths or hands files over via `docs/handoff/a/`.
- Final live acceptance (demo path three times in a row) is run by A on the integration branch.

### 2.2 FakeBridge: what everyone else uses
`FakeBridge` means `seance_mcp.fake` (P0 promotes it out of `mcp-server/tests`):

- `FakePort`: implements `BridgePort` (`connect`, `disconnect`, `read_screen`, `fill_field`, `press`) over a `FakeApp`.
- `FakeApp`: a declarative app: screens built with the real `ScreenParser` (so `screen_id`s, hidden fields and field layouts are genuine) and **value-aware transitions** `(screen, key, field-values) -> screen`. It records every key it receives and a `dirty` flag that is set when a transition marked `mutating` runs. Tests assert on both.
- `fake_insurance()`: the 5-screen app of section 10, with 8 seed policies. The same screens A builds in KICKS.
- `FakeApp.from_capture(path)`: replays a **capture**, below.

### 2.3 Captures (real screens without touching the container)
A produces `legacy/captures/<app_id>/<name>.json` by reading the live app through the normal tools:

```json
{
  "schema": "gss.capture/1",
  "app_id": "tk4-builtins",
  "captured_at": "2026-11-12T09:30:00Z",
  "screens": [ { "name": "welcome", "screen": { /* ScreenOut, section 3.1 */ } } ],
  "transitions": [
    { "from": "welcome", "key": "CLEAR", "fills": [], "to": "welcome" },
    { "from": "welcome", "key": "ENTER", "fills": [{"field": "logon", "value": "XYZZY"}], "to": "logon_rejected" }
  ]
}
```
Captures contain only what the tools return (sanitised, hidden values null). A capture with any hidden-field value, password or real user id other than documented test ids is a bug. B and D load captures through `FakeApp.from_capture`.

---

## 3. Shared data shapes

Source of truth is the Python models in `mcp-server` (`seance_mcp.screens`, `seance_mcp.audit`, `seance_mcp.safety`). TypeScript mirrors them in `web/src/protocol/types.ts`. Conformance tests (section 11) keep both honest. All rows and positions are **0-origin**. Envelope `ts` is ISO-8601 UTC with milliseconds and `Z` (`2026-11-24T10:15:30.123Z`). `AuditEntry.ts` is written by the audit log as Python `isoformat()` (`2026-11-24T10:15:30.123000+00:00`); parse it as ISO-8601 and do not reformat it (the hash chain covers its exact text).

### 3.1 `ScreenOut`
```json
{
  "trust": "untrusted-screen-data",
  "screen_id": "9f2c...64 hex",
  "cursor": [5, 14],
  "rows": ["... 24 strings, each 80 chars, control chars replaced by spaces ..."],
  "fields": [ FieldOut ],
  "volatile": [[0, 64, 16], [1, 64, 16]]
}
`volatile` is the list of positions masked out of `screen_id` (clocks, paint-time dates, the demo app's output fields), as `(row, col, length)` runs, 0-origin; each run stays on one row. It is advisory, never a field value. Spirit-map treats these spans as part of node identity (section 10.4); a consumer that does not care ignores it.
```
### 3.2 `FieldOut`
```json
{ "index": 3, "row": 5, "col": 14, "length": 8, "protected": false, "numeric": false,
  "hidden": false, "intensified": false, "label": "POLNO", "value": "P0000001" }
```
`value` is **always `null` when `hidden` is true**. `col` is the first data position (the attribute byte is at `col - 1`).

### 3.3 `FieldSnap` and `PendingOut`
```json
{ "index": 3, "row": 5, "col": 14, "label": "PREMIUM", "value": "250.00" }
```
`value` may be `"<hidden>"` or `"<redacted>"`.
```json
{ "action_id": "uuid4", "screen_id": "...", "key": "Enter", "expires_in_s": 295.0,
  "field_snapshot": [ FieldSnap ] }
```
`key` uses the bridge's key names (`Enter`, `Clear`, `PA1`, `PF3`, ...).

### 3.4 `AuditEntry`
```json
{ "seq": 7, "ts": "2026-11-24T10:15:30.123Z", "tool": "confirm_action", "outcome": "ok",
  "screen_id": "...", "field": null, "value": null, "key": "Enter", "action_id": "uuid4",
  "confirmed_by": "oob:web-ui:s_01", "detail": null, "prev_hash": "...", "hash": "..." }
```
Outcomes in use: `ok`, `error`, `proposed`, `superseded`, `rejected`, `expired`, `stale_screen`, `blocked_read_only`, `needs_resync`, `ambiguous_ack`, `session_lost`, `field_invalid`, `not_connected`, `confirmation_unavailable`, `awaiting_oob`, `unknown_action`.

### 3.5 Error codes (stable)
From mcp-server: `not_connected`, `field_invalid`, `keyboard_timeout`, `session_lost`, `unknown_action`, `action_expired`, `stale_screen`, `read_only`, `confirmation_unavailable`, `awaiting_oob`, `bad_key`, `bridge_error`, `needs_resync`.
From the tool-pack runtime: `screen_mismatch`, `unknown_start`, `unexpected_pending`, `step_budget`, `invalid_arguments`.
From the agent: `denied_by_user` (tool result when the human pressed Deny), `llm_unavailable`, `llm_error`, `max_steps`, `bad_message`, `observer_only`, `unknown_app`, `live_not_allowed`, `session_busy`, `turn_in_progress`.

---

## 4. Agent-to-UI websocket protocol (v1)

Endpoint: `ws://127.0.0.1:8000/ws/seance`. Text frames, one JSON object each, UTF-8. Server and client both ignore unknown fields and unknown `type`s (log once). Breaking changes bump `v`.

### 4.1 Handshake and access
1. Browser `GET /api/session` (CORS-allowed origins only) -> `{"token": "...", "session_id": "s_01", "v": 1}`.
2. Open the websocket. The server checks the `Origin` header against `AGENT_ALLOWED_ORIGINS` and closes with code 4403 otherwise.
3. Client's first message MUST be `hello`. The server replies with `session_state` and replays or snapshots (4.4).
4. First valid `hello` becomes the **controller**. Later connections are **observers**: they receive all events; their control messages get `error{code:"observer_only"}`.

### 4.2 Server -> client envelope
```json
{ "v": 1, "type": "tool_call", "seq": 42, "ts": "2026-11-24T10:15:30.123Z",
  "session_id": "s_01", "turn_id": "t_07", "data": { } }
```
`seq` is gap-free and strictly increasing per `session_id`, starting at 1. `turn_id` is `null` for session-level events. The client MUST ignore `seq <= last_seq`.

### 4.3 Server -> client event types

| `type` | `data` |
|---|---|
| `session_state` | `{ "state": "disconnected"\|"connecting"\|"connected"\|"session_lost"\|"error", "app_id": string\|null, "read_only": bool, "confirm_mode": "oob", "llm": {"provider": string, "model": string, "available": bool}, "tools": {"business": int, "generic": int}, "resync": bool, "controller": bool }` |
| `ack` | `{ "ref": "<client message id>" }` |
| `turn_started` | `{ "user_message_id": string }` |
| `thinking` | `{ "summary": string }` short caption, not raw reasoning |
| `assistant_delta` | `{ "message_id": string, "text": string }` |
| `assistant_message` | `{ "message_id": string, "text": string }` final text for that message |
| `tool_call` | `{ "tool_call_id": string, "tool": string, "kind": "business"\|"generic", "arguments": object, "may_commit": bool\|null }` arguments redacted like the audit log |
| `screen` | `{ "phase": "before"\|"after"\|"snapshot", "tool_call_id": string\|null, "screen": ScreenOut }` |
| `field_focus` | `{ "tool_call_id": string, "step": int, "mode": "read"\|"fill"\|"key", "screen_id": string, "field_index": int\|null, "row": int\|null, "col": int\|null, "length": int\|null, "label": string\|null, "key": string\|null }` position only, never a value |
| `tool_result` | `{ "tool_call_id": string, "status": "ok"\|"pending"\|"error", "error_code": string\|null, "summary": string, "result": object\|null, "truncated": bool }` `result` capped at 8 KB; no hidden values |
| `confirmation_required` | `{ "action_id": string, "tool_call_id": string, "screen_id": string, "key": string, "field_snapshot": [FieldSnap], "expires_in_s": number, "read_only": bool, "agent_summary": string\|null }` **all fields except `agent_summary` come from the gate** |
| `confirmation_resolved` | `{ "action_id": string, "outcome": "approved"\|"denied"\|"expired"\|"superseded"\|"blocked_read_only"\|"stale"\|"error", "confirmed_by": string\|null, "error_code": string\|null }` exactly one per `confirmation_required` |
| `audit_entry` | `{ "entry": AuditEntry }` |
| `turn_finished` | `{ "reason": "completed"\|"cancelled"\|"error"\|"max_steps", "usage": {"input_tokens": int, "output_tokens": int}\|null }` exactly one per turn |
| `error` | `{ "code": string, "message": string, "recoverable": bool, "ref": string\|null }` |
| `pong` | `{}` |

Screen and focus rules (recorded from the real service, see the transcripts):
- Per tool call: one `screen{phase:before}` at the start of its first operation, then a `screen{phase:after}` after **every** operation that succeeded (so the UI can animate typing and follow the recipe). The last `after` is the call's final screen. `snapshot` is only for connect and resync.
- `field_focus` is emitted when an operation **starts**: `fill` has the field's position; `key` has the key name and no position; `read` has no position (sweep the screen). An operation that was refused before it chose anything (for example a confirm that fails read-only) emits **no** `field_focus`. `field_focus.screen_id` is the screen the operation acts on.
- `audit_entry` events interleave in the order the entries were appended.
- A tool call that needs confirmation emits `confirmation_required` and then **nothing else for that call** until the human decides; `tool_result` is emitted once, after `confirmation_resolved`, with status `ok` (approved), or `error` with `denied_by_user`, `action_expired` or `read_only`.
- **Confirmation modal content:** the gate's `field_snapshot` lists only *unprotected* fields, which is empty on review screens such as `confirm` where old and new values are protected text. The UI MUST therefore render the miniature from the latest `screen` event whose `screen_id` equals `confirmation_required.screen_id`. If there is none, it says so and keeps Approve disabled.

Ordering guarantees per turn: `turn_started`, then any interleaving of the others, then `turn_finished`. Each `tool_call` is followed by exactly one `tool_result` with the same `tool_call_id`. For a business tool, `screen`/`field_focus` events for its inner steps arrive between `tool_call` and `tool_result` with the same `tool_call_id`; `step` counts from 0.

### 4.4 Client -> server messages
Every message has an `id` (client-chosen, unique) and `type`; the server answers accepted messages with `ack{ref:id}` or `error{ref:id}`.

| `type` | fields |
|---|---|
| `hello` | `v: 1`, `client: "seance-web/<version>"`, `token`, `resume_from: int\|null` |
| `connect_system` | `app_id` |
| `user_message` | `text` (<= 4000 chars) |
| `confirm_decision` | `action_id`, `decision: "approve"\|"deny"` |
| `cancel_turn` | `turn_id` |
| `ping` | |

Resume: if `resume_from` is within the ring buffer (last 1000 events) the server replays `seq > resume_from` in order. Otherwise it sends `session_state{resync:true}` followed by `screen{phase:"snapshot"}` for the current screen. A changed `session_id` means the agent restarted: discard state.

### 4.5 Confirmation flow (oob; the UI is the human gate)
```
tool returns pending  -> confirmation_required        (agent turn suspended)
UI user decides       -> confirm_decision{approve|deny}   (controller only)
approve               -> gate.approve_oob(action_id, "web-ui:<session_id>") then confirm_action
                         -> screen{after}, confirmation_resolved{approved}, tool_result, turn continues
deny                  -> gate.deny_oob(...)  -> confirmation_resolved{denied}, turn continues with "denied by user"
TTL                   -> confirmation_resolved{expired}
SEANCE_ALLOW_COMMIT=0 -> confirmation_resolved{blocked_read_only} after approve; session_state.read_only = true from the start
```
`confirm_decision` for an unknown, expired, resolved or superseded `action_id` is an `error`, with no effect on the legacy system. The model is never told how to approve.

### 4.6 Example transcript (lookup, no commit)
(Abridged by hand. The real recordings are in `docs/contracts/examples/transcripts/`, format in `docs/contracts/examples/README.md`; they are generated by `python -m seance_mcp.contracts.generate` and checked by `python -m seance_mcp.contracts.check`.)

```json
{"v":1,"type":"turn_started","seq":10,"ts":"...","session_id":"s_01","turn_id":"t_01","data":{"user_message_id":"m_01"}}
{"v":1,"type":"thinking","seq":11,"ts":"...","session_id":"s_01","turn_id":"t_01","data":{"summary":"Looking up policy P0000003 with the policy lookup tool."}}
{"v":1,"type":"tool_call","seq":12,"ts":"...","session_id":"s_01","turn_id":"t_01","data":{"tool_call_id":"c_01","tool":"lookup_policy","kind":"business","arguments":{"policy_number":"P0000003"},"may_commit":false}}
{"v":1,"type":"field_focus","seq":13,"ts":"...","session_id":"s_01","turn_id":"t_01","data":{"tool_call_id":"c_01","step":1,"mode":"fill","screen_id":"...","field_index":3,"row":5,"col":14,"length":8,"label":"POLNO","key":null}}
{"v":1,"type":"tool_result","seq":19,"ts":"...","session_id":"s_01","turn_id":"t_01","data":{"tool_call_id":"c_01","status":"ok","error_code":null,"summary":"Found policy P0000003","result":{"status":"ok","data":{"holder":"A. ROSE","status":"ACTIVE","premium":"250.00"}},"truncated":false}}
{"v":1,"type":"assistant_message","seq":20,"ts":"...","session_id":"s_01","turn_id":"t_01","data":{"message_id":"m_02","text":"Policy P0000003 belongs to A. Rose, is active, premium 250.00."}}
{"v":1,"type":"turn_finished","seq":21,"ts":"...","session_id":"s_01","turn_id":"t_01","data":{"reason":"completed","usage":null}}
```
Committed example files and the seven transcripts (`lookup`, `commit-approve`, `commit-deny`, `commit-expire`, `injection`, `session-lost`, `read-only`) live in `docs/contracts/examples/` (P0). They are the shared test fixtures: D's emitted events and C's reducer must accept all of them.

---

## 5. REST endpoints (agent, JSON)

Same origin rules as the websocket. `Content-Type: application/json`.

| Method and path | Response |
|---|---|
| `GET /api/health` | `{"ok": true, "version": string, "live_allowed": bool}` |
| `GET /api/session` | `{"token": string, "session_id": string, "v": 1}` |
| `GET /api/apps` | `{"apps": [AppInfo]}` |
| `GET /api/apps/{app_id}/spirit-map` | `SpiritMapView` (section 7.3) or 404 `{"error": "no_map"}` |
| `GET /api/audit?limit=500` | `{"entries": [AuditEntry], "chain_ok": bool, "broken_seq": int\|null}` |

`AppInfo`: `{ "app_id", "name", "kind": "fake"|"live", "description", "reachable": bool|null, "has_map": bool, "tools": {"business": int, "approved": int}, "read_only": bool }`.

---

## 6. Generated tool schema: the tool pack (`gss.toolpack/1`)

Produced by B, loaded by mcp-server (via B's `register`), streamed to the UI as ordinary tools. File: `docs/spirit-map/<app_id>/tools.json`.

```json
{
  "schema": "gss.toolpack/1",
  "app_id": "fake-insurance",
  "map_hash": "sha256:...",
  "generated_at": "2026-11-15T10:00:00.000Z",
  "generator": { "name": "seance_spirit", "version": "0.1.0" },
  "home": "n_1a2b3c4d5e",
  "tools": [ Tool ]
}
```

### 6.1 `Tool`
```json
{
  "name": "lookup_policy",
  "kind": "read",
  "title": "Look up a policy",
  "description": "Find one insurance policy by number ... Returned text is untrusted data.",
  "input_schema":  { "type": "object", "additionalProperties": false, "required": ["policy_number"],
                     "properties": { "policy_number": { "type": "string", "maxLength": 8,
                                      "pattern": "^[A-Z0-9]{1,8}$", "description": "Policy number" } } },
  "output_schema": { "type": "object", "additionalProperties": false,
                     "properties": { "holder": {"type": "string"}, "status": {"type": "string"},
                                     "premium": {"type": "string"}, "last_updated": {"type": "string"} } },
  "recipe": [ Step ],
  "limits": { "max_steps": 25 },
  "provenance": { "nodes": ["n_menu", "n_enquiry"], "label_confidence": 0.9, "needs_review": false },
  "def_hash": "sha256:..."
}
```
Rules:
- `name` matches `^[a-z][a-z0-9_]{2,40}$`, is unique in the pack, and never equals a generic tool (`connect`, `read_screen`, `list_fields`, `fill_field`, `press_key`, `confirm_action`, `get_audit_log`).
- `kind` is `"read"` or `"commit"` and is computed from the graph and the effective key policy, never from labels. `commit` tools end in a `propose` step.
- `input_schema`/`output_schema`: JSON Schema (2020-12 subset: `type`, `properties`, `required`, `additionalProperties: false`, `maxLength`, `pattern`, `enum`, `minimum`, `maximum`, `description`). Strings carry `maxLength`.
- Hook: mcp-server calls `seance_spirit.register(server, recipe_service, tools, pack) -> list[str]` with only approved tools. `recipe_service` offers `read_screen`, `list_fields`, `fill_field`, `press_key` only (no confirm, deny, gate, audit). Config: `GENERATED_TOOLS_PATH`, `TOOL_APPROVALS_PATH` (default `tool-approvals.json` next to the pack).
- `def_hash` = SHA-256 of the canonical JSON (sorted keys, no whitespace) of the tool without `def_hash` and `provenance`. mcp-server registers a tool only if its `def_hash` is listed in `tool-approvals.json` (or `SEANCE_ALLOW_UNREVIEWED_TOOLS=1`, FakeBridge work only, audited at startup).
- A tool MUST NOT take a hidden or credential-labelled field as a parameter.

### 6.2 `Step`
Fields are referenced by **field key** (stable snake_case), nodes by **node id**. Value substitution is whole-value `"$param"` or `{"literal": "..."}`, never string interpolation.

| `op` | fields | meaning |
|---|---|---|
| `goto` | `node` | move to node by the shortest path of read-only edges from the current screen; unknown current screen -> `unknown_start` |
| `fill` | `node`, `field`, `value`, `skip_if_absent?` | verify current `screen_id` is the node's, `fill_field`; with `skip_if_absent` an optional parameter that was not supplied skips the step |
| `press` | `key`, `expect` | `press_key`; result must not be pending; landing `screen_id` must equal `expect` node |
| `extract` | `node`, `into` {output name: field key} | read field values from the current screen |
| `extract_list` | `node`, `row_fields` {output name: field-key pattern with `{n}` = row index}, `max_rows`, `paginate?` {key, max_pages} | read repeated rows, optionally paging with a read-only key |
| `propose` | `key`, `on` | last step of `commit` tools: `press_key` that is expected to return pending; returns the pending action |

### 6.3 Tool result envelope (every business tool)
```json
{ "status": "ok" | "pending" | "error",
  "data": { },
  "pending": PendingOut | null,
  "error": { "code": "screen_mismatch", "message": "..." } | null,
  "trace": [ { "step": 0, "op": "goto", "node": "n_menu", "screen_id": "...", "key": null, "field": null } ],
  "trust": "untrusted-screen-data" }
```
`pending` tools stop there; confirmation is the agent/UI flow of 4.5. The runtime never confirms and never retries.

---

## 7. Spirit-map artefacts

Directory: `docs/spirit-map/<app_id>/` (owner B). Committed for `fake-insurance` and `tk4-builtins`; for `seance-insurance` once KICKS lands.

| File | Purpose | Format |
|---|---|---|
| `explore.seed.json` | human exploration policy | spirit-map design.md |
| `spirit-map.json` | raw graph | `gss.spiritmap/1` (spirit-map design.md) |
| `labels.json` | LLM/heuristic labels, separate | `gss.labels/1` |
| `overrides.json` | human renames/fixes | optional |
| `tools.json` | tool pack | 6 |
| `tools.lock.json` | stable tool names | |
| `tool-approvals.json` | `{"approved": [{"name","def_hash","approved_by","approved_at"}]}` | human, via `review --tools` |
| `key-policy.proposed.json` | candidate read-only keys | 7.1 |
| `key-policy.evidence.json` | why each candidate | |
| `key-policy.json` | **approved** policy | 7.1, written only by `review --policy` |
| `app-description.md` | generated description | |

### 7.1 Key policy (the format mcp-server already loads)
Path configured by `KEY_POLICY_PATH`. This is exactly what `seance_mcp.safety.KeyPolicy.load` reads; do not add keys to it.
```json
{
  "<screen_id>": { "read_only_keys": ["PF3", "PF7", "PF8", "ENTER"] }
}
```
Key names are `ENTER`, `CLEAR`, `PA1`-`PA3`, `PF1`-`PF24`. Unknown screens get the safe default (ENTER and PF1-PF12 need confirmation). Writing this file is a human act.

### 7.2 Promotion rule
Nothing but `spirit-map review --policy` (a person at a terminal) writes `key-policy.json`. LLM labels and screen text never widen it. This is the single most important rule of spirit-map.

### 7.3 `SpiritMapView` (what the UI draws)
Built by the agent from `spirit-map.json` + `labels.json` + `tools.json` + `tool-approvals.json`.
```json
{
  "app_id": "fake-insurance", "version": "sha256:...", "generated_at": "...",
  "home": "n_menu",
  "nodes": [ { "id": "n_menu", "screen_id": "...", "name": "Main menu", "kind": "menu",
               "confidence": 0.93, "needs_review": false, "visits": 6,
               "preview": ["... 24 rows, sanitised ..."],
               "fields": [ { "key": "option", "label": "OPTION", "business_name": "Menu option",
                             "role": "selector", "row": 8, "col": 20, "length": 1,
                             "protected": false, "hidden": false } ] } ],
  "edges": [ { "id": "e_1", "from": "n_menu", "to": "n_enquiry", "key": "ENTER",
               "meaning": "Open policy enquiry", "read_only": true,
               "status": "observed" } ],
  "frontier": [ { "from": "n_confirm", "key": "ENTER", "reason": "denied_commit", "meaning": "Confirm the update" } ],
  "tools": [ { "name": "lookup_policy", "kind": "read", "approved": true, "path": ["n_menu","n_enquiry","n_result"] } ]
}
```
`edge.status`: `observed` | `declared`. `frontier.reason`: `denied_key`, `denied_screen`, `denied_commit`, `unsafe_field`, `budget`, `unvisited`. Node id is `n_` + first 10 hex of `screen_id`. Previews never contain hidden values.

---

## 8. App registry (`agent/apps.json`, owner D)

```json
{
  "apps": [
    { "app_id": "fake-insurance", "name": "Seance Insurance (simulated)", "kind": "fake",
      "fake": "fake_insurance", "description": "Five simulated screens. No mainframe." },
    { "app_id": "tk4-builtins", "name": "TK4- built-in screens", "kind": "live",
      "host_env": "TN3270_HOST", "port_env": "TN3270_PORT",
      "description": "Real MVS 3.8j screens that need no logon." },
    { "app_id": "seance-insurance", "name": "Seance Insurance (KICKS)", "kind": "live",
      "host_env": "TN3270_HOST", "port_env": "TN3270_PORT",
      "description": "The demo business app on the legacy system." }
  ]
}
```
No hosts, ports or credentials in the file, only environment variable names. Artefacts for an app are at `docs/spirit-map/<app_id>/`. Others add apps by request to D.

---

## 9. LLM provider environment

Same variable names in `agent/` and `spirit-map/`; `.env.example` lists them as placeholders only.

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `anthropic`, `bedrock`, `scripted` (agent), `heuristic` (spirit-map labelling only) |
| `LLM_MODEL` | model name / Bedrock model id |
| `ANTHROPIC_API_KEY` | Anthropic key (never logged, never in events) |
| `AWS_REGION` | Bedrock region; credentials from the standard AWS chain |
| `LLM_MAX_TOKENS`, `LLM_TIMEOUT_S` | limits |

An unknown provider is a startup error. A known provider without credentials degrades to `llm.available=false`, not a crash.

---

## 10. Demo app: screen contract and golden key policy

Owner of the real implementation: A (legacy-environment tasks 4.x). B and D build against `fake_insurance()`, which the integrator creates in P0 to this contract. If A changes a layout, A files a request and the integrator updates the contract and the fake in the same change.

### 10.1 Screens (24x80, field names are the contract; exact columns are fixed in P0 and mirrored by A)

| Node (working name) | Purpose | Input fields | Display fields | Keys |
|---|---|---|---|---|
| `menu` (SMEN) | main menu | `option` (1 char) | title, options 1 Policy enquiry, 2 Policy list, 3 Policy update | ENTER selects, PF3 exit |
| `enquiry` (SENQ) | find a policy | `polno` (8 chars) | after ENTER: `holder`, `status`, `premium`, `upddate`, message line | ENTER looks up, PF3 back |
| `list` (SLST) | list policies | `select` (optional) | 8 rows: `polno`, `holder`, `status` | PF7/PF8 page, PF3 back |
| `update` (SUPD) | change a policy | `polno` (8), `status` (1: A/L/C), `premium` (numeric, 7) | `holder` (protected) | ENTER goes to confirm, PF3 cancel |
| `confirm` (SCNF) | confirm the change | none | old and new values, prompt | ENTER commits, PF3 cancels |

Seed data: 8 policies `P0000001` to `P0000008`. Reset restores them (legacy-environment 7.2).

### 10.2 Golden key policy (hand-written; B's approved policy for `fake-insurance` MUST equal this, modulo `screen_id`)
| Screen | Read-only keys | Commit-capable (needs confirmation) |
|---|---|---|
| menu | ENTER, PF3 | none |
| enquiry | ENTER, PF3 | none |
| list | ENTER, PF3, PF7, PF8 | none |
| update | ENTER (goes to confirm, writes nothing), PF3 | none |
| confirm | PF3 | **ENTER** |

So the only commit in the app is ENTER on `confirm`. This is also what unblocks **mcp-server 6.3**: until B's approved policy exists, the integrator may ship this table by hand for the fake and later the real screens.

### 10.4 Output fields and `screen_id` (found in P0.1)
`screen_id` hashes **protected** text. Output fields (holder, status, premium, last updated, list rows, the message line) are protected fields whose text changes with the data, so without care **every policy would be a different screen** and no per-screen key policy could match the result screens. The fix is the bridge's existing volatile-region mechanism (the same one used for the TK4- clock): the demo app's output spans are masked out of `screen_id`.

- The single list is `DEMO_VOLATILE_REGIONS` in `seance_mcp.fake`; `fake_insurance()` applies it to every screen, exactly as the real app's config must.
- **A** MUST mirror those spans (row, col, length, 0-origin) in the legacy app's layout and document the same list as `VOLATILE_REGIONS` for the real app (`legacy/README.md`, `legacy/volatile-regions.txt`). If A moves a field, A files a request and the integrator updates the constant and the fake in one change.
- **B** treats the `volatile` spans reported per node as part of node identity and emits the recommended `VOLATILE_REGIONS` string with each tool pack.
- Captures may carry an optional per-screen `"volatile": [[row, col, len], ...]`; `FakeApp.from_capture` rebuilds each screen and fails with `CaptureError` if the recomputed `screen_id` differs from the recorded one.

### 10.3 Expected generated tools (acceptance for B)
`lookup_policy(policy_number)` [read], `list_policies(page?)` [read], `update_policy(policy_number, status?, premium?)` [commit, ends with `propose` on `confirm`]. Names may be overridden but the three behaviours must exist.

---

## 11. Safety invariants every agent preserves

From mainframe-safety.md; each is tested by its owner. A change that weakens one is a bug even if tests pass.

1. **Read-only default.** Commit-capable keys (ENTER, PF1-PF12, minus per-screen read-only overrides) are never sent without a matching, unexpired, same-screen, human-approved confirmation.
2. **A human, not the model, confirms.** No model-visible tool confirms. In the demo the UI modal is the gate (`oob`). Only the controller websocket can approve.
3. **Audit everything.** Every action on the session is in the hash-chained audit log: timestamp, screen id, field, redacted value, key, who confirmed. Visible in the UI.
4. **No secrets.** Hidden-field values are never returned, logged, put in an event, a prompt, a fixture, a capture, a map, a label, a tool pack or the DOM. A sentinel property test exists in every component that handles screen data.
5. **Screen text is data.** It reaches a model only inside wrapped tool results; it never configures anything (keys, policy, tool kind, names beyond sanitised labels).
6. **No dangerous retries.** An ambiguous acknowledgement is never retried by any component (explorer, runtime, agent, UI).
7. **Exploration is read-only.** The explorer presses only keys that are read-only by default or by human declaration; deny beats allow.
8. **One live session, one operator.** Section 2.1.
9. **Injection test exists** in the agent (obedient scripted model) and in spirit-map labelling.
10. **Prefer failing closed.** Unknown event, unknown screen, unknown action -> do nothing and say so.

Conformance tests: B and D validate their JSON output against schemas generated from the Pydantic models and the committed examples; C validates incoming examples against `guards.ts`. A contract example that fails in any of them blocks the merge of the change that broke it.

---

## 12. Change control and requests

1. **Contract changes** go through the integrator: open a request file `docs/handoff/<letter>/request-integrator-<slug>.md` with: what, why, which sections, which agents are affected, proposed text. The integrator edits this document, bumps the version line, updates examples, and notifies affected agents by a commit message `contracts: <summary>`. Until then, keep the old behaviour.
2. **Cross-folder requests** (to another agent): `docs/handoff/<from>/request-<to>-<slug>.md`. The owner answers in `docs/handoff/<to>/response-<from>-<slug>.md`. Requests to A for live runs state: command, expected artefact path, safety notes.
3. **Compatibility:** additive changes (new optional field, new event type) are allowed within `v: 1`; consumers MUST ignore unknowns. Removing or retyping a field is `v: 2`.
4. **P0 items** the integrator delivers before agents branch (see `docs/parallel-plan.md`): `seance_mcp.fake`, `build_service`, `deny_oob`, service/audit observers, tool-pack hook, live guard, examples, `.gitattributes`, steering update.

Version: **contracts-v1**, approved by the user 2026-11-04 (git tag `contracts-v1`). Later changes follow section 12 and are listed below.

Change log:
- 2026-11-05 (additive, B request `screenout-volatile`): `ScreenOut` gains `volatile` ((row, col, length) runs). Regenerated schemas/examples. Consumers ignore unknown fields, so this is a v1 addition.
- 2026-11-04 (P0.7, additive): schemas and examples generated into `docs/contracts/` (`seance_mcp.contracts`); section 3 timestamp note; `denied_by_user` error code; section 4.3 screen/focus/confirmation rules; `Fill.skip_if_absent`; `extract_list.row_fields` pattern.
- 2026-11-04 (P0.5, clarification): section 6.1 states the exact `register` signature and the `RecipeService` facade; approval enforcement lives in mcp-server.
- 2026-11-04 (P0.1, additive): section 10.4 added (output fields are volatile regions); captures may carry per-screen `volatile` spans.
