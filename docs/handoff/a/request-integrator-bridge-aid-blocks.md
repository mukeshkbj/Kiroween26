# Request to integrator: an AID press can block forever in s3270 (no timeout)

Second live finding from B's tk4-builtins exploration (2026-11-06, Agent A).
Related to `request-integrator-bridge-pf-keys.md` (still open; PF/PA presses
fail live with the current bridge).

**What:** `Session.press_key` calls `_exec(key)`. For an AID key, s3270 does not
answer until the host unlocks the keyboard after receiving the key. If the host
never answers, `_exec` blocks in `proc.stdout.readline()` with **no timeout**,
and the caller hangs forever. On the real TK4- this happens reliably: after
CLEAR on an unformatted (blank) VTAM screen, the next AID (a PA or PF13-24) is
sent and TK4- never responds.

**Evidence:** `docs/handoff/a/live-runs/tk4-builtins/stack.txt`, a faulthandler
dump from a watchdog. Thread stack: `session.py:122 _exec` <- `session.py:208
press_key` <- `bridge.py:110 press` <- `port.py:80`. A bounded
`Wait(5,Unlock)` immediately before the press succeeded, so the keyboard was
unlocked, the key **was sent**, and only the host's answer was missing.

**Why it matters (safety):** this is an *ambiguous acknowledgement*, the case
mainframe-safety says must fail safely and never be retried. At the moment it
neither fails nor reports: it hangs the explorer, the agent and the MCP server
call, and holds the single live session. The bridge already has
`AmbiguousAckError`, but nothing raises it on this path.

**Proposed fix (bridge, integrator-owned):**
1. Bound every `_exec`. For example, read s3270's stdout on a thread or via a
   selector with a deadline. Simplest: run AID keys as a non-blocking s3270
   action and then `Wait(<t>,Unlock)`, or kill and reconnect the s3270 process
   on timeout.
2. If the deadline expires after an AID was written, raise `AmbiguousAckError`.
   This means "key may have been processed, do not resend". The caller reports
   `ambiguous_ack` (contracts 3.4) and must reconnect or resync before doing
   anything else.
3. Also check `Wait(<t>,Unlock)` before writing the AID. If the keyboard is
   locked, raise `KeyboardTimeoutError` with nothing sent. s3270 queues AIDs
   while the keyboard is locked, and a queued key could be sent later, behind
   the caller's back.

Agent A's live runner `legacy/scripts/live_explore.py` does (3) and adds a
watchdog. It cannot do (1)/(2) without reimplementing the session.
