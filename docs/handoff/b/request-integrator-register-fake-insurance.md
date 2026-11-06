# Request to the integrator: load the fake-insurance tool pack and approved key policy (unblocks mcp-server 6.3)

From: Agent B (spirit-map). Task 6.7. Everything B owns is committed on `agent/b-spirit-map`.

## What is ready
`docs/spirit-map/fake-insurance/` now holds the full set:
- `tools.json` — three tools: `lookup_policy` (read), `list_policies` (read), `update_policy` (commit, ends in `propose` on the confirm screen).
- `tool-approvals.json` — all three approved (name + `def_hash`), by `agent-b-demo`.
- `key-policy.json` — the **approved** policy. It equals `docs/contracts/examples/toolpack/key-policy.golden.json` exactly (verified in `tests/test_generator.py::test_proposed_policy_equals_the_golden_modulo_screen_id`). This is the file mcp-server 6.3 was waiting for.
- `key-policy.proposed.json` + `key-policy.evidence.json`, `app-description.md`, `tools.lock.json`, `labels.json`, `overrides.json`, `spirit-map.json`, `explore.seed.json`.

## What I'd like the integrator to do
1. Point mcp-server at the pack for the fake-insurance server config: `GENERATED_TOOLS_PATH=docs/spirit-map/fake-insurance/tools.json`, `TOOL_APPROVALS_PATH` defaults to `tool-approvals.json` beside it, and `KEY_POLICY_PATH=docs/spirit-map/fake-insurance/key-policy.json`.
2. Replace the hand-written fake policy with `key-policy.json` for `fake-insurance` (mcp-server 6.3). They are identical modulo `screen_id`, so this is a no-behaviour-change swap that closes the task.
3. The hook calls `seance_spirit.register(server, recipe_service, tools, pack)`. It is implemented and tested (`tests/test_runtime.py::test_register_advertises_strict_schema_and_runs`). It advertises each tool's strict JSON Schema and returns the registered names. Agent D can then drive the three tools.

## Facts the integrator needs
- `register` uses one SDK-private seam, `server._tool_manager._tools`, because `mcp` 2.3.0 derives a tool's advertised schema from the Python signature, not from a schema you hand it (task 6.1 spike, recorded in `.kiro/specs/spirit-map/design.md`). A test (`test_register_is_the_only_private_sdk_seam`) fails if that spreads. If the SDK gains a public "register with schema" API, this is the one place to change.
- The SDK validates calls against the signature (required + types) only; `maxLength`/`pattern`/`enum`/`additionalProperties` are advertised but enforced by `run_tool` itself (jsonschema), which returns `invalid_arguments` before touching the session. Tested.
- `volatile_regions` is carried as a string on the pack; `run_tool` uses it so output-field values are read positionally (a populated list cell keys on `r6c11`, not on the holder name it holds). If A's real app uses different regions, regenerate; nothing is hard-coded.
- No recipe confirms. The commit tool returns `status:"pending"` with the gate's `PendingOut`; the UI/agent confirmation flow (contracts 4.5) takes it from there.
