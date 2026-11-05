# Agent B: end-to-end pipeline on fake-insurance (17 Nov milestone core)

Date: 2026-11-04. Branch `agent/b-spirit-map`. Tasks 1-6 complete; task 7 pending Agent A.

## What works end to end on `fake-insurance`
`explore -> label -> generate -> review -> runtime`, all against `seance_mcp.fake` (no container):

```
python -m seance_spirit explore  --app fake-insurance --fake fake-insurance
python -m seance_spirit label    --app fake-insurance
python -m seance_spirit generate --app fake-insurance
python -m seance_spirit review   --app fake-insurance --tools  --by you
python -m seance_spirit review   --app fake-insurance --policy --by you
```

Committed artefacts in `docs/spirit-map/fake-insurance/`: `explore.seed.json`, `spirit-map.json`,
`labels.json`, `overrides.json`, `tools.json`, `tools.lock.json`, `tool-approvals.json`,
`key-policy.proposed.json`, `key-policy.evidence.json`, `key-policy.json`, `app-description.md`.

## Acceptance
- **Three tools** (contracts 10.3): `lookup_policy` (read), `list_policies` (read, paginated),
  `update_policy` (commit, ends in `propose` on the confirm screen).
- **Golden key policy (REQ-039):** the approved `key-policy.json` equals
  `docs/contracts/examples/toolpack/key-policy.golden.json` exactly. The confirm screen's ENTER
  is never a candidate; it is the one real commit.
- **Runtime (REQ-027/028):** against a live FakeApp through the real service, `lookup_policy`
  returns A. ROSE/ACTIVE/250.00; `list_policies` returns 8 rows; `update_policy` ends `pending`
  with the gate's `PendingOut`, the fake saw no commit key, and the policy data is unchanged.
- **Label independence (REQ-036):** key policy, tool kinds and recipe key sets are identical for
  heuristic and hostile label files. **Injection (REQ-038):** a model that returns
  `read_only:true, confidence:1.0` changes nothing but a string.
- **Registration (6.1):** `register` advertises each tool's strict schema and runs via the SDK;
  `run_tool` enforces maxLength/pattern/enum/additionalProperties itself. Spike recorded in design.md.

## Tests
129 pass (`python -m pytest`, ~70 s). `scripts/gate.ps1 -Only spirit-map,contracts,ownership` is ok.
Suites: policy (+10 mutants), graph/store, explorer (property + mutation + oracles), labelling,
generator (snapshot, golden policy, label independence, credential refusal), runtime (lookup/list/
update, abort codes, register adapter), review (hash invalidation, policy promotion).

## Task 7 (live TK4-) — handed to A
`docs/handoff/b/request-a-tk4-captures-and-run.md`: A records `legacy/captures/tk4-builtins/*`
and runs the marked `explore --attach` for `tk4-builtins`. Seed is committed
(`docs/spirit-map/tk4-builtins/explore.seed.json`): non-commit keys only, clock regions volatile,
credential fields denied, nothing declared. B never touches the container.

## For the integrator
`docs/handoff/b/request-integrator-register-fake-insurance.md` unblocks **mcp-server 6.3**: point
the fake-insurance server at B's `tools.json`/`tool-approvals.json`/`key-policy.json`. The policy
is a no-behaviour-change swap for the hand-written one.
