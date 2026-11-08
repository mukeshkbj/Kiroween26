# Mutation checks for the reducer (tasks 2.2). Each deliberately weakens src/state/reducer.ts and runs the
# state tests: every mutation must make them FAIL. The original file is restored afterwards.
#   powershell -File test/mutation-check.ps1
$ErrorActionPreference = 'Continue'
Set-Location (Split-Path -Parent $PSScriptRoot)
$p = 'src/state/reducer.ts'
$orig = [IO.File]::ReadAllText((Resolve-Path $p))
$muts = @(
  @('M1 remove seq de-dup', 'if (ev.seq <= s.session.lastSeq && s.session.id === ev.session_id) return s;', '/* mutated */'),
  @('M2 remove supersede rule', 'return { ...next, confirmation: c };', 'return { ...next, confirmation: old ?? c };'),
  @('M3 store hidden value', 'fields: s.fields.map((f) => (f.hidden && f.value !== null ? { ...f, value: null } : f)),', 'fields: s.fields,'),
  @('M4 drop gap check', 'if (s.session.lastSeq > 0 && ev.seq > s.session.lastSeq + 1 && !isResync) {', 'if (false) {'),
  @('M5 accept unmatched tool_result', "if (!call || call.status !== 'running') return s0;", "if (call && call.status !== 'running') return s0;"),
  @('M6 skip new-session reset', 'if (s.session.id !== null && s.session.id !== ev.session_id) s = resetForNewSession(s);', '/* mutated */'),
  @('M7 fresh client demands seq 1 (the reconnect-storm bug)', 'ev.seq === 1 || isResync || ev.type === ''session_state''', 'ev.seq === 1 || isResync')
)
$out = Join-Path ([IO.Path]::GetTempPath()) ("mut-" + [guid]::NewGuid().ToString('N') + '.txt')
$bad = 0
try {
  foreach ($m in $muts) {
    if (-not $orig.Contains($m[1])) { Write-Host "$($m[0]): PATTERN NOT FOUND"; $bad++; continue }
    [IO.File]::WriteAllText((Resolve-Path $p), $orig.Replace($m[1], $m[2]))
    & npx vitest --run src/state *> $out
    if ($LASTEXITCODE -eq 0) { Write-Host "$($m[0]): SURVIVED (tests did not notice)"; $bad++ }
    else { Write-Host "$($m[0]): killed" }
  }
} finally {
  [IO.File]::WriteAllText((Resolve-Path $p), $orig)
  Remove-Item $out -ErrorAction SilentlyContinue
}
if ($bad -gt 0) { exit 1 }

