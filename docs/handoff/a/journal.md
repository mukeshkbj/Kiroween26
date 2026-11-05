# Agent A journal

- 2026-11-04 Task 1.2 done: legacy/Dockerfile extends skunklabz/tk4-hercules and copies src/jcl to /tk4-/jcl; compose now builds it. The live container was NOT recreated (its DASD holds the KICKS datasets); only `docker build` was run.
- 2026-11-04 Surprise: KICKS "attempt 3" failure (CB2 not in catalog) was my own typo, `//*//HCB2` in kicks-unpack.jcl commented the step out. Not a KFIX or prefix problem alone; PROFILE PREFIX(HERC01) was also needed.
- 2026-11-04 Surprise: abruptly disconnecting s3270 leaves the TSO user logged on ("USERID HERC01 IN USE"). Cancel with Hercules console `/c u=herc01` and wait ~15 s. legacy/scripts/s3270_drive.py is the small driver used (password read from legacy/.env, never printed).
- 2026-11-04 Task 3.6: from TSO READY, `PROFILE PREFIX(HERC01)` then `EXEC 'HERC01.KICKSSYS.V1R5M0.CLIST(KICKS)'` starts KICKS; after a few Enters the KSGM banner shows ("KICKS for TSO V1R5M0", "Press PF1 for help, CLEAR to continue"). Logon sequence: Enter, userid, password, Enter, Enter, X at the menu, then READY.
- 2026-11-04 KICKS go/no-go: technically GO so far (KICKS starts). Formal decision is due Sun 8 Nov; still open until KICKS transactions (task 4) are proven. Waiting for the user at the gate.

## 2026-11-05 KICKS COBOL/BMS spike (task 4) — BMS works, COBOL compiler abends

Decision: GO taken (user said continue). Spiked the SMEN menu transaction end to end.

What works:
- **BMS assembly works.** `legacy/src/jcl/asm-smenmap.jcl` runs the KICKS `KIKMAPS`
  proc on `SMENMAP.bms`: ASM (IFOX00) RC=0000, LINKMAP (IEWL) RC=0000, so the
  SMENMAP mapset is a load module in KIKRPL, and the COBOL DSECT copybook
  `SMENMAP` was generated into COBCOPY with the exact field names the program
  uses (SMENMI/SMENMO, OPTIONI/OPTIONO, MSGI/MSGO).
- Source upload path works: `legacy/scripts/submit-member.ps1` adds a PDS member
  via IEBUPDTE (guards source to <=72 cols). SMENMAP and SEANCEM uploaded clean.
- Baseline COBOL compile (plain COBUCLG, task 2.3) still works.

What does NOT work (the blocker):
- **OS/VS COBOL (IKFCBL00) abends S0C4** on the KICKS-preprocessed output, in
  both KICKS compile procs:
    - `K2KCOBCL` (two-pass): abend in COB1 (the DMAP-only pass).
    - `KIKCOBCL` (single-pass): abend in COB2.
  KIKPPCOB (the KICKS preprocessor) itself runs RC=0000 each time.
- It is NOT my source: a trivial program (`DISPLAY`/`STOP RUN`, no EXEC KICKS,
  no copybooks) run through the same proc also S0C4s. Yet the shipped Murach
  sample `INVMENU` passes COB1 cleanly (RC=12 — ordinary diagnostics, no abend).
  So IKFCBL00 crashes on *our* submissions through these procs but compiles a
  resident member. The compiler abends before producing any IKF listing, which
  points at a storage/DCB setup issue in the proc as driven from the card reader
  on this TK4- build, not at the COBOL text.
- Time-boxed per START-HERE after reproducing the abend many times (jobs 55-72).

Recommendation to the user (go/no-go): **No-go on the full KICKS COBOL path.**
Take the START-HERE fallback: the five insurance screens are served by a clearly
labelled Python TN3270 stand-in in `legacy/standin/`, whose business logic calls
a COBOL program compiled via the proven COBUCLG route. The demo still shows the
real TK4- built-in screens (and the real KICKS banner, task 3.6) live. Same
screens, field names, keys and VOLATILE_REGIONS as contract section 10, so
spirit-map, the agent and the UI are unaffected. BMS/mapset work is kept in
`legacy/src/kicks/` and can be revisited as a stretch (e.g. finishing KFIX-style
install interactively through our own MCP server, task 3.5-followup).

Artefacts kept: `legacy/src/kicks/map/SMENMAP.bms`, `legacy/src/kicks/cob/SEANCEM.cob`,
assemble/compile JCL, and the s3270 driver. The SMENMAP mapset is installed in
KIKRPL on the live system.
- 2026-11-05: `.kiro/specs/legacy-environment/tasks.md` changed

## 2026-11-05 Go/no-go decided: NO-GO on KICKS COBOL, take the fallback

The user approved the fallback. Plan from here (task 3.5-fallback + 4.x reshaped):
1. COBOL business logic as a real TK4- program (COBUCLG route, proven): policy
   lookup / list / update over an on-mainframe policy file. Driven as a batch
   "service" the stand-in calls, returning records to the Python stand-in.
2. `legacy/standin/`: a clearly labelled Python TN3270 server that paints the five
   insurance screens (SMEN/SENQ/SLST/SUPD/SCNF) exactly per contract section 10
   (field names, keys, 24x80 layout, VOLATILE_REGIONS), and runs the business
   logic through the COBOL program on TK4-.
3. Captures of the five real stand-in screens + the TK4- built-ins for B.
4. reset-data + healthcheck.
5. README: honest about real (TK4- live, KICKS banner, COBOL logic) vs stand-in.
Then ONE <=1h retry of the KICKS COBOL compile with raised REGION/SIZE/BUF.
