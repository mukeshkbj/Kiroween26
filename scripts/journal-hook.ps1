<#
.SYNOPSIS
  Kiro hook helper: append a dated line to docs/kiro-journal.md when a spec or
  steering file changes.

.DESCRIPTION
  Reads the hook's JSON from stdin, finds a .kiro/specs/** or .kiro/steering/**
  markdown path in it, and appends "- YYYY-MM-DD: <path> changed". Skips the line
  if the same date+path is already recorded, so repeated saves don't spam the
  journal. Does nothing (exit 0) if no such path is present.
#>
$raw = [Console]::In.ReadToEnd()
# JSON escapes backslashes ("\\"), so accept either slash style.
if ($raw -notmatch '\.kiro[\\/]+(specs|steering)[\\/]+[^"\r\n]*?\.md') { exit 0 }
$path = ($Matches[0] -replace '\\+', '/')

$repo = Split-Path -Parent $PSScriptRoot
$journal = Join-Path $repo "docs\kiro-journal.md"
$line = "- $(Get-Date -Format 'yyyy-MM-dd'): ``$path`` changed"

if (-not (Test-Path $journal)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $journal) | Out-Null
    "# Kiro journal`n`nHow Kiro was used on Green Screen Seance: spec and steering changes, in order.`n" |
        Set-Content -LiteralPath $journal -Encoding utf8
}
if (-not (Select-String -LiteralPath $journal -SimpleMatch -Pattern $line -Quiet)) {
    Add-Content -LiteralPath $journal -Value $line -Encoding utf8
}
exit 0
