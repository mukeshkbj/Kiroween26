# Request: Agent D to Integrator, merge `agent/d-seance-agent` again (e2e findings D-1 to D-5)

**From:** Agent D. **Branch:** `agent/d-seance-agent`, tip `bfd5ecf` or later. It already contains `main` at `dfa4990`,
so the merge is a fast-forward of D's paths. Details per finding: `response-integrator-e2e-findings.md`.

## Ask

Merge into `integration`, then `main`.

## What lands

| Commit | What |
|---|---|
| `1f60953`, `66be441` | 2026-11-06 fixes found against C's client (per-session ids, baseline for late clients, reload keeps control, demo phrasing, error summaries). Not on `main` yet. They cover D-1 and most of D-2. |
| `b34e180` | D-2 to D-5: failures never "ok", contracts 4.3 screen/focus order, `apps.json` equal to contracts section 8, person-facing text after a decision |
| `bfd5ecf` | `field_focus.step` keeps counting through the confirmation |
| `13e2bb5` | the 2026-11-07 real-model injection transcript (evidence for 7.3; 7.3 itself stays parked) |
| `b9769c9` and earlier | the 8.2 live check, the README run guide, the request to B |

## Done-when (from the request), checked

- D-1 and D-2 have tests: `agent/tests/test_e2e_findings.py`.
- D-3 passes the stricter `check_stream`: the rules are in `agent/tests/_stream.py`, ready to copy into
  `seance_mcp.contracts.check`. All seven committed transcripts already pass them.
- D-4 matches contracts section 8; the test parses `docs/contracts.md`.
- `scripts/gate.ps1 -Only agent,contracts,ownership -Mypy`: ownership, agent and mypy pass. `contracts` is skipped in my
  worktree for lack of `mcp-server/.venv`. Its two commands, run with the agent venv: `generate --check` exit 0,
  `check` exit 0.

No contract text change is needed. No new dependencies.
