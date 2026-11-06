# Request to integrator: bridge sends `PF3`, s3270 wants `PF(3)`

**What:** `seance_bridge.Session.press_key` / `Bridge.press` send the raw key
name as an s3270 command (e.g. the literal `PF3`). s3270 rejects `PF3` and
`PA1`; the correct s3270 action form is `PF(3)` / `PA(1)`. `Enter` and `Clear`
are fine because those are valid s3270 action names.

**Evidence (against the live stand-in and TK4-, Agent A worktree):**
```
PF3   -> error   (status "U F U C(localhost) I ...")
PF(3) -> ok
```
So any live press of a PF/PA key currently fails with `SessionError: PF3 failed`.
ENTER/CLEAR paths are unaffected, which is why it was not caught earlier.

**Why it matters:** D's agent and the demo need PF3 (back) and PF7/PF8 (paging)
on the real screens (contract 10.1-10.2). The spirit-map explorer (B) also
presses PF keys. This blocks any live PF-key use.

**Proposed fix (mcp-server/bridge, integrator-owned):** in `Session.press_key`,
translate a `PFn`/`PAn` name to the s3270 action form before `_exec`:
```python
import re
m = re.fullmatch(r"(PF|PA)(\d+)", key)
cmd = f"{m.group(1)}({m.group(2)})" if m else key
```
Keep `Enter`/`Clear` as-is. No contract change (section 3.3 key names stay
`Enter`, `Clear`, `PA1`, `PF3`, ...; this is purely the s3270 wire form).

**Workaround in the meantime:** Agent A's capture tool
(`legacy/scripts/capture_seance.py`) issues `PF(n)` directly via
`Session._exec` for PF/PA keys; see the `press()` helper there.

Filed 2026-11-05 by Agent A.
