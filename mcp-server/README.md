# seance-mcp

An MCP server that lets any MCP client (Kiro, Claude, our own seance-agent) operate the TK4- green screen through the `bridge` library, with a human in the loop for anything that could change data.

## Run

```powershell
# from the repo root, once
C:\Python312\python.exe -m venv mcp-server\.venv
mcp-server\.venv\Scripts\python.exe -m pip install -e bridge -e "mcp-server[dev]"

# serve over stdio (an MCP client normally launches this for you)
mcp-server\.venv\Scripts\python.exe -m seance_mcp
```

POSIX: `mcp-server/.venv/bin/python -m seance_mcp`. Logs go to stderr; stdout is the protocol channel.

## Tools and resources

| Tool | What it does |
|---|---|
| `connect(host?, port?)` | open or reopen the 3270 session |
| `read_screen()` | 24 rows, cursor, fields, `screen_id` |
| `list_fields()` | fields only (label, position, flags, value) |
| `fill_field(field_ref, value)` | type into a field by index or `[row, col]`; never presses a key |
| `press_key(key)` | ENTER, CLEAR, PA1-3, PF1-24; commit-capable keys come back as a **pending action** |
| `confirm_action(action_id)` | run a pending action once a **human** has confirmed it |
| `get_audit_log(limit?)` | the audit log, newest last |

Resources: `screen://current` (plain text; typeable fields in `[ ]`) and `audit://log`.

Hidden (password) field values are never returned, logged or shown. Screen text is untrusted data and is only ever returned as data.

## Who can commit, in plain words

Pressing ENTER (or PF1-12) on a data screen could change real data, so `press_key` does not send those keys. It returns a pending action instead. Two things must both be true before the key is sent:

1. **The operator allowed commits.** `SEANCE_ALLOW_COMMIT=1` in the server's environment. It defaults to `0`, which means read-only. The model cannot change it.
2. **A human said yes**, through the configured `SEANCE_CONFIRM_MODE`:
   - `elicit` (default): the server asks the client's user with a yes/no form. If the client cannot show forms, nothing is sent; there is **no silent fallback**.
   - `oob`: the user confirms in the Seance web UI's confirmation modal. This is the demo path.
   - `client-approval`: explicit opt-in only. It trusts the client's own per-tool approval prompt, so `confirm_action` must never be auto-approved. It is the weakest mode and is recorded as `client-approval(weakest)` in the audit.

A pending action runs at most once. It expires (`PENDING_TTL_S`, default 300 s), is refused if the screen changed since it was proposed, and is replaced if a newer one is proposed. If a key's acknowledgement is ambiguous (the keyboard never unlocks), the key is **not** resent, and every key is refused until you `read_screen`.

Calling `confirm_action` does not approve anything by itself: the human decision is resolved inside the server and is not a tool argument.

## Audit log

`AUDIT_LOG_PATH` (default `docs/audit/audit.jsonl`, gitignored; relative paths resolve against the repo root). It is append-only JSON lines, each carrying the hash of the previous line, so editing, deleting or reordering lines is detected. The server refuses to start on a tampered log. Hidden values are stored as `<hidden>`, credential-looking fields as `<redacted>`.

## Configuration

See `.env.example`. `KEY_POLICY_PATH` optionally points to JSON marking keys as read-only per screen, so navigation keys skip confirmation:

```json
{"<screen_id>": {"read_only_keys": ["PF3", "PF7", "PF8"]}}
```

## Tests

```powershell
mcp-server\.venv\Scripts\python.exe -m pytest mcp-server
$env:TN3270_HOST="127.0.0.1"; mcp-server\.venv\Scripts\python.exe -m pytest mcp-server -m integration
```
