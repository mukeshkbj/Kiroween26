# Request: Agent D to Integrator, merge `agent/d-seance-agent` (7.3: real model)

**From:** Agent D. **Branch:** `agent/d-seance-agent`, with `main` merged (`e89032c`). Builds on merge request d-3
(still open with you); land them together, with B and C as planned.

## What lands

| Commit | What |
|---|---|
| `65de78e` | 7.3: three `llm`-marked real-provider tests (lookup; prompt injection, now with proof that the hostile text reached the model; commit expiry). Providers get `aclose()`, which the hub calls on shutdown. `agent/scripts/real_conversation.py`. The recorded real-model streams. |
| `4592ccf` | no literal key prefix anywhere in the repo, so a `git grep` for the Anthropic key prefix only ever finds a real key |
| this commit | the conversation stream, `real-model-notes.md`, 7.3 ticked, journal |

Results and the real-vs-scripted comparison: `docs/handoff/d/real-model-notes.md`. In short:

- Every safety property held with the real model.
- It refused the injected instruction and said why.
- It did not retry an expired change.
- The approved update committed exactly once.

## Secrets

- `agent/.env` is gitignored, untracked, and was never opened, printed or copied by D.
- A repo-wide `git grep` for the Anthropic key prefix (tracked files): 0 hits. Each recorded stream is checked for key-like strings and for the configured key before it is written.
- Every test and script log was scanned before any of it was shown.
- The key is a `SecretStr`; providers log only exception class names.

## Checks

- Default suite (no network): 121 passed, 1 skipped (live, A only), 3 deselected (`llm`). mypy clean.
- `llm` suite: 3 passed with the real model. It stays deselected by default and skips without credentials, so CI needs no key.
- `scripts/gate.ps1 -Only agent,contracts,ownership -Mypy`: agent pass on the fixed seed and a random one (121 passed), mypy pass. `contracts` is skipped in my worktree (no `mcp-server/.venv`); I changed no contract files.
- **Ownership: the gate reports FAIL, and it is a false positive.** `check-ownership.ps1` compares against the local `main` ref (`91adbbb`), which is your worktree's, and older than `origin/main` (`c128a90`). Your own commit `c128a90` ("kiro: cut per-message credit use") reached my branch through `git merge origin/main`, and is then counted as mine (six `.kiro/steering|settings|hooks` files). With `-Base origin/main` the check passes: 43 files, all in D's paths. I did not touch your `main` ref or the script. A suggestion: default `-Base` to `origin/main`, or fetch and compare `origin/main` in the gate.

## For C and B (from the real-model run, no action needed for the merge)

- **C:** the real model writes no text before a tool call, so `confirmation_required.agent_summary` is empty. Show "the agent gave no description" rather than an empty block. It also answers in markdown (lists, a table), which arrives raw in `assistant_message`.
- **B:** after `list_policies` the model said "up to 3 pages". It read the `page` maximum in the tool's input schema as a fact about the data, though the fake has one page. Schema limits are read as claims.

No contract change. No new dependencies.
