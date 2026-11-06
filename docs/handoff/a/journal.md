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

## 2026-11-05 Fallback demo app DONE (Tue 10 Nov milestone safe)

- Real COBOL `SEANCSVC` compiles+links on TK4- via COBUCLG (COB RC=0004, LKED
  RC=0000) into `HERC01.SEANCE.LOAD`. Proven: lookup returns
  `OK|R|P0000003|A. ROSE|ACTIVE|250.00|2026-10-21`; list returns all 8; update
  rewrites the master and persists. This confirms the S0C4 was specific to the
  KICKS preprocessor path (plain COBOL is fine).
  - Surprise: the KICKS program name `SEANCESVC` was 9 chars -> `IEF642I
    EXCESSIVE PARAMETER LENGTH` (member names max 8). Renamed to `SEANCSVC`.
  - Surprise: a JCL card exactly 72 cols ending in `,` puts the comma in the
    continuation column -> `IEF618I`. Keep continued operands short.
- `legacy/standin/` Python TN3270 server paints the 5 screens to contract 10
  geometry and calls `SEANCSVC` per request via the card reader. 15 unit tests
  pass; proven end-to-end over real s3270 (menu/enquiry/list/update+commit).
  - Surprise: the bridge sends `PF3`, but s3270 wants `PF(3)` — PF/PA presses
    fail live. Filed `request-integrator-bridge-pf-keys.md`; capture/demo tools
    issue `PF(n)` directly meanwhile.
- Captures: `seance-insurance` (5 screens, loads via from_capture) and
  `tk4-builtins` (real welcome + `IKJ56420I` for XYZZY). Known: from_capture
  rejects the welcome's top-left field — filed to the integrator; B informed.
- `volatile-regions.txt` equals the fake's DEMO_VOLATILE_REGIONS (36 spans).
- reset-data, healthcheck (exit 0), and demo_path 3x in a row (ALL RUNS OK).
- README is explicit about real (TK4-, KICKS banner, COBOL logic) vs stand-in
  (the 3270 presentation of the 5 screens only).

Milestone deliverables for B/C/D are all in place. Remaining per the user: ONE
time-boxed (<=1h) retry of the KICKS COBOL compile with raised REGION/SIZE/BUF.

## 2026-11-05 Authorized KICKS COBOL retry with raised storage — still S0C4 (closed)

Ran the one allowed (<=1h) retry: inlined the KICKS single-pass compile with
REGION=8192K on both the job and the COB2 step and PARM SIZE=4096K/BUF=2048K on
IKFCBL00 (`src/jcl/cob-seancem-big.jcl`, job 125). KIKPPCOB RC=0000, then
**COB2 IKFCBL00 abends S0C4** exactly as before. Raising storage did not help,
so the S0C4 is a genuine IKFCBL00 limitation on KICKS-preprocessed source in this
TK4- build, not a storage shortfall. KICKS COBOL path is closed; the stand-in +
real COBOL (COBUCLG) fallback stands and the demo milestone is met. `src/kicks/`
kept as a documented stretch (the SMENMAP BMS mapset does assemble+link).
(Two JCL 72-column traps hit again on the way: a quoted PARM whose closing
apostrophe fell in column 72 -> IEF629I; shortened the PARM.)

## 2026-11-06 Docker restart, health check, B's live tk4-builtins run

- Docker Desktop had stopped overnight. After the integrator restarted it,
  `gss-legacy` IPLed, and the health check passed first try (`P0000001 -> J.
  MARLOWE` from COBOL). The policy data and the SEANCSVC load module survived
  the restart. I restarted the stand-in.
- Merged main (spirit-map, contracts with ScreenOut.volatile).
- Surprise: my first tk4-builtins capture had grabbed the **Hercules device
  banner**, not the VTAM welcome. TK4- paints the banner first, and the bridge's
  "input field + stable" wait accepted it. The capture now waits for a row 0
  starting with `Terminal`. Clock volatile is now TK4_CLOCK_REGIONS (0,64,16;1,64,16).
- B's explorer, live (7.3), three attempts:
  1. Bridge as shipped: halted `session_lost` on the first PA1. The cause is the
     PF/PA key-form bug (bridge sends `PA1`, s3270 wants `PA(1)`; nothing is
     sent).
  2. `legacy/scripts/live_explore.py` (PF/PA form fix only): reaches 7 screens,
     then **hangs forever** on the next AID after CLEAR on a blank VTAM screen.
     A faulthandler watchdog showed `Session._exec` blocked in readline: the key
     was sent and the host never answered, so this is an ambiguous ack with no
     timeout. Filed `request-integrator-bridge-aid-blocks.md`.
  3. Same, plus a bounded pre-press `Wait(Unlock)`: the same hang, which
     confirmed the keyboard was unlocked and the AID itself was the problem.
  Partial map (7 nodes, 12 edges, 17 frontier) handed to B in
  `docs/handoff/a/live-runs/tk4-builtins/` with a response file.
- Surprise: the welcome's `screen_id` changes per connection because row 0
  shows the VTAM terminal `CUU0C0`/`CUU0C1`. Suggested to B: volatile `[0,11,6]`.
- My mistake: the tool returned before a background explorer exited, and I
  started a second one. For a short time two sessions overlapped on separate
  VTAM terminals. I discarded those artefacts. I now check for a live explorer
  process before starting one, and the runner has a watchdog.
- Safety check of every audit: only read-only keys were sent (CLEAR, PA1-3,
  PF13-14). ENTER stayed `denied_commit`, and `Logon ===>` stayed
  `unsafe_field`. No password or real userid appears in any artefact.
