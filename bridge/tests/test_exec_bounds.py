"""Bounded s3270 commands (Agent A's live finding, 2026-11-06).

A stand-in "s3270" (a tiny Python script) answers commands over the same pipe protocol.
It can be told to stay silent for a command, to report a locked keyboard, or to exit.
Every command it receives is appended to a log so the tests can prove a key was sent
exactly once, or not at all.
"""
import subprocess
import sys
import textwrap
import time

import pytest

from seance_bridge import AmbiguousAckError, KeyboardTimeoutError, SessionError
from seance_bridge.session import Session

FAKE = textwrap.dedent(
    r"""
    import sys, time
    log = open(sys.argv[1], "a", buffering=1)
    silent = set(sys.argv[2].split(",")) if len(sys.argv) > 2 and sys.argv[2] else set()
    locked = len(sys.argv) > 3 and sys.argv[3] == "locked"
    for line in sys.stdin:
        cmd = line.strip()
        log.write(cmd + "\n")
        name = cmd.split("(")[0]
        if name in silent:
            time.sleep(60)          # never answers
        elif name == "Wait" and "Unlock" in cmd and locked:
            print("L F U C(h) I 4 24 80 0 0 0x0 -"); print("error")
        elif name == "Quit":
            print("ok"); sys.exit(0)
        else:
            print("U F U C(h) I 4 24 80 0 0 0x0 -"); print("ok")
        sys.stdout.flush()
    """
)


def make(tmp_path, silent="", locked=False, exec_timeout_s=60.0) -> tuple[Session, "Path"]:
    script = tmp_path / "fake_s3270.py"
    script.write_text(FAKE, encoding="utf-8")
    log = tmp_path / "log.txt"
    log.write_text("", encoding="utf-8")
    args = [sys.executable, "-u", str(script), str(log), silent] + (["locked"] if locked else [])
    s = Session(command=args, exec_timeout_s=exec_timeout_s)
    s._proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                               encoding="latin-1", bufsize=1)
    s._start_reader()
    return s, log


def sent(log) -> list[str]:
    return [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln]


def test_normal_command_round_trips(tmp_path):
    s, log = make(tmp_path)
    data, status, ok = s._exec("Ascii()")
    assert ok and status.startswith("U")
    s.disconnect()
    assert s._proc is None


def test_silent_command_is_bounded_and_ambiguous_not_a_hang(tmp_path):
    s, log = make(tmp_path, silent="ReadBuffer", exec_timeout_s=0.5)
    t0 = time.monotonic()
    with pytest.raises(AmbiguousAckError):
        s._exec("ReadBuffer(Ascii)")
    assert time.monotonic() - t0 < 5
    assert s._proc is None                       # the session is dead, not half-alive
    with pytest.raises(SessionError):            # and stays dead: no silent reuse
        s._exec("Ascii()")
    assert sent(log) == ["ReadBuffer(Ascii)"]    # sent once, never again


def test_aid_with_no_answer_is_sent_exactly_once_and_never_resent(tmp_path):
    s, log = make(tmp_path, silent="PF", exec_timeout_s=60.0)
    # shrink the key deadline: press_key uses max(15, 3 * timeout) so call _exec path directly via a small timeout
    t0 = time.monotonic()
    with pytest.raises(AmbiguousAckError):
        s._exec("PF(3)", timeout_s=0.5)
    assert time.monotonic() - t0 < 5 and s._proc is None
    assert sent(log).count("PF(3)") == 1


def test_press_key_checks_unlock_first_and_translates_the_key(tmp_path):
    s, log = make(tmp_path)
    s.press_key("PF3", timeout_s=2)
    cmds = sent(log)
    assert cmds[0].startswith("Wait(") and "Unlock" in cmds[0]   # keyboard checked BEFORE the key
    assert cmds[1] == "PF(3)"                                      # translated wire form
    assert cmds[2].startswith("Wait(")                             # and waited after
    s.disconnect()


def test_locked_keyboard_means_the_key_is_not_written_at_all(tmp_path):
    s, log = make(tmp_path, locked=True)
    with pytest.raises(KeyboardTimeoutError, match="NOT sent"):
        s.press_key("Enter", timeout_s=1)
    assert "Enter" not in sent(log) and all(c.startswith("Wait(") for c in sent(log))


def test_unsupported_key_never_reaches_the_process(tmp_path):
    s, log = make(tmp_path)
    with pytest.raises(SessionError):
        s.press_key("Quit")
    assert sent(log) == []


def test_process_exit_is_a_session_error_not_a_hang(tmp_path):
    s, log = make(tmp_path)
    with pytest.raises(SessionError):
        s._exec("Quit")        # the fake answers ok then exits; the next command finds EOF
        s._exec("Ascii()")
