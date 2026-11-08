# START HERE: Agent D (seance agent)

Branch `agent/d-seance-agent`. Worktree `D:\Kiro\gss-wt\d\Kiroween26` (open exactly this folder as your Kiro workspace).
You own: `agent/`, `.kiro/specs/seance-agent/`, `docs/handoff/d/`. Nothing else.

## First command, always
```
git branch --show-current
```
It must print `agent/d-seance-agent`. If it prints anything else, stop and tell the user.

## Rules that never bend
1. **Write only in your paths.** Need a change in `mcp-server/`, `bridge/`, the contracts or another agent's folder? Write `docs/handoff/d/request-<owner>-<slug>.md` and carry on.
2. **Never touch the live container `gss-legacy`.** You have no `.env`, no `.tools/` and no `.gss-live-ok` here, and a live `connect` is refused (`live_not_allowed`). Use `seance_mcp.fake` (`fake_insurance()`). The live end-to-end run (task 8.3) is done by Agent A on request.
3. `docs/contracts.md` (tag `contracts-v1`) is law. Sections 3, 4, 5, 8, 9, 11 are yours. Examples, transcripts and JSON Schemas: `docs/contracts/` (read-only for you). If the protocol is wrong, request a change; do not diverge.
4. **The thesis of your component: even a fully compromised model cannot change data on the legacy system.** The model gets no tool that confirms, cannot name the confirmer, and does not write the confirmation modal's content. Only the controller websocket can approve. Screen text reaches the model only inside tool results marked untrusted. Safety does not rely on the model behaving: test with an obedient model (`GullibleLlm`).
5. Rhythm: `git merge main` each day (no rebasing pushed branches, no force-push); one commit per task, message `agent: <task id> <what>`; `powershell -File scripts/gate.ps1 -Only agent,contracts` and `scripts/check-ownership.ps1` before a PR. `git push -u origin agent/d-seance-agent`; never push to `main`.
6. Journal: dated lines to `docs/handoff/d/journal.md` (one real surprise per section 4, 5 and 7).
7. Kiro sub-agents (context-gatherer) may be used for read-only research inside this worktree only.

## Read, in order
1. `docs/contracts.md` sections 3, 4, 5, 8, 9, 11, then `docs/contracts/examples/README.md`.
2. `.kiro/specs/seance-agent/{requirements,design,tasks}.md` (task 0.x prerequisites are done).
3. `mcp-server/src/seance_mcp/`: `factory.py` (`build_service`), `service.py` (`observe`, `deny_action`, `confirm_action`), `safety.py` (`approve_oob`, `deny_oob`, `decide`, `GateError`), `observe.py` (`OpEvent`), `toolpack.py`, `fake.py`.
4. **`mcp-server/src/seance_mcp/contracts/record.py`**: a small stand-in that drives the real service and maps `OpEvent`s and audit entries into the contract's events. It produced the transcripts you must match. Read it as a worked example of the mapping (when to emit `screen before/after`, `field_focus`, `audit_entry`, when `tool_result` comes relative to `confirmation_resolved`). It is not your implementation; write yours in `agent/`.
5. `seance_mcp/contracts/check.py` (`check_stream`) shows the ordering rules your streams must satisfy.

## Facts you need
- In-process wiring: `server, service = build_service(settings, port, registrar=...)`; `service.gate` is the handle for `approve_oob(action_id, "web-ui:<session_id>")` and `deny_oob`; `service.deny_action(action_id, who)` audits a denial. None of these is a tool. The model is offered read_screen, list_fields, fill_field, press_key and the business tools only (never `confirm_action`, `connect`, `get_audit_log`).
- `SEANCE_CONFIRM_MODE=oob`. `confirm_action` over MCP stays refused (`awaiting_oob`) until `approve_oob` was recorded for that action.
- Tool results with `status: pending`: emit `confirmation_required` (content from `service.gate.pending`, never from model text), suspend the turn, emit exactly one `tool_result` after the decision (contracts 4.3, 4.5).
- Business tools come from Agent B's pack; until B merges (about 17 Nov) use a two-tool stub built over the generic service (task 5.3), or `docs/contracts/examples/toolpack/tools.json` with a test registrar.
- The fake app's recorded `confirm` review screen has an empty `field_snapshot` (all fields protected). That is expected.
- Timestamps: envelope `ts` has milliseconds and `Z`; `AuditEntry.ts` is passed through untouched.

## Setup in this worktree
```
cd agent
python -m venv .venv                      # Python 3.12
.venv\Scripts\python.exe -m pip install -e ..\bridge -e ..\mcp-server[dev] -e .[dev]
```
Create `agent/pyproject.toml` first (task 1.1). Pin every dependency with `==`: reuse `mcp==2.3.0 pydantic==2.14.2 anyio==4.16.0 pytest==8.4.2 hypothesis==6.170.14 jsonschema==4.26.0` and look up current exact versions of `fastapi`, `uvicorn`, `httpx`, `anthropic` (boto3 as an extra) before pinning.

## Milestones (docs/parallel-plan.md)
Sun 8 Nov: scaffold and events. Thu 12 Nov: agent loop with the scripted LLM and the obedient-model injection test. Sun 15 Nov: API plus websocket; Agent C can run the UI against `python -m seance_agent` with the scripted provider (write the handoff note). Fri 20 Nov: Anthropic and Bedrock providers. Tue 24 Nov: integrated with C and B's pack on the `integration` branch.

## Your first prompt (paste into the agent)
```
You are Agent D of the Green Screen Seance parallel build. First run `git branch --show-current`; it must print agent/d-seance-agent, otherwise stop and tell me.
Read docs/handoff/d/START-HERE.md, docs/contracts.md (sections 3, 4, 5, 8, 9, 11), docs/contracts/examples/README.md, .kiro/specs/seance-agent/* in full, and mcp-server/src/seance_mcp/contracts/record.py as a worked example.
You own agent/, .kiro/specs/seance-agent/ and docs/handoff/d/ and nothing else. Never touch the live container; use seance_mcp.fake.
Thesis: even a fully compromised model cannot change data on the legacy system. The model has no confirm tool; only the controller websocket approves; test with an obedient scripted model.
Start with tasks 1 (scaffold with pinned deps), 2 (events and session, validated against docs/contracts/schemas and the examples), 3 (tool broker and mapper) and 4 (confirmation broker with the RuleBasedStateMachine and its mutation checks). Commit per task (agent: <task id> ...), tick tasks.md, journal surprises in docs/handoff/d/journal.md, run scripts/gate.ps1 -Only agent,contracts before each push. Anything you need from another folder goes in a request file under docs/handoff/d/. Report when task 4.4 is done.
```
