//RUNSVC  JOB (ACCT),'RUN SEANCSVC',CLASS=A,MSGCLASS=A,REGION=2048K,
//         USER=@MVS_USER@,PASSWORD=@MVS_PASSWORD@
//* Run the pre-linked SEANCSVC business logic once. The Python stand-in
//* (legacy/standin/) submits a job like this per request, filling SYSIN
//* with the request card and reading the pipe-delimited response from
//* SYSOUT. This copy is a manual smoke test (lookup P0000003).
//RUN     EXEC PGM=SEANCSVC
//STEPLIB  DD DSN=HERC01.SEANCE.LOAD,DISP=SHR
//POLIN    DD DSN=HERC01.SEANCE.POLICY,DISP=SHR
//POLOUT   DD DUMMY
//SYSOUT   DD SYSOUT=*
//SYSIN    DD *
L P0000003
/*
//
