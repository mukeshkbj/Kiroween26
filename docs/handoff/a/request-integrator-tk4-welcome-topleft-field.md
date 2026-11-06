# Request to integrator: FakeApp.from_capture rejects a field at buffer position 0

**What:** `seance_mcp.fake._spec_from_screen_out` raises
`CaptureError("<name>: field starts at the first cell")` when a captured screen
has a field whose attribute byte is at buffer offset 0 (row 0, col 0). The real
TK4- welcome screen has exactly such a field, so
`legacy/captures/tk4-builtins/capture.json` cannot be replayed through the fake.

**Why it matters:** `tk4-builtins` is Agent B's second spirit-map target. The
capture is genuine (captured live through the real bridge), so the loader, not
the data, is the limitation. I did not edit the capture to dodge it, because
that would falsify a real screen (contract 2.3: a capture carries only what the
tools returned).

**Proposed fix (mcp-server, integrator-owned):** allow a field at position 0.
In `_spec_from_screen_out`, instead of raising on `pos < 0`, treat a field whose
data starts at col 0 as having its attribute byte at the last cell of the
previous row (standard 3270 wrap) or simply place the SF at position 0 and drop
the implicit `(0, P)` start. A real 3270 buffer wraps, so the attribute for a
field "at (0,0)" physically sits at offset 1919; the parser already handles
wrap. Happy to test a fix against the committed capture.

**Interim:** B uses the `welcome` screen's `rows`/`fields` directly (documented
in `response-b-captures.md`); `logon_rejected` loads fine.

Filed 2026-11-05 by Agent A.
