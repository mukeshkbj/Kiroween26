//LODTEMP JOB (ACCT),'KICKS LODTEMP',CLASS=A,MSGCLASS=A,
//         USER=@MVS_USER@,PASSWORD=@MVS_PASSWORD@
//* Creates HERC01.KICKSSYS.V1R5M0.KIKTEMP (the KICKS temporary storage
//* queues), one of the system datasets KFIX's README member
//* says must exist before KICKS will start (task 3.6). Our own IDCAMS
//* job, modelled on the KICKS INSTLIB member (not a copy of it).
//DELDEF EXEC PGM=IDCAMS,REGION=1024K
//SYSPRINT DD SYSOUT=*
//SYSIN DD *
 DELETE HERC01.KICKSSYS.V1R5M0.KIKTEMP
 SET MAXCC = 0
 DEFINE CLUSTER                                       -
      (NAME(HERC01.KICKSSYS.V1R5M0.KIKTEMP) INDEXED  -
       VOLUMES(PUB002)                                -
       TRACKS(15 15)                                  -
       SHAREOPTIONS(1 3) UNIQUE                       -
       RECORDSIZE(19 32767) SPANNED                   -
       KEYS(18 0)                                     -
      )                                               -
     DATA ( NAME(HERC01.KICKSSYS.V1R5M0.KIKTEMP.DATA)) -
    INDEX ( NAME(HERC01.KICKSSYS.V1R5M0.KIKTEMP.INDEX))
/*
//*
//* LOAD A DUMMY RECORD
//*
//LOAD   EXEC PGM=IDCAMS
//SYSPRINT DD SYSOUT=*
//SYSIN    DD *
 REPRO INFILE(DUMYDATA) OUTDATASET(HERC01.KICKSSYS.V1R5M0.KIKTEMP)
/*
//DUMYDATA DD *
99999999999999999999999999999999999
/*
//
