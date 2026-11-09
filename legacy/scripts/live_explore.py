"""Run B's spirit-map CLI against a live host, with a watchdog. Agent A only.

History: this wrapper used to patch the bridge (PF/PA key form, pre-press unlock
check). The integrator fixed both in bridge/ on 2026-11-06, so those patches
are gone; the bridge is used unmodified. Patching it now would even break it,
because ``PF(3)`` is not in the bridge's key allowlist. What remains:

* **Watchdog**: a live run must be bounded. After ``LIVE_WATCHDOG_S`` (default
  600) every thread's stack is dumped to stderr and the process exits.
* **Host/port wiring**: ``seance_spirit explore/replay`` build their Explorer
  without host/port, so a non-attach run always dials localhost:3270
  (reported to B: docs/handoff/integrator/request-b-explore-host-port.md).
  We pass ``Settings.from_env()`` host/port. Once B ships the fix, this is a
  no-op (B's own value wins).

    mcp-server/.venv/Scripts/python legacy/scripts/live_explore.py explore --app tk4-builtins ...
"""
from __future__ import annotations

import faulthandler
import functools
import inspect
import os
import sys


def _wire_host_port() -> None:
    from seance_mcp.config import Settings
    import seance_spirit.__main__ as cli  # noqa: PLC0415

    s = Settings.from_env()
    if "host=" in inspect.getsource(cli.cmd_explore):
        print("[live_explore] CLI already passes host/port; not overriding", file=sys.stderr)
        return
    cli.Explorer = functools.partial(cli.Explorer, host=s.host, tn_port=s.port)  # type: ignore[assignment]
    print(f"[live_explore] explorer will connect to {s.host}:{s.port}", file=sys.stderr)


if __name__ == "__main__":
    faulthandler.dump_traceback_later(int(os.environ.get("LIVE_WATCHDOG_S", "600")), exit=True)
    sys.argv = ["seance_spirit", *sys.argv[1:]]
    _wire_host_port()
    import seance_spirit.__main__ as cli  # noqa: E402,PLC0415

    sys.exit(cli.main())
