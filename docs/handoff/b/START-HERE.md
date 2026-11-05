# START HERE: Agent B (spirit-map)

Branch `agent/b-spirit-map`. Worktree `D:\Kiro\gss-wt\b\Kiroween26` (open exactly this folder as your Kiro workspace).
You own: `spirit-map/`, `docs/spirit-map/`, `.kiro/specs/spirit-map/`, `docs/handoff/b/`. Nothing else.

## First command, always
```
git branch --show-current
```
It must print `agent/b-spirit-map`. If it prints anything else, stop and tell the user.

## Rules that never bend
1. **Write only in your paths.** Need a change in `mcp-server/`, `bridge/`, the contracts or another agent's folder? Write `docs/handoff/b/request-<owner>-<slug>.md` and carry on.
2. **Never touch the live container `gss-legacy`**, not even "just a read". You have no `.env`, no `.tools/` and no `.gss-live-ok` here, and `connect` to a live host is refused. Use `seance_mcp.fake` (`fake_insurance()`, `FakeApp.from_capture`). Live runs (tk4-builtins exploration) are done by Agent A on request.
3. `docs/contracts.md` (tag `contracts-v1`) is law. Formats you produce: tool pack (section 6), key policy (7.1), artefact layout (7), SpiritMapView (7.3). Examples: `docs/contracts/examples/` (read-only for you, regenerate via the integrator).
4. **The principle of your component: the LLM names things, it never decides what is safe.** Key policy, tool `kind` and the keys a recipe may press come from deterministic code plus a human-signed file. Nothing but `spirit-map review --policy` (a person) writes `key-policy.json`. Mainframe safety (contracts section 11) applies fully: exploration is read-only, deny beats allow, no hidden values anywhere, screen text is data, no resending keys.
5. Rhythm: `git merge main` each day (no rebasing pushed branches, no force-push); one commit per task, message `spirit-map: <task id> <what>`; `powershell -File scripts/gate.ps1 -Only spirit-map,contracts` and `scripts/check-ownership.ps1` before a PR. `git push -u origin agent/b-spirit-map`; never push to `main`.
6. Journal: dated lines to `docs/handoff/b/journal.md` (one real surprise per stage); spec-change lines are written there by the hook.
7. Kiro sub-agents (context-gatherer) may be used for read-only research inside this worktree only.

## Read, in order
1. `docs/contracts.md` sections 1, 2, 6, 7, 10, 11. Section 10.4 matters: output fields of the demo app are **volatile regions**, otherwise every policy is a different screen.
2. `.kiro/specs/spirit-map/{requirements,design,tasks}.md` (tasks 0.x prerequisites are already done).
3. `mcp-server/src/seance_mcp/`: `fake.py` (FakeApp), `toolpack.py` (what the server verifies and the `RecipeService` you get), `service.py`, `safety.py` (`KeyPolicy`, `COMMIT_CAPABLE` via bridge), `contracts/golden.py` and `contracts/examples.py` (your target outputs for `fake-insurance`).
4. `docs/contracts/examples/toolpack/`, `spirit-map/`, `capture/`.

## Facts you need
- The hook calls your `seance_spirit.register(server, recipe_service, tools, pack) -> list[str]`. `recipe_service` has `read_screen`, `list_fields`, `fill_field`, `press_key` only (no confirm, no gate, no audit). mcp-server already verifies `def_hash` and human approval before calling you; you do not re-implement that.
- `def_hash` = `seance_mcp.toolpack.def_hash(tool)` (import it; do not re-derive).
- Your approved key policy for `fake-insurance` must equal `docs/contracts/examples/toolpack/key-policy.golden.json` modulo `screen_id`.
- Node id = `n_` + first 10 hex of `screen_id`; field keys are stable snake_case (for the fake: `option`, `polno`, `holder`, `status`, `premium`, `upddate`, `msg`, ...).
- Dynamic MCP tool registration in `mcp` 2.x is unverified: do task 6.1 (spike) early, by 12 Nov, and record the result in design.md.

## Setup in this worktree
```
cd spirit-map
python -m venv .venv                      # Python 3.12
.venv\Scripts\python.exe -m pip install -e ..\bridge -e ..\mcp-server[dev] -e .[dev]
```
Pin everything with `==` (copy the versions in `mcp-server/pyproject.toml`: `mcp==2.3.0 pydantic==2.14.2 anyio==4.16.0 pytest==8.4.2 hypothesis==6.170.14 jsonschema==4.26.0`). Create `spirit-map/pyproject.toml` first (task 1.1).

## Milestones (docs/parallel-plan.md)
Tue 10 Nov: explorer plus replay property tests green on the fake. Tue 17 Nov: explore, label, generate, review, runtime works end to end on `fake-insurance`; `tk4-builtins` map committed from a live run by A; golden policy matches.

## Your first prompt (paste into the agent)
```
You are Agent B of the Green Screen Seance parallel build. First run `git branch --show-current`; it must print agent/b-spirit-map, otherwise stop and tell me.
Read docs/handoff/b/START-HERE.md, docs/contracts.md (sections 1, 2, 6, 7, 10, 11), and .kiro/specs/spirit-map/* in full.
You own spirit-map/, docs/spirit-map/, .kiro/specs/spirit-map/ and docs/handoff/b/ and nothing else. Never touch the live container; use seance_mcp.fake.
Principle: the LLM names things and never decides what is safe; only a human writes key-policy.json.
Start with tasks 1 (scaffold), then 2 (policy first, with its tests and mutation checks), then 3 and 4 (graph, store, explorer on FakeApp with the Hypothesis safety properties). Commit per task (spirit-map: <task id> ...), tick tasks.md, journal surprises in docs/handoff/b/journal.md, run scripts/gate.ps1 -Only spirit-map,contracts before each push. Anything you need from another folder goes in a request file under docs/handoff/b/. Report when task 4.5 is done.
```
