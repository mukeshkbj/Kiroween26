"""Run B's spirit-map CLI against a live host, with the PF/PA key-form fix.

Agent A only (live container). The current bridge sends PF/PA keys as the bare
name (``PA1``, ``PF13``), which s3270 rejects as an unknown action, so every
PF/PA press fails and the explorer halts with ``session_lost``
(docs/handoff/a/request-integrator-bridge-pf-keys.md). s3270 rejects the
unknown action before sending anything, so no key reaches the host.

This wrapper applies exactly the proposed fix -- ``PFn``/``PAn`` -> ``PF(n)``/
``PA(n)`` -- to ``Session.press_key`` for this process only, then hands over to
``python -m seance_spirit``. Nothing else changes: the safety gate, key policy,
deny lists and audit are B's and mcp-server's unmodified code. Delete this file
once the integrator ships the fix in bridge/.

    mcp-server/.venv/Scripts/python legacy/scripts/live_explore.py explore --app tk4-builtins ...
"""
from __future__ import annotations

import re
import runpy
import sys

from seance_bridge import errors as _errors
from seance_bridge import session as _session

_PFPA = re.compile(r"(PF|PA)(\d{1,2})")
_orig = _session.Session.press_key


def _press_key(self: _session.Session, key: str, timeout_s: float = 5.0) -> None:
    # Guard 2 (also proposed to the integrator): s3270 QUEUES an AID while the
    # host keyboard is locked and blocks with no timeout; the queued key could
    # even be sent later. So wait (bounded) for unlock BEFORE sending, and if
    # the keyboard stays locked, fail safely without sending anything.
    _, _, unlocked = self._exec(f"Wait({max(1, int(timeout_s))},Unlock)")
    if not unlocked:
        raise _errors.KeyboardTimeoutError("keyboard locked before key press; key NOT sent")
    m = _PFPA.fullmatch(key)
    return _orig(self, f"{m.group(1)}({m.group(2)})" if m else key, timeout_s)


_session.Session.press_key = _press_key  # type: ignore[method-assign]

if __name__ == "__main__":
    import faulthandler
    import os

    # Watchdog: a live run must be bounded. If it stalls (e.g. blocked on s3270),
    # dump every thread's stack to stderr and exit instead of hanging forever.
    faulthandler.dump_traceback_later(int(os.environ.get("LIVE_WATCHDOG_S", "240")), exit=True)
    sys.argv = ["seance_spirit", *sys.argv[1:]]
    runpy.run_module("seance_spirit", run_name="__main__", alter_sys=True)
