# Green Screen Seance legacy system: TK4- (MVS 3.8j) on Hercules, plus our
# demo app sources and setup scripts. The base image IPLs MVS on start and
# exposes 3270 (3270) and the Hercules HTTP console (8038).
#
# Note: MVS state (DASD) lives inside the container filesystem. Rebuilding or
# recreating the container loses installed datasets; re-run the setup JCL
# (legacy/scripts) afterwards.
FROM skunklabz/tk4-hercules:latest

# JCL and COBOL/BMS sources are copied to /tk4-/jcl, where the Hercules card
# reader helper (scripts/submit-jcl.ps1) expects them. @MVS_USER@ and
# @MVS_PASSWORD@ placeholders in the JCL are filled at submit time, so no
# credentials are baked into the image.
COPY src/jcl/ /tk4-/jcl/

EXPOSE 3270 8038
