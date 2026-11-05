       IDENTIFICATION DIVISION.
       PROGRAM-ID. SEANCSVC.
      *****************************************************************
      * Seance Insurance business logic - REAL COBOL on TK4-.        *
      *                                                              *
      * This is the demo's genuine mainframe business logic. It is   *
      * compiled and run with the proven OS/VS COBOL COBUCLG route   *
      * (not KICKS, whose COBOL compile abends S0C4 on this build -  *
      * see docs/handoff/a/journal.md). The Python TN3270 stand-in   *
      * in legacy/standin/ paints the 3270 screens and calls this    *
      * program for every lookup / list / update.                    *
      *                                                              *
      * Protocol (line mode, one request per run):                   *
      *   SYSIN  : a request card (see 01 REQ-CARD below)            *
      *   POLIN  : the policy master (fixed records, 01 POL-REC)     *
      *   POLOUT : rewritten master (update only)                    *
      *   SYSOUT : one or more response lines (01 RESP-* layouts)    *
      *                                                              *
      * Operations:                                                  *
      *   L <polno>            lookup one policy                      *
      *   A                    list all policies (sorted by polno)   *
      *   U <polno> <st> <prem> update status/premium, rewrite master*
      * Status codes: A ACTIVE, L LAPSED, C CANCELLED.               *
      *****************************************************************
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT POLIN  ASSIGN TO UT-S-POLIN.
           SELECT POLOUT ASSIGN TO UT-S-POLOUT.
       DATA DIVISION.
       FILE SECTION.
       FD  POLIN
           LABEL RECORDS ARE STANDARD
           RECORDING MODE IS F
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 80 CHARACTERS.
       01  POLIN-REC.
           05  PI-POLNO     PIC X(8).
           05  PI-HOLDER    PIC X(20).
           05  PI-STATUS    PIC X(9).
           05  PI-PREMIUM   PIC X(8).
           05  PI-UPDDATE   PIC X(10).
           05  FILLER       PIC X(25).
       FD  POLOUT
           LABEL RECORDS ARE STANDARD
           RECORDING MODE IS F
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 80 CHARACTERS.
       01  POLOUT-REC       PIC X(80).
       WORKING-STORAGE SECTION.
       01  WS-EOF           PIC X VALUE 'N'.
           88  END-OF-FILE  VALUE 'Y'.
       01  WS-FOUND         PIC X VALUE 'N'.
           88  FOUND        VALUE 'Y'.
       01  REQ-CARD.
           05  RQ-OP        PIC X.
           05  FILLER       PIC X.
           05  RQ-POLNO     PIC X(8).
           05  FILLER       PIC X.
           05  RQ-STATUS    PIC X.
           05  FILLER       PIC X.
           05  RQ-PREMIUM   PIC X(8).
           05  FILLER       PIC X(60).
       01  WS-REC.
           05  WS-POLNO     PIC X(8).
           05  WS-HOLDER    PIC X(20).
           05  WS-STATUS    PIC X(9).
           05  WS-PREMIUM   PIC X(8).
           05  WS-UPDDATE   PIC X(10).
           05  FILLER       PIC X(25).
       01  WS-NEW-STATUS    PIC X(9).
       01  WS-NEW-PREMIUM   PIC X(8).
      * A response line the stand-in parses. Fields are pipe-delimited
      * so the Python side can split without guessing columns.
       01  RESP-OK.
           05  FILLER       PIC X(5) VALUE 'OK|R|'.
           05  RO-POLNO     PIC X(8).
           05  FILLER       PIC X VALUE '|'.
           05  RO-HOLDER    PIC X(20).
           05  FILLER       PIC X VALUE '|'.
           05  RO-STATUS    PIC X(9).
           05  FILLER       PIC X VALUE '|'.
           05  RO-PREMIUM   PIC X(8).
           05  FILLER       PIC X VALUE '|'.
           05  RO-UPDDATE   PIC X(10).
       01  RESP-ERR.
           05  FILLER       PIC X(3) VALUE 'ER|'.
           05  RE-TEXT      PIC X(30).
       01  RESP-END         PIC X(3) VALUE 'END'.
       PROCEDURE DIVISION.
       0000-MAIN.
           ACCEPT REQ-CARD FROM SYSIN.
           IF RQ-OP = 'L'
               PERFORM 1000-LOOKUP
           ELSE IF RQ-OP = 'A'
               PERFORM 2000-LIST
           ELSE IF RQ-OP = 'U'
               PERFORM 3000-UPDATE
           ELSE
               MOVE 'UNKNOWN OPERATION' TO RE-TEXT
               DISPLAY RESP-ERR.
           DISPLAY RESP-END.
           STOP RUN.
      *--------------------------------------------------- lookup one
       1000-LOOKUP.
           OPEN INPUT POLIN.
           MOVE 'N' TO WS-EOF.
           MOVE 'N' TO WS-FOUND.
           PERFORM 1100-READ UNTIL END-OF-FILE OR FOUND.
           IF FOUND
               PERFORM 9000-EMIT-REC
           ELSE
               MOVE 'POLICY NOT FOUND' TO RE-TEXT
               DISPLAY RESP-ERR.
           CLOSE POLIN.
       1100-READ.
           READ POLIN INTO WS-REC
               AT END MOVE 'Y' TO WS-EOF.
           IF NOT END-OF-FILE
               IF WS-POLNO = RQ-POLNO
                   MOVE 'Y' TO WS-FOUND.
      *--------------------------------------------------- list all
       2000-LIST.
           OPEN INPUT POLIN.
           MOVE 'N' TO WS-EOF.
           PERFORM 2100-READ-EMIT UNTIL END-OF-FILE.
           CLOSE POLIN.
       2100-READ-EMIT.
           READ POLIN INTO WS-REC
               AT END MOVE 'Y' TO WS-EOF.
           IF NOT END-OF-FILE
               PERFORM 9000-EMIT-REC.
      *--------------------------------------------------- update one
       3000-UPDATE.
           OPEN INPUT POLIN.
           OPEN OUTPUT POLOUT.
           MOVE 'N' TO WS-EOF.
           MOVE 'N' TO WS-FOUND.
           PERFORM 3100-COPY UNTIL END-OF-FILE.
           CLOSE POLIN POLOUT.
           IF FOUND
               PERFORM 9000-EMIT-REC
           ELSE
               MOVE 'POLICY NOT FOUND' TO RE-TEXT
               DISPLAY RESP-ERR.
       3100-COPY.
           READ POLIN INTO WS-REC
               AT END MOVE 'Y' TO WS-EOF.
           IF NOT END-OF-FILE
               PERFORM 3150-COPY-ONE.
       3150-COPY-ONE.
           IF WS-POLNO = RQ-POLNO
               PERFORM 3200-APPLY.
           WRITE POLOUT-REC FROM WS-REC.
       3200-APPLY.
           MOVE 'Y' TO WS-FOUND.
           IF RQ-STATUS = 'A'
               MOVE 'ACTIVE   ' TO WS-STATUS.
           IF RQ-STATUS = 'L'
               MOVE 'LAPSED   ' TO WS-STATUS.
           IF RQ-STATUS = 'C'
               MOVE 'CANCELLED' TO WS-STATUS.
           IF RQ-PREMIUM NOT = SPACES
               MOVE RQ-PREMIUM TO WS-PREMIUM.
           MOVE '2026-11-24' TO WS-UPDDATE.
      *--------------------------------------------------- emit helper
       9000-EMIT-REC.
           MOVE WS-POLNO   TO RO-POLNO.
           MOVE WS-HOLDER  TO RO-HOLDER.
           MOVE WS-STATUS  TO RO-STATUS.
           MOVE WS-PREMIUM TO RO-PREMIUM.
           MOVE WS-UPDDATE TO RO-UPDDATE.
           DISPLAY RESP-OK.
