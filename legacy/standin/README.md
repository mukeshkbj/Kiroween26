# Seance Insurance TN3270 stand-in

**This is a stand-in, not the KICKS transaction.** It is a small Python TN3270
server that paints the five Seance Insurance screens (contracts section 10) and
**delegates every lookup / list / update to the real COBOL program `SEANCSVC`
running on the live TK4- mainframe** (compiled with the proven COBUCLG route;
see `legacy/src/cobol/SEANCSVC.cob`).

Why it exists: KICKS starts and shows its banner on TK4- (task 3.6), but the
OS/VS COBOL compiler (`IKFCBL00`) abends S0C4 on KICKS-preprocessed source in
this build, so the BMS/KICKS transaction path could not be finished in time
(see `docs/handoff/a/journal.md`, go/no-go on 2026-11-05). The business logic is
still genuine mainframe COBOL; only the 3270 presentation layer is this stand-in.

## What is real vs stand-in
- **Real mainframe (live TK4- on Hercules):** the COBOL business logic
  (`SEANCSVC`), the policy master file `HERC01.SEANCE.POLICY`, the KICKS banner,
  and all the TK4- built-in screens the demo also shows.
- **Stand-in (this package):** the TN3270 server that renders the five insurance
  screens and runs `SEANCSVC` per request via the Hercules card reader.

The screens, field names, keys and `VOLATILE_REGIONS` are identical to
contracts section 10 and `seance_mcp.fake`, so spirit-map, the agent and the UI
treat the stand-in and a future real KICKS app the same way.

## Run
```
python -m seance_standin            # serves TN3270 on STANDIN_PORT (default 3271)
```
The bridge / s3270 connects to it exactly as to a real host.

Backend failures never leave the terminal waiting. Every Docker call is bounded
(`STANDIN_DOCKER_TIMEOUT_S`, default 20 s). A failed read shows `MAINFRAME NOT
AVAILABLE - TRY AGAIN LATER`. A failed commit is ambiguous (the update job may
have run), so it shows `UPDATE OUTCOME UNKNOWN - CHECK THE POLICY, DO NOT
RETRY`, drops the pending change and never resubmits it. See
`legacy/README.md` for the full demo run, reset and health check.
