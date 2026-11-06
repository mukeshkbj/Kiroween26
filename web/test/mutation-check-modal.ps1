# Mutation checks for the confirmation modal (tasks 5.1). Each weakens a safety property; the modal tests must FAIL.
#   powershell -File test/mutation-check-modal.ps1
$ErrorActionPreference = 'Continue'
Set-Location (Split-Path -Parent $PSScriptRoot)
$p = 'src/confirm/ConfirmModal.tsx'
$orig = [IO.File]::ReadAllText((Resolve-Path $p))
$muts = @(
  @('N1 drop the isTrusted check', 'if (!(p.isTrusted ?? browserIsTrusted)(e.nativeEvent)) return;', '/* mutated */'),
  @('N2 remove the 600 ms approve delay', 'waitMs === 0 && !decidedRef.current', '!decidedRef.current'),
  @('N3 Esc no longer denies', "if (c.phase === 'open') decide('deny');", '/* mutated */'),
  @('N4 allow more than one decision', 'if (decidedRef.current) return; // exactly one decision per modal', '/* mutated */'),
  @('N5 approve allowed without a screen', 'hasScreen && left > 0', 'left > 0'),
  @('N6 approve allowed after expiry', 'hasScreen && left > 0', 'hasScreen')
)
$out = Join-Path ([IO.Path]::GetTempPath()) ("mutm-" + [guid]::NewGuid().ToString('N') + '.txt')
$bad = 0
try {
  foreach ($m in $muts) {
    if (-not $orig.Contains($m[1])) { Write-Host "$($m[0]): PATTERN NOT FOUND"; $bad++; continue }
    [IO.File]::WriteAllText((Resolve-Path $p), $orig.Replace($m[1], $m[2]))
    & npx vitest --run src/confirm *> $out
    if ($LASTEXITCODE -eq 0) { Write-Host "$($m[0]): SURVIVED"; $bad++ } else { Write-Host "$($m[0]): killed" }
  }
} finally {
  [IO.File]::WriteAllText((Resolve-Path $p), $orig)
  Remove-Item $out -ErrorAction SilentlyContinue
}
if ($bad -gt 0) { exit 1 }
