# legacy-environment — Tasks

Tasks are ordered so the go/no-go de-risks as early as possible: COBOL compile first (done), then KICKS setup (the main risk), then the app, then the spirit-map second target, then the fallback.

## 1. Container baseline
- [x] 1.1 `legacy/docker-compose.yml`: `legacy` service from a custom `gss-legacy` image; ports from `.env` (defaults 3270/8038).
- [ ] 1.2 `legacy/Dockerfile`: extend `skunklabz/tk4-hercules`; layer in our app source + setup scripts (not KICKS).
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
- [ ] 3.4 Upload the KICKS XMI via card reader (`devinit 000c ... ebcdic`) and run the unpack jobstream (V1R5M0 member).
- [ ] 3.5 Run KFIX customization (HLQ=KICKS), create system datasets (LODINTRA, LODTEMP). Increase DYNAMNBR in IKJACCNT.
- [ ] 3.6 Verify KICKS starts: `EXEC 'KICKS.KICKSSYS.V1R5M0.CLIST(KICKS)'` shows the banner screen.

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
