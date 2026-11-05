# spirit-map — Tasks

Owner: **Agent B**. Folder: `spirit-map/`, `docs/spirit-map/**`, `.kiro/specs/spirit-map/`, `docs/handoff/b/`. Branch: `agent/b-spirit-map`. Read `docs/contracts.md` first; do not edit any other folder.

Ordered so the safety machinery and its property tests exist before the explorer touches anything, and everything runs on FakeBridge first. Dates are the plan in `docs/parallel-plan.md`.

## 0. Prerequisites (integrator, parallel-plan P0; blocked until done)
- [x] 0.1 `seance_mcp.fake` exports `FakePort` and `FakeApp` (value-aware transitions, records every key and a `dirty` flag). Today `FakePort` lives in `mcp-server/tests` and ignores field values.
- [x] 0.2 `mcp-server` has `build_service(settings, port)` and the tool-pack hook (`seance_mcp.toolpack`, `GENERATED_TOOLS_PATH`, `TOOL_APPROVALS_PATH`, `SEANCE_ALLOW_UNREVIEWED_TOOLS`). Done in P0.2/P0.5.
- [x] 0.3 Contract examples exist under `docs/contracts/examples/` (tool pack, key policy, SpiritMapView).

## 1. Scaffold (by 7 Nov)
- [x] 1.1 `spirit-map/` package (`pyproject.toml`, Python >=3.12, `src/seance_spirit/`). Pin with `==`: `pydantic`, `anyio`, `hypothesis`, `pytest`, `jsonschema`; install `../bridge` and `../mcp-server` editable. `anthropic` and `boto3` as optional extras, pinned.
- [x] 1.2 `.env.example` (LLM vars from contracts section 9, `GSS_LIVE_OK=0`), `README.md` with the "LLM names, never decides safety" principle up front.
- [x] 1.3 Register markers `integration` and `llm`; both skip by default.

## 2. Policy first (REQ-001 to REQ-004, REQ-033)
- [x] 2.1 `seed.py`: `ExploreSeed` with validation (seed that fills a hidden/credential field is an error; unknown keys are errors).
- [x] 2.2 `policy.py`: pure `EffectivePolicy.may_press`. Deny beats allow. Text hints can only add denies.
- [x] 2.3 Unit tests: deny wins; commit-capable key denied by default; declared key allowed only on its screen; hint cannot relax.
- [x] 2.4 Mutation-check list recorded in tasks as each rule is added (remove rule -> a test fails).
  Recorded: `tests/test_policy_mutations.py` builds 10 mutants of `policy.py` (drop global/screen/per-screen deny, drop hint deny, hint relaxes, allow-before-deny, commit check removed, declared keys on every screen, approved policy ignores screen, hints cleared) and requires each to fail `policy_invariants.check`. All killed.

## 3. Graph and store (REQ-009 to REQ-013)
- [x] 3.1 `graph.py`: nodes, edges, frontier; stable ids; merge; drift; shortest read-only path.
- [x] 3.2 `store.py`: atomic write, canonical ordering, leak check.
- [x] 3.3 Property tests: ids stable under reorder; merge is idempotent; write then read is identity; sentinel never survives a write.

## 4. Explorer on FakeBridge (REQ-001 to REQ-008) (by 10 Nov)
- [x] 4.1 `strategies.fake_apps()` (random apps with mutating and hidden-field screens).
- [x] 4.2 `explorer.py`: frontier search, return-path discipline, halting (`lost`, `ambiguous_ack`, session loss), budgets, attach mode, harvest.
- [x] 4.3 Property tests REQ-033 (explorer safety, own bookkeeping, mutation-checked), REQ-034 (completeness), REQ-032 (replay, with `replay.py`).
- [x] 4.4 Hand-written `fake-insurance` seed and a deterministic run that yields the 5-screen map (menu, enquiry, result, list, update, confirm frontier); commit `docs/spirit-map/fake-insurance/`.
- [x] 4.5 Milestone: `explore` + `replay` green on `fake-insurance`; summary to `docs/handoff/b/`.

## 5. Labelling (REQ-014 to REQ-018) (by 13 Nov)
- [x] 5.1 `labels.py` schema + sanitising; `labeller.py` heuristic mode.
- [x] 5.2 `llm.py`: `LlmClient` protocol, `ScriptedLlm`, anthropic and bedrock adapters (env-driven, no keys logged), prompt-hash cache.
- [x] 5.3 Prompt builder: screen text delimited as data; response validated; failures fall back and are recorded.
- [x] 5.4 Tests: REQ-036 (label independence), REQ-038 (injection fixture), REQ-035 on prompts (sentinel never in a prompt), cache round-trip.
- [ ] 5.5 Optional `llm`-marked test against a real provider; capture one real labelled run for the journal (screenshot + a surprise).

## 6. Generator and runtime (REQ-019 to REQ-031) (by 15 Nov)
- [x] 6.1 **Spike:** dynamic tool registration with `mcp` 2.x `MCPServer` (inputSchema from JSON Schema, kwargs handler). Record result in design.md; pick adapter or the single-tool fallback.
- [x] 6.2 `generator.py` + `keypolicy.py`: candidates and evidence; tool derivation (lookup, list, update); schemas; names + `tools.lock.json`; refuse hidden/credential params.
- [x] 6.3 `describe.py`: `app-description.md` with Mermaid flow.
- [x] 6.4 `runtime.py`: `run_tool`, `register`; abort codes; trace; step budget.
- [x] 6.5 `review.py` + CLI: `review --tools`, `review --policy` (records `approved_by`, `approved_at`; only writer of `key-policy.json`).
- [x] 6.6 Tests: REQ-037 snapshots, REQ-039 golden policy for `fake-insurance`, runtime against `FakeApp` (lookup, list, update ends `pending` and the fake saw no commit key), `screen_mismatch` and `unknown_start` paths, approval hash invalidation on edit.
- [x] 6.7 Handoff request to the integrator: mcp-server registers packs (P0 hook) and loads `key-policy.json`. This unblocks **mcp-server 6.3** (hand-written policy replaced by the approved one for `fake-insurance`).

## 7. Live TK4- built-ins (REQ-040) (by 17 Nov)
- [ ] 7.1 Handoff request to **Agent A** for `legacy/captures/tk4-*.json` (recorded real screens, format in contracts section 2). FakeBridge replays them so B can test against real layouts without touching the container.
- [ ] 7.2 `tk4-builtins` seed (welcome screen, bogus-logon error; clock volatile regions). Explore against captures.
- [ ] 7.3 Request A (or the integrator) to run the marked live exploration; commit the resulting map under `docs/spirit-map/tk4-builtins/`.
- [ ] 7.4 Stretch: attach-mode run after a human logon (RFE/ISPF), map committed if clean.

## 8. Docs and journal
- [x] 8.1 `spirit-map/README.md`: pipeline, the human-in-the-loop widening cycle, how to review.
- [ ] 8.2 Journal entries to `docs/handoff/b/journal.md` (integrator merges into `docs/kiro-journal.md`): one surprise per stage.
- [ ] 8.3 After KICKS lands (legacy-environment 4.6): rerun the pipeline on `seance-insurance`, review, approve, commit artefacts. Not a blocker for the 17 Nov milestone.
