# Kiro journal

How Kiro was used on Green Screen Seance: spec and steering changes, in order.

- 2026-11-04: `.kiro/specs/mcp-server/requirements.md` changed
- 2026-11-04: `.kiro/specs/mcp-server/design.md` changed
- 2026-11-04: `.kiro/specs/mcp-server/tasks.md` changed
- 2026-11-04: Surprise in the elicitation spike: with the MCP v2 SDK, a value a resolver returns directly reaches the tool wrapped as AcceptedElicitation. A naive match would have turned 'client cannot ask the user' into 'user said yes'. Caught before any commit path existed.
- 2026-11-04: mcp-server live: Kiro-style stdio launch read the real TK4- welcome screen through our MCP server; ENTER came back as a pending action and confirm_action was refused read-only, all in the hash-chained audit log. Surprise: TK4-'s welcome-screen field goes straight to TSO logon, so the 'harmless' test input is a non-existent user id (IKJ56420I).
