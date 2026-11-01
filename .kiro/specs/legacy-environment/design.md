# legacy-environment — Design

## Recommendation: (A) KICKS for TSO as primary, (B) built-in screens as second target, (C) COBOL line-mode as fallback

We use a three-tier approach. The primary demo app is built on KICKS for TSO (a free CICS clone), which gives us authentic BMS-mapped 3270 screens with structured fields — exactly what the `screen-bridge` is built to parse. A setup script downloads and installs KICKS at setup time so no KICKS files are committed to the repo (the KICKS 1.5.0 licence prohibits placing KICKS objects in public source-control). If KICKS install fails, a COBOL line-mode fallback keeps the demo working. TK4- built-in screens serve as a zero-setup second target for spirit-map auto-discovery.

## Why the three tiers

### (A) KICKS for TSO — PRIMARY (was option (a) in the original design)
KICKS is the most authentic choice for a business-level 3270 app: it provides CICS-compatible BMS maps (structured 3270 screens with fields), transaction processing, and file control. COBOL programs use `EXEC CICS` (KICKS) commands — `SEND MAP`, `RECEIVE MAP`, `READ`, `WRITE`, `REWRITE` — which is exactly how real mainframe business apps work.

**Licence handling:** KICKS 1.5.0 states that KICKS objects must not be placed in publicly accessible source-control repositories, and redistribution is only permitted as the complete original package. We respect this by:
- Never committing KICKS files to the repo.
- A setup script (`legacy/setup-kicks`) that downloads KICKS from GitHub and installs it into the running TK4- container at setup time.
- Our own app code (COBOL programs, BMS map source, JCL, control-table assembler source) is committed to the repo under MIT.

**KICKS installation process** (per Jay Moseley's guide):
1. Download KICKS archive from `github.com/moshix/kicks`.
2. Create a 3350 DASD volume with `dasdinit`, attach to Hercules via the console.
3. Initialize with ICKDSF, vary online, mount.
4. Set up a user catalog on the KICKS0 volume with IDCAMS.
5. Upload the XMI file via the card reader (`devinit 000c <file> ebcdic`) using a `RECV370`-style program.
6. Run the unpack jobstream to expand the 26 embedded XMIT files into KICKS datasets.
7. Run the KFIX CLIST to set the HLQ to `KICKS`.
8. Create KICKS system datasets (LODINTRA, LODTEMP).
9. Install our app: compile COBOL programs, assemble BMS mapsets, load seed data, update KICKS control tables (PPT, PCT, FCT).

The setup script submits each JCL job via the Hercules HTTP console on port 8038 using `devinit 000c <file> ascii`, waits for the job to complete (polling the hardcopy log), and proceeds to the next step.

### (b) ISPF dialog over COBOL — REJECTED: not available on TK4-
TK4- (MVS 3.8j) does not include ISPF. A catalog listing of SYS1.* datasets showed no ISPF-related libraries. Without ISPF, there is no panel-based dialog manager, and writing raw 3270 TPUT/TGET screen handling in assembler is too much custom work for a hackathon. This option is dead.

### (c) Plain TSO/ISPF built-in screens — REPURPOSED as second target (B)
TK4- built-in full-screen tools (the TSO logon screen, RFE/utility screens) are zero-setup and already produce structured 3270 screens. They serve as a second target for spirit-map exploration, proving auto-discovery works on any 3270 app — not just our own. No app code needed; the health check and spirit-map explorer just point at the built-in screens.

### (C) COBOL line-mode fallback
If KICKS install fails, a plain COBOL program using `ACCEPT`/`DISPLAY` (TSO line-mode terminal I/O, no BMS) provides a working policy enquiry. It uses the proven `COBUCLG` cataloged procedure and `devinit 000c` card-reader submission. The screens won't have structured fields, but the demo still runs.

## Container approach
Base image: `skunklabz/tk4-hercules` (MVS 3.8j TK4- on Hercules), exposing 3270 and 8038. We extend it with a `Dockerfile` that layers in our app source + setup scripts (but not KICKS). KICKS is installed at setup time, not during `docker build`.

`docker-compose.yml`:
- service `legacy`: built from `legacy/Dockerfile`, ports `${TN3270_PORT:-3270}:3270` and `${HERCULES_CONSOLE_PORT:-8038}:8038`, env from `.env`.
- healthcheck: poll the 3270 port until a readable TSO logon screen is present.

## Demo app: "Séance Insurance" (5 screens) — KICKS transactions

| # | Transaction | BMS Mapset | COBOL Program | Purpose | Screen type |
|---|-------------|-----------|--------------|---------|-------------|
| 1 | SMEN | SMENMAP | SEANCEM | Main menu: choice 1-4 | menu |
| 2 | SENQ | SENQMAP | SEANCEQ | Policy enquiry: POLNO → display details | enquiry (read-only result) |
| 3 | SLST | SLSTMAP | SEANCLS | List all policies (browse) | browse |
| 4 | SUPD | SUPDMAP | SEANCEU | Policy update: POLNO + field + new value | **update (commit-capable)** |
| 5 | SCNF | SCNFMAP | SEANCEC | Confirm update: Y/N → commit | **confirm (commit-capable)** |

COBOL programs use `EXEC CICS` commands: `SEND MAP`, `RECEIVE MAP`, `READ`/`WRITE`/`REWRITE` on the policy file, `RETURN TRANSID` for screen-to-screen navigation. BMS maps define the 3270 screen layout with protected (labels) and unprotected (input) fields.

Policy record layout (copybook): POLNO (6 char), HOLDER (20 char), STATUS (8 char), PREMIUM (6 digit), UPDDATE (8 char). Seed data: 8 policies in a sequential or VSAM file.

KICKS control tables updated for our app:
- PPT: entries for each COBOL program and BMS mapset.
- PCT: entries mapping transaction IDs (SMEN, SENQ, SLST, SUPD, SCNF) to programs.
- FCT: entry for the policy file.

## Demo user
TK4- default `HERC01` (password from `.env`, not committed). `.env.example` documents `HERC01` + a placeholder password.

## Health check
A script (`legacy/healthcheck.sh`) connects to the 3270 port and checks that a screen can be read and the keyboard unlocks (system available), indicating the IPL completed and TSO is ready. Timeout ~6 minutes for a cold IPL. This checks the TK4- baseline, not KICKS — KICKS availability is checked separately by the setup script.

## Data reset
`legacy/reset-data.sh` restores the seed policy file to its initial state (re-run the load JCL via the console), so the demo path works three times in a row.

## Ports / env
| Var | Default | Purpose |
|-----|---------|---------|
| `TN3270_HOST` | localhost | 3270 host for integration tests |
| `TN3270_PORT` | 3270 | 3270 terminal port |
| `HERCULES_CONSOLE_PORT` | 8038 | Hercules console (JCL submit) |
| `MVS_USER` | HERC01 | demo user |
| `MVS_PASSWORD` | (placeholder) | demo password, from .env |

## Sources
- TK4- Docker base: [skunklabz/tk4-hercules](https://hub.docker.com/r/skunklabz/tk4-hercules); multi-arch fallback [mvslovers/mvs-docker](https://github.com/mvslovers/mvs-docker).
- KICKS source: [moshix/kicks](https://github.com/moshix/kicks) (KICKS 1.5.0).
- KICKS install guide: [Jay Moseley — Installing KICKS](https://www.jaymoseley.com/hercules/kicks/index.htm).
- KICKS licence: KICKS 1.5.0 License — redistribution restrictions as cited in the KICKS distribution.
- COBOL compiler: `IKFCBL00` (OS/VS COBOL) via `COBUCLG` cataloged procedure — verified working on TK4-.
- JCL submission: `devinit 000c <file> ascii` via Hercules HTTP console on port 8038 — verified working.
