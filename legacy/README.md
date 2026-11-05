# Green Screen Seance - legacy system

This is the legacy half of the demo: a real IBM mainframe environment plus the
Seance Insurance demo app the agent drives.

## What is REAL mainframe vs what is a stand-in (read this first)

We are honest about this because the whole project is about driving a *real*
legacy system, not faking one.

**Real, running on the live TK4- (MVS 3.8j on Hercules, in Docker):**
- The **COBOL business logic** `SEANCSVC` (`src/cobol/SEANCSVC.cob`), compiled
  with the stock OS/VS COBOL compiler via the proven COBUCLG route and linked
  into `HERC01.SEANCE.LOAD`. It does the actual policy lookup, list and update
  against the policy master file `HERC01.SEANCE.POLICY`.
- **KICKS** (a CICS-like TP monitor) is installed and **starts with its banner**
  over 3270 (`EXEC 'HERC01.KICKSSYS.V1R5M0.CLIST(KICKS)'`).
- All the **TK4- built-in screens** the demo also shows (welcome, TSO logon,
  the `IKJ56420I` rejection, RFE, etc.).

**Stand-in (the one thing that is not the mainframe):**
- The **3270 presentation layer** for the five insurance screens. It is a small,
  clearly labelled Python TN3270 server (`standin/`) that paints the screens and
  calls `SEANCSVC` on TK4- for every operation.

### Why the presentation is a stand-in
We first built the five screens as a native **KICKS** transaction (BMS maps +
command-level COBOL). The BMS maps assemble and link cleanly, and KICKS starts,
but the OS/VS COBOL compiler (`IKFCBL00`) **abends S0C4 on KICKS-preprocessed
source in this TK4- build** - reproducibly, even for a trivial program, while
the same compiler compiles plain (non-KICKS) COBOL fine. We time-boxed it (see
`docs/handoff/a/journal.md`, go/no-go on 2026-11-05) and took the stand-in so
the demo milestone is safe. The KICKS attempt is kept under `src/kicks/` as a
stretch (`SMENMAP` is installed in KIKRPL; finishing it is task 3.5-followup:
run the install interactively through our own MCP server).

The stand-in paints the exact screens, field names, keys and `VOLATILE_REGIONS`
of `docs/contracts.md` section 10, so spirit-map, the agent and the UI cannot
tell it from a native KICKS app.

## Run it

Prerequisites: Docker, and (for the stand-in / checks) Python 3.12 with the
`bridge` and `mcp-server` packages installed into `mcp-server/.venv`.

```
# 1. Start the mainframe (first cold IPL ~1 min to a reachable 3270 port)
docker compose -f legacy/docker-compose.yml up -d        # container: gss-legacy

# 2. One-time install on the mainframe (idempotent; see "Install" below)
#    - build the COBOL business logic into HERC01.SEANCE.LOAD
powershell -File legacy/scripts/submit-jcl.ps1 -Jcl legacy/src/jcl/mkpds.jcl
#    (upload SEANCSVC source, then:)
powershell -File legacy/scripts/submit-jcl.ps1 -Jcl legacy/src/jcl/build-seancsvc.jcl
#    - seed the 8 demo policies
powershell -File legacy/reset-data.ps1

# 3. Start the stand-in (serves TN3270 on STANDIN_PORT, default 3271)
#    It reads MVS_USER / MVS_PASSWORD from the environment or legacy/.env.
$env:PYTHONPATH="legacy/standin"; python -m seance_standin

# 4. Point the bridge / s3270 (and the rest of the stack) at the stand-in port.
```

Cold-start time: the TK4- container reaches a reachable 3270 port in about one
minute from a cold `up`. The stand-in starts instantly. A lookup/list/update
round-trips to the mainframe in ~1-3 s (one batch job per operation).

## The five screens (contract section 10)

| Screen (tranid) | Purpose | Keys |
|---|---|---|
| Main menu (SMEN)  | pick 1 enquiry / 2 list / 3 update | ENTER selects, CLEAR exits |
| Enquiry (SENQ)    | look up one policy by number        | ENTER looks up, PF3 back |
| List (SLST)       | list the 8 policies                 | PF7/PF8 page, PF3 back |
| Update (SUPD)     | change status (A/L/C) and/or premium| ENTER -> confirm, PF3 back |
| Confirm (SCNF)    | review old vs new, then commit      | ENTER commits, PF3 cancels |

Walkthrough: from the menu type `1`, ENTER; on enquiry type `P0000003`, ENTER ->
A. ROSE / ACTIVE / 250.00. CLEAR to the menu; `2`, ENTER -> the 8 policies.
CLEAR; `3`, ENTER; `P0000003`, tab, `L`, ENTER -> the confirm screen shows
STATUS A -> L; ENTER commits (the only data change in the app) and the menu says
POLICY UPDATED. Enquiry again shows the new value with today's date.

Seed data: 8 policies `P0000001`..`P0000008` (see `src/jcl/seed-policies.jcl`).

## Install (what runs on the mainframe)

| Artefact | Where |
|---|---|
| COBOL business logic source | `src/cobol/SEANCSVC.cob` |
| build (compile+link) job     | `src/jcl/build-seancsvc.jcl` -> `HERC01.SEANCE.LOAD(SEANCSVC)` |
| seed / reset the policy file | `src/jcl/seed-policies.jcl` -> `HERC01.SEANCE.POLICY` |
| run one request (smoke test) | `src/jcl/run-seancsvc.jcl` |
| KICKS install (stretch)      | `src/jcl/kicks-*.jcl`, `src/kicks/` |

Source members are uploaded with `scripts/submit-member.ps1` (IEBUPDTE) and jobs
submitted with `scripts/submit-jcl.ps1` (Hercules card reader on device 000C).

## Reset and health check

- `legacy/reset-data.ps1` (or `.sh`) restores the 8 seed policies. Run before
  each demo so the path works three times in a row.
- `legacy/healthcheck.ps1` / `legacy/healthcheck.py` connects through the bridge,
  checks the menu is readable with the keyboard unlocked, and confirms a seed
  lookup returns live COBOL data. Exit 0 = ready.
- `legacy/scripts/demo_path.py` runs the whole flow three times in a row.

## Credentials and safety

- Credentials live in `legacy/.env` (gitignored); `legacy/.env.example` is the
  template. `MVS_USER` / `MVS_PASSWORD` are the TK4- batch credentials. **No
  password is ever committed, logged, or shown on a screen or in a capture.**
- Only Agent A touches the live `gss-legacy` container (contracts section 2.1).
- The update path is the app's only data change and goes through the explicit
  Confirm screen (mainframe-safety: read-only by default, confirm before commit).

## Captures

`captures/seance-insurance/capture.json` (the 5 screens) and
`captures/tk4-builtins/capture.json` (real TK4- welcome + `IKJ56420I` rejection)
are `gss.capture/1` files for Agent B, produced live through the real bridge.
See `docs/handoff/a/response-b-captures.md`.

## Fallback path if the mainframe is unavailable

If TK4- cannot be started, `mcp-server`'s `seance_mcp.fake.fake_insurance()`
serves the identical five screens in-process (no mainframe), which is what
agents B, C and D develop against anyway. The stand-in plus the fake share one
contract, so the UI and agent behave the same either way.
