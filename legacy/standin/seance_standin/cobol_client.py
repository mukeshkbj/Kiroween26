"""Call the real COBOL business logic SEANCSVC on the live TK4- mainframe.

Each request submits a small job to Hercules' card reader (device 000C) via the
HTTP console, waits for it to end, and reads the pipe-delimited response SEANCSVC
printed (see legacy/src/cobol/SEANCSVC.cob). This keeps the business logic on the
mainframe; the stand-in is only the 3270 presentation layer.

Safety: the COBOL update rewrites HERC01.SEANCE.POLICY in place. A job is never
resubmitted automatically -- an ambiguous/timed-out run fails closed (contract
section 11.6, mainframe-safety "no dangerous retries").
"""
from __future__ import annotations

import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

CONSOLE = os.environ.get("HERCULES_CONSOLE", "http://localhost:8038")
CONTAINER_JCL_DIR = "/tk4-/jcl"
HARDCOPY = "/tk4-/log/hardcopy.log"
PRINTER = "/tk4-/prt/prt00e.txt"


@dataclass
class Policy:
    polno: str
    holder: str
    status: str
    premium: str
    upddate: str


class CobolError(RuntimeError):
    pass


DOCKER_TIMEOUT_S = float(os.environ.get("STANDIN_DOCKER_TIMEOUT_S", "20"))


def _docker_exec(container: str, cmd: str) -> str:
    """Run a command in the container, bounded: a stalled Docker engine (seen
    2026-11-06) must surface as a CobolError, never as a 3270 terminal that
    waits forever."""
    import subprocess

    try:
        return subprocess.run(
            ["docker", "exec", container, "sh", "-c", cmd],
            capture_output=True, text=True, check=False, timeout=DOCKER_TIMEOUT_S,
        ).stdout
    except subprocess.TimeoutExpired:
        raise CobolError("mainframe backend (docker exec) did not answer") from None


def _console(cmd: str) -> None:
    body = urllib.parse.urlencode({"command": cmd, "send": "Send"}).encode()
    req = urllib.request.Request(f"{CONSOLE}/cgi-bin/tasks/syslog", data=body)
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception:
        pass  # console returns HTTP/0.9; the read may error but the command ran


class CobolClient:
    """Runs SEANCSVC jobs against the gss-legacy container (Agent A's live host)."""

    def __init__(self, container: str = "gss-legacy", user: str | None = None,
                 password: str | None = None, timeout_s: int = 60):
        self.container = container
        self.user = user or os.environ.get("MVS_USER", "HERC01")
        self.password = password or os.environ.get("MVS_PASSWORD", "")
        self.timeout_s = timeout_s

    # -- public operations ------------------------------------------------

    def lookup(self, polno: str) -> Policy | None:
        rows = self._run(f"L {polno.strip().upper()}")
        return rows[0] if rows else None

    def list_all(self) -> list[Policy]:
        return self._run("A")

    def update(self, polno: str, status_code: str, premium: str) -> Policy | None:
        card = f"U {polno.strip().upper():<8} {status_code or ' '} {premium.strip():<8}"
        rows = self._run_update(card)
        return rows[0] if rows else None

    # -- job plumbing -----------------------------------------------------

    def _job(self, step_svcout: str, request_card: str, polout: str) -> str:
        return "\n".join([
            f"//SVCRUN   JOB (ACCT),'SVC',CLASS=A,MSGCLASS=A,REGION=2048K,",
            f"//         USER={self.user},PASSWORD={self.password}",
            f"//RUN     EXEC PGM=SEANCSVC",
            f"//STEPLIB  DD DSN=HERC01.SEANCE.LOAD,DISP=SHR",
            f"//POLIN    DD DSN=HERC01.SEANCE.POLICY,DISP=SHR",
            f"//POLOUT   DD {polout}",
            f"//SYSOUT   DD SYSOUT=*",
            f"//SYSIN    DD *",
            request_card,
            "/*",
            "//",
        ])

    def _run(self, request_card: str) -> list[Policy]:
        return self._submit(self._job("*", request_card, "DUMMY"))

    def _run_update(self, request_card: str) -> list[Policy]:
        # Update rewrites the master: POLOUT to a temp, then a copy step swaps it.
        job = "\n".join([
            f"//SVCUPD   JOB (ACCT),'SVCU',CLASS=A,MSGCLASS=A,REGION=2048K,",
            f"//         USER={self.user},PASSWORD={self.password}",
            f"//RUN     EXEC PGM=SEANCSVC",
            f"//STEPLIB  DD DSN=HERC01.SEANCE.LOAD,DISP=SHR",
            f"//POLIN    DD DSN=HERC01.SEANCE.POLICY,DISP=SHR",
            f"//POLOUT   DD DSN=&&NEW,DISP=(,PASS),UNIT=SYSDA,",
            f"//            SPACE=(TRK,(2,1)),DCB=(RECFM=FB,LRECL=80,BLKSIZE=800)",
            f"//SYSOUT   DD SYSOUT=*",
            f"//SYSIN    DD *",
            request_card,
            "/*",
            f"//SWAP    EXEC PGM=IEBGENER,COND=(4,LT,RUN)",
            f"//SYSPRINT DD SYSOUT=*",
            f"//SYSIN    DD DUMMY",
            f"//SYSUT1   DD DSN=&&NEW,DISP=(OLD,DELETE)",
            f"//SYSUT2   DD DSN=HERC01.SEANCE.POLICY,DISP=OLD",
            "//",
        ])
        return self._submit(job)

    def _submit(self, jcl: str) -> list[Policy]:
        name = f"svc-{int(time.time()*1000)}.jcl"
        remote = f"{CONTAINER_JCL_DIR}/{name}"
        self._put_file(remote, jcl)
        log_off = self._size(HARDCOPY)
        prt_off = self._size(PRINTER)
        _console(f"devinit 000c {remote} ascii")
        job_re = re.compile(r"HASP395\s+SVC(RUN|UPD)\s+ENDED")
        deadline = time.monotonic() + self.timeout_s
        ended = False
        while time.monotonic() < deadline:
            time.sleep(1.0)
            tail = _docker_exec(self.container, f"tail -c +{log_off + 1} {HARDCOPY}")
            if job_re.search(tail):
                ended = True
                break
            if re.search(r"SVC(RUN|UPD)\s+.*JCL ERROR", tail):
                raise CobolError("SEANCSVC job rejected (JCL error)")
        if not ended:
            raise CobolError("SEANCSVC job did not end in time; not resubmitting")
        time.sleep(1.5)  # let the printer flush
        out = _docker_exec(self.container, f"tail -c +{prt_off + 1} {PRINTER}")
        return self._parse(out)

    def _parse(self, printed: str) -> list[Policy]:
        rows: list[Policy] = []
        for line in printed.splitlines():
            line = line.rstrip()
            if line.startswith("OK|R|"):
                parts = line.split("|")
                # OK | R | polno | holder | status | premium | upddate
                if len(parts) >= 7:
                    rows.append(Policy(
                        polno=parts[2].strip(), holder=parts[3].strip(),
                        status=parts[4].strip(), premium=parts[5].strip(),
                        upddate=parts[6].strip(),
                    ))
            elif line.startswith("ER|"):
                # error response: caller treats empty list as not found
                return []
        return rows

    def _put_file(self, remote: str, text: str) -> None:
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile("w", delete=False, newline="\n") as fh:
            fh.write(text)
            local = fh.name
        try:
            subprocess.run(["docker", "cp", local, f"{self.container}:{remote}"],
                           check=True, capture_output=True, timeout=DOCKER_TIMEOUT_S)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            # Nothing was submitted yet (the job file never reached the reader).
            raise CobolError("mainframe backend (docker cp) unavailable") from None
        finally:
            os.unlink(local)

    def _size(self, path: str) -> int:
        out = _docker_exec(self.container, f"wc -c < {path} 2>/dev/null || echo 0")
        try:
            return int(out.strip() or "0")
        except ValueError:
            return 0
