# legacy-environment — Tasks

Tasks are ordered so the go/no-go de-risks as early as possible: COBOL compile first (done), then KICKS setup (the main risk), then the app, then the spirit-map second target, then the fallback.

## 1. Container baseline
- [x] 1.1 `legacy/docker-compose.yml`: `legacy` service from a custom `gss-legacy` image; ports from `.env` (defaults 3270/8038).
- [x] 1.2 `legacy/Dockerfile`: extend `skunklabz/tk4-hercules`; layer in our app source + setup scripts (not KICKS).
- [x] 1.3 `.env.example` with `TN3270_HOST`, `TN3270_PORT`, `HERCULES_CONSOLE_PORT`, `MVS_USER`, `MVS_PASSWORD`. Gitignore `.env`.
- [x] 1.4 Smoke test: `docker-compose up` reaches a 3270 port that responds (TCP open). Cold-IPL time noted.

## 2. Validate the COBOL compile (DONE — key risk cleared)
- [x] 2.1 Write a hello-world COBOL program + COBUCLG compile/link/go JCL.
- [x] 2.2 Get the compile job to run via `devinit 000c` card-reader submission (Hercules console on 8038). Compiler is `IKFCBL00` (OS/VS COBOL).
- [x] 2.3 Verify the load module executes: DISPLAY 'HELLO FROM COBOL', RC=0000.

## 3. KICKS setup script (A — primary, main risk)
- [ ] 3.1 `legacy/setup-kicks`: download KICKS archive from `github.com/moshix/kicks`, extract `kicks-tso-v1r5m0`.
- [ ] 3.2 Create a 3350 DASD volume with `dasdinit`; attach to running Hercules via HTTP console (`attach 351 3350 ...`).
- [ ] 3.3 Submit ICKDSF JCL to init the volume, then IDCAMS JCL for the user catalog (UCKICKS0) + KICKS alias.
- [x] 3.4a Upload the KICKS XMI and RECV370 it: `devinit 10c kicks.xmi ebcdic` mounts it on the 10C reader, `legacy/src/jcl/recv370-kicks.jcl` receives it into `HERC01.KICKS.V1R5M0.INSTALL` (28 members, RC=0000, 106,474 records read). Run via `legacy/scripts/submit-jcl.ps1`.
- [x] 3.4b Unpack: `legacy/src/jcl/kicks-unpack.jcl` (our own job, modelled on the KICKS-supplied one) RECV370s all 26 members into `HERC01.KICKS.V1R5M0.*` and `HERC01.KICKSSYS.V1R5M0.*`, every step RC=0000.
- [x] 3.5 Run KFIX customization (HLQ=HERC01, since the unpack used the user id), create system datasets (LODINTRA, LODTEMP). Increase DYNAMNBR in IKJACCNT. **BLOCKED after 2 attempts (time-box).**
  - Attempt 1: KFIX in batch TSO with `YES` stacked in SYSTSIN. In batch `&SYSUID` is blank and `READ` gets no input, so the prompt loops forever (1M lines, cancelled, S222).
  - Attempt 2: copy KFIX to `HERC01.KFIX.CLIST`, patch it with TSO EDIT, then run it. Both `CHANGE` commands said `TEXT NOT FOUND`, so it looped again (`TIME=1` stopped it, S322). Root cause: the CLIST has line numbers like `00180000`, and my range `1 99999` only covered the first nine lines.
  - Attempt 3 (range `1 99999999`): the patch took effect (HLQ 1 = HERC01 selected, "LOOKS LIKE TURNKEY MVS"). It then failed with RC=12: `IKJ56228I DATA SET KICKS.V1R5M0.CB2 NOT IN CATALOG`. KFIX uses unqualified dataset names and relies on the TSO PROFILE PREFIX, which is blank in batch. Likely next fix: add `PROFILE PREFIX(HERC01)` before the EXEC. **KICKS parked here (time-box), per review.**
  - Attempt 4 (2026-11-04): PROFILE PREFIX(HERC01) before EXEC fixed the prefix. The real remaining cause of NOT IN CATALOG was my own typo: the HCB2 step in kicks-unpack.jcl was commented out (//*//HCB2), so HERC01.KICKS.V1R5M0.CB2 never existed. Received it with kicks-unpack-cb2.jcl; KFIX then ended RC=0000. KIKINTRA and KIKTEMP created by kicks-lodintra.jcl / kicks-lodtemp.jcl. IKJACCNT DYNAMNBR change was not needed to start KICKS.
- [ ] 3.5-followup **Dogfooding:** once mcp-server works, run KFIX interactively over 3270 *through our own bridge / MCP server* (log on to TSO, `PROFILE PREFIX(HERC01)`, `EXEC KFIX`, answer the prompt). A good write-up story: our own tool finishing the install of the legacy app it will later drive.
- [x] 3.5-gate **Go/no-go decided 2026-11-05 (user).** KICKS starts and the banner shows (3.6 done), but OS/VS COBOL (IKFCBL00) abends S0C4 on the KICKS-preprocessed output in both KICKS compile procs, while BMS assembly works and plain COBUCLG works. Decision: **NO-GO on the full KICKS COBOL path**; take the fallback (3.5-fallback). KICKS mapset work kept under `legacy/src/kicks/` as a stretch. One time-boxed (<=1h) KICKS COBOL retry with raised REGION/SIZE/BUF is allowed only after the fallback is done and committed.
- [ ] 3.5-fallback **(only on no-go)** The five insurance screens (contract: `docs/contracts.md` section 10) are served by a **clearly labelled Python TN3270 stand-in** in docker (`legacy/standin/`), whose business logic (lookup, list, update) calls a **COBOL program running on TK4-** (compiled via the proven COBUCLG route, results returned to the stand-in). The demo also shows the **real TK4- built-in screens live**. README must state which parts are real mainframe and which is the stand-in. Same screens, field names and key behaviour as the contract, so spirit-map, the agent and the UI work unchanged.
- [x] 3.6 Verify KICKS starts (2026-11-04: banner "KSGM ... KICKS for TSO V1R5M0" shown over 3270 after TSO logon; see journal): `EXEC 'KICKS.KICKSSYS.V1R5M0.CLIST(KICKS)'` shows the banner screen.

## 4. Séance Insurance app — KICKS transactions (A)
- [ ] 4.1 COBOL copybook: policy record layout (POLNO, HOLDER, STATUS, PREMIUM, UPDDATE).
- [ ] 4.2 COBOL programs with EXEC CICS (KICKS) commands: SEANCEM (menu), SEANCEQ (enquiry), SEANCLS (list), SEANCEU (update), SEANCEC (confirm).
- [ ] 4.3 BMS mapsets: SMENMAP, SENQMAP, SLSTMAP, SUPDMAP, SCNFMAP (5 maps with protected + unprotected fields).
- [ ] 4.4 Install JCL: compile COBOL programs, assemble BMS mapsets, define + load seed policy file (8 records).
- [ ] 4.5 KICKS control table updates: assemble PPT (programs + mapsets), PCT (transaction IDs), FCT (policy file).
- [ ] 4.6 Verify all 5 screens reachable from a 3270 client / the bridge after running setup-kicks.

## 5. Built-in screens — spirit-map second target (B)
- [ ] 5.1 Document the TK4- built-in full-screen tools available for spirit-map exploration (RFE, TSO logon, utility screens).
- [ ] 5.2 Verify the bridge can read the TSO logon screen (structured fields present) — this is the screen-bridge integration test (task 6.2).

## 6. COBOL line-mode fallback (C)
- [ ] 6.1 COBOL program: line-mode policy enquiry (ACCEPT/DISPLAY, no BMS, no KICKS).
- [ ] 6.2 Compile via COBUCLG, verify it runs and produces output under TSO.
- [ ] 6.3 Document as the fallback path in `legacy/README.md`.

## 7. Health check + reset
- [ ] 7.1 `legacy/healthcheck.sh`: poll 3270 until a readable screen + keyboard unlocked; timeout ~6 min; clear error.
- [ ] 7.2 `legacy/reset-data.sh`: re-run the seed-load JCL via the console to restore known data.
- [ ] 7.3 Run the demo path (menu → enquiry → list → update → confirm) three times after reset.

## 8. Docs
- [ ] 8.1 `legacy/README.md`: how to run, KICKS setup instructions, cold-start time, the 5-screen walkthrough, demo credentials (from `.env`), fallback instructions.
