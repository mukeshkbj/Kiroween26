//LCHERC  JOB (ACCT),'LISTCAT HERC01',CLASS=A,MSGCLASS=A,
//         USER=@MVS_USER@,PASSWORD=@MVS_PASSWORD@
//* Catalog fingerprint for the volume migration: every HERC01.* dataset
//* (demo app + KICKS). Run before and after; the name lists must match.
//S1      EXEC PGM=IDCAMS
//SYSPRINT DD SYSOUT=*
//SYSIN    DD *
  LISTCAT LEVEL(HERC01) NAME
/*
//
