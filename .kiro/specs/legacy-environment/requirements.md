# Spec: legacy-environment

## Overview
A one-command local legacy system for development and for judges. Runs TK4- (MVS 3.8j on Hercules) in Docker, exposes a 3270 terminal and the Hercules console, and installs a demo business application so a fresh clone works end to end. This is the substrate the `screen-bridge` integration test runs against.

## Requirements

### Container
- REQ-001: A `docker-compose` service running TK4- (Hercules MVS 3.8j), exposing 3270 on port 3270 and the Hercules console on 8038.
- REQ-002: Host ports configurable via `.env` (defaults 3270 / 8038); no ports hard-coded in compose.

### Demo user
- REQ-003: A documented demo user (TK4- default `HERC01`) configured via `.env`, not hard-coded credentials.
- REQ-004: No credentials committed to the repo; `.env` gitignored, `.env.example` committed with placeholders.

### Demo business app — three-tier approach
- REQ-005: A scripted setup step installs the demo business application so a fresh clone works without manual TSO steps.

#### (A) Primary — KICKS for TSO
- REQ-006a: The primary demo app is built as KICKS transactions (CICS clone) with BMS maps over COBOL programs and a seeded policy file. ~5 screens: menu, policy enquiry, policy list, policy update, confirm update.
- REQ-006b: KICKS is never committed to the repo (KICKS 1.5.0 licence prohibits placing KICKS objects in public source-control). A setup script (`legacy/setup-kicks`) downloads and installs KICKS into the running container at setup time.
- REQ-006c: Our own app code (COBOL programs, BMS map source, JCL, control-table updates) is committed to the repo under an MIT licence.
- REQ-006d: The KICKS setup script is documented in `legacy/README.md` and runnable with one command against a running TK4- container.

#### (B) Second target — TK4- built-in full-screen tools
- REQ-007a: TK4- built-in full-screen tools (e.g. RFE / the TSO logon and utility screens) serve as a second, zero-setup target for spirit-map exploration.
- REQ-007b: This proves auto-discovery works on any 3270 app, not just our own.

#### (C) Fallback — COBOL line-mode
- REQ-008a: A plain COBOL line-mode version of the policy enquiry (TSO terminal I/O via ACCEPT/DISPLAY, no BMS) so the demo still works if KICKS install fails.
- REQ-008b: Uses the proven COBUCLG cataloged procedure and devinit 000c card-reader submission.

### Health check
- REQ-009: A health check that waits until the TSO logon screen is reachable over 3270 (i.e. the keyboard is unlocked and a logon screen can be read), with a timeout and a clear error on failure.

### Convenience / repeatability
- REQ-010: One command starts everything (`docker-compose up`); documented startup-time expectations (TK4- IPL takes a few minutes from cold).
- REQ-011: A script to reset the demo app data to a known state, so the demo path works three times in a row.

### Specs
- REQ-012: `design.md` researches options and recommends the approach. Criteria: looks like a real business app, ~5 screens, reliable, licence allows our code in the repo.

## Non-goals
- Real z/OS.
- Networking beyond localhost.
- Production hardening / security hardening of the mainframe.
- Committing KICKS binaries or any third-party mainframe objects to the repo.
