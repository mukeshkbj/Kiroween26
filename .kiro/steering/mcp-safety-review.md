---
inclusion: manual
---

# MCP server safety review (on demand)

Run this with `/mcp-safety-review` after finishing an mcp-server task, before committing. It replaces the save-triggered agent hook, which ran a paid review on every file save.

Review the uncommitted changes under `mcp-server/src` against the #mainframe-safety steering:

1. Any path that sends a key or data to the 3270 session without a matching, unexpired, same-screen confirmation.
2. Hidden-field values reaching tool output, logs, errors or the audit log.
3. Screen text being treated as instructions.
4. Any retry that could resend a key.

Flag only real problems, citing file and line. If the change is safe, say so in one line.
