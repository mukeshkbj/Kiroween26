//CLNSEAN JOB (ACCT),'CLEAN SEANCE APP',CLASS=A,MSGCLASS=A,
//         USER=@MVS_USER@,PASSWORD=@MVS_PASSWORD@
//* Delete the Seance demo app datasets so setup-app.ps1 can rebuild them
//* from source. Only HERC01.SEANCE.* (ours). MOD,DELETE is a no-op delete
//* when a dataset does not exist yet, so this is safe on a fresh system.
//DEL     EXEC PGM=IEFBR14
//D1      DD DSN=HERC01.SEANCE.COB,DISP=(MOD,DELETE),
//            UNIT=SYSDA,SPACE=(TRK,1)
//D2      DD DSN=HERC01.SEANCE.LOAD,DISP=(MOD,DELETE),
//            UNIT=SYSDA,SPACE=(TRK,1)
//D3      DD DSN=HERC01.SEANCE.TSOREQ,DISP=(MOD,DELETE),
//            UNIT=SYSDA,SPACE=(TRK,1)
//
