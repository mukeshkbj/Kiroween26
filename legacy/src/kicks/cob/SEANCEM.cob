       IDENTIFICATION DIVISION.
       PROGRAM-ID.  SEANCEM.
      *****************************************************************
      * Seance Insurance - main menu transaction (SMEN).            *
      * Pseudo-conversational KICKS (CICS-like) program.            *
      * First pass (no COMMAREA): send the empty menu map.          *
      * Later passes: receive the option, XCTL to the chosen        *
      * transaction's program, else redisplay with a message.       *
      * Keys (contract 10.1): ENTER selects, CLEAR exits.           *
      * KICKS commands are period-terminated (no END-EXEC).         *
      *****************************************************************
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-SEND-FLAG            PIC X VALUE '1'.
           88  SEND-ERASE          VALUE '1'.
       01  WS-COMMAREA            PIC X VALUE LOW-VALUE.
       COPY SMENMAP.
       COPY KIKAID.
       LINKAGE SECTION.
       01  DFHCOMMAREA            PIC X.
       PROCEDURE DIVISION.
       0000-MAIN.
           IF EIBCALEN = 0
               MOVE LOW-VALUE TO SMENMO
               MOVE '1' TO WS-SEND-FLAG
               PERFORM 1400-SEND-MAP
               GO TO 9000-RETURN.
           IF EIBAID = KIKCLEAR
               PERFORM 8000-EXIT.
           IF EIBAID = KIKENTER
               PERFORM 1000-PROCESS
           ELSE
               MOVE LOW-VALUE TO SMENMO
               MOVE 'PRESS ENTER OR CLEAR' TO MSGO
               MOVE '2' TO WS-SEND-FLAG
               PERFORM 1400-SEND-MAP.
           GO TO 9000-RETURN.
       1000-PROCESS.
           EXEC KICKS RECEIVE MAP('SMENM') MAPSET('SMENMAP')
                INTO(SMENMI).
           IF OPTIONI = '1'
               EXEC KICKS XCTL PROGRAM('SEANCEQ').
           IF OPTIONI = '2'
               EXEC KICKS XCTL PROGRAM('SEANCLS').
           IF OPTIONI = '3'
               EXEC KICKS XCTL PROGRAM('SEANCEU').
           MOVE LOW-VALUE TO SMENMO.
           MOVE 'INVALID OPTION' TO MSGO.
           MOVE '2' TO WS-SEND-FLAG.
           PERFORM 1400-SEND-MAP.
       1400-SEND-MAP.
           IF SEND-ERASE
               EXEC KICKS SEND MAP('SMENM') MAPSET('SMENMAP')
                    FROM(SMENMO) ERASE FREEKB CURSOR
           ELSE
               EXEC KICKS SEND MAP('SMENM') MAPSET('SMENMAP')
                    FROM(SMENMO) DATAONLY FREEKB CURSOR.
       8000-EXIT.
           EXEC KICKS SEND CONTROL ERASE FREEKB.
           EXEC KICKS RETURN.
       9000-RETURN.
           EXEC KICKS RETURN TRANSID('SMEN')
                COMMAREA(WS-COMMAREA) LENGTH(1).
           GOBACK.
