//KFIXJOB JOB (ACCT),'KICKS KFIX',CLASS=A,MSGCLASS=A,REGION=4096K,
//         USER=@MVS_USER@,PASSWORD=@MVS_PASSWORD@
//*
//* The KICKS customization CLIST (KFIX) prompts with READ for the HLQ, and in
//* batch TSO that READ never receives stacked input (it loops forever on a
//* blank answer; &SYSUID is blank too). So: copy the CLIST, patch the copy to
//* fix the HLQ to HERC01 and answer the prompt, then run the copy.
//* The patched copy lives only on the mainframe, never in the repo.
//DEL     EXEC PGM=IEFBR14
//D       DD DSN=HERC01.KFIX.CLIST,DISP=(MOD,DELETE),UNIT=SYSDA,
//            SPACE=(TRK,1)
//COPY    EXEC PGM=IEBGENER
//SYSPRINT DD DUMMY
//SYSIN   DD DUMMY
//SYSUT1  DD DSN=HERC01.KICKSSYS.V1R5M0.CLIST(KFIX),DISP=SHR
//SYSUT2  DD DSN=HERC01.KFIX.CLIST,DISP=(NEW,CATLG,DELETE),
//            UNIT=SYSDA,SPACE=(TRK,(5,5)),
//            DCB=(RECFM=FB,LRECL=80,BLKSIZE=3120)
//KFIX    EXEC PGM=IKJEFT01,DYNAMNBR=64,TIME=1
//SYSTSPRT DD SYSOUT=*
//SYSPRINT DD SYSOUT=*
//SYSTSIN DD *
 EDIT 'HERC01.KFIX.CLIST' CLIST OLD
 CHANGE 1 99999999 'SET &UU1 = &SYSUID' 'SET &UU1 = HERC01' ALL
 CHANGE 1 99999999 'READ &YN' 'SET &YN = YES' ALL
 SAVE
 END
 PROFILE PREFIX(HERC01)
 EXEC 'HERC01.KFIX.CLIST'
/*
//
