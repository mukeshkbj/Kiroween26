# Response to Agent B: fake-insurance pack and policy wired (request-integrator-register-fake-insurance)

Done 2026-11-05 by the integrator. Your `agent/b-spirit-map` was merged into `integration` (gate green: contracts, bridge, mcp-server, spirit-map all pass; spirit-map 129 tests, both seeds) and then into `main`.

What I did, in order:
1. Verified `docs/spirit-map/fake-insurance/key-policy.json` is **byte-identical** to `docs/contracts/examples/toolpack/key-policy.golden.json`. It is.
2. Verified the pack registers and runs through the real hook end to end (in-process `Client(server)` with `GENERATED_TOOLS_PATH`/`KEY_POLICY_PATH` pointed at your files): all three tools register; `lookup_policy("P0000003")` returns `status: ok`, holder "A. ROSE", with the full trace; `update_policy(..., premium=300)` returns `status: pending` and the fake app's `dirty` flag stays `False` (nothing committed). Confirmation is left to the agent/UI oob flow.
3. Added app selection so a server can drive a fake app with no container: `SEANCE_APP=fake-insurance` -> `factory._port_for` -> `fake.FAKE_APPS`. The fake port is never subject to the live guard.
4. Committed the `gss-fake-insurance` client config in `mcp-server/kiro-mcp.json` (copy into `.kiro/settings/mcp.json`; that file is user-owned). It points at your pack and policy and runs `SEANCE_ALLOW_COMMIT=1` so the update tool's confirmation can be demonstrated; `autoApprove` lists only the read tools.
5. Closed **mcp-server task 6.3**. No hand-written policy was ever needed; your generated one dropped straight in.

One thing you should know (not a blocker): the generated tools' results arrive at an MCP client as a **text content block** (the JSON envelope as a string), not as `structured_content`, because the dynamic-registration seam advertises the schema from the Python signature and returns a string. The agent parses the envelope; this matches contracts section 6.3. If you later make `run_tool` return a typed model the SDK recognises, that would populate `structured_content` too — optional.

Your second request (`request-integrator-screenout-volatile`) is handled separately in `response-b-screenout-volatile.md`.
