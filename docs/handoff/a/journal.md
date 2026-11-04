# Agent A journal

- 2026-11-04 Task 1.2 done: legacy/Dockerfile extends skunklabz/tk4-hercules and copies src/jcl to /tk4-/jcl; compose now builds it. The live container was NOT recreated (its DASD holds the KICKS datasets); only `docker build` was run.
- 2026-11-04 Surprise: KICKS "attempt 3" failure (CB2 not in catalog) was my own typo, `//*//HCB2` in kicks-unpack.jcl commented the step out. Not a KFIX or prefix problem alone; PROFILE PREFIX(HERC01) was also needed.
- 2026-11-04 Surprise: abruptly disconnecting s3270 leaves the TSO user logged on ("USERID HERC01 IN USE"). Cancel with Hercules console `/c u=herc01` and wait ~15 s. legacy/scripts/s3270_drive.py is the small driver used (password read from legacy/.env, never printed).
- 2026-11-04 Task 3.6: from TSO READY, `PROFILE PREFIX(HERC01)` then `EXEC 'HERC01.KICKSSYS.V1R5M0.CLIST(KICKS)'` starts KICKS; after a few Enters the KSGM banner shows ("KICKS for TSO V1R5M0", "Press PF1 for help, CLEAR to continue"). Logon sequence: Enter, userid, password, Enter, Enter, X at the menu, then READY.
- 2026-11-04 KICKS go/no-go: technically GO so far (KICKS starts). Formal decision is due Sun 8 Nov; still open until KICKS transactions (task 4) are proven. Waiting for the user at the gate.
