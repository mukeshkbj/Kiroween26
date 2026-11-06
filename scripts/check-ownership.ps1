<#
.SYNOPSIS
  Merge gate: fail if a branch changed paths its owner may not touch (docs/contracts.md section 1).

.DESCRIPTION
  Looks at the files touched by the commits unique to the branch (base..branch, merge commits
  excluded), so merging main into your branch, or your branch into main, never counts as your change.
  Branch -> allowed prefixes:
    agent/a-legacy        legacy/  .kiro/specs/legacy-environment/  docs/handoff/a/
    agent/b-spirit-map    spirit-map/  docs/spirit-map/  .kiro/specs/spirit-map/  docs/handoff/b/
    agent/c-seance-ui     web/  .kiro/specs/seance-ui/  docs/handoff/c/
    agent/d-seance-agent  agent/  .kiro/specs/seance-agent/  docs/handoff/d/
    main, integration     anything (integrator)
  Everywhere: never a real .env, the live marker, keys or certificates.

.EXAMPLE
  powershell -File scripts/check-ownership.ps1                 # current branch against main
  powershell -File scripts/check-ownership.ps1 -Branch agent/b-spirit-map -Base main
#>
param(
  [string]$Branch = '',
  [string]$Base = 'main'
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not $Branch) { $Branch = (git branch --show-current).Trim() }
if (-not $Branch) { Write-Error 'no branch (detached HEAD?); pass -Branch'; exit 2 }

$allowed = @{
  'agent/a-legacy'       = @('legacy/', '.kiro/specs/legacy-environment/', 'docs/handoff/a/')
  'agent/b-spirit-map'   = @('spirit-map/', 'docs/spirit-map/', '.kiro/specs/spirit-map/', 'docs/handoff/b/')
  'agent/c-seance-ui'    = @('web/', '.kiro/specs/seance-ui/', 'docs/handoff/c/')
  'agent/d-seance-agent' = @('agent/', '.kiro/specs/seance-agent/', 'docs/handoff/d/')
}
$integrator = @('main', 'integration')

if ($integrator -contains $Branch) {
  $prefixes = $null
} elseif ($allowed.ContainsKey($Branch)) {
  $prefixes = $allowed[$Branch]
} else {
  Write-Host "FAIL: unknown branch '$Branch'. Expected one of: $(($allowed.Keys + $integrator) -join ', ')"
  exit 2
}

# Only the files touched by commits the branch itself authored: reachable from the branch but not
# from the base, merge commits excluded. A three-dot diff is wrong once a branch has been merged
# into the base and the base merged back (criss-cross history: several merge bases, and the diff
# then charges the base's own files to the branch).
$changed = @(git log --no-merges --name-only --no-renames --pretty=format: "$Base..$Branch" | Where-Object { $_ -ne '' } | Sort-Object -Unique)
if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: git log $Base..$Branch failed"; exit 2 }

$forbiddenAlways = '(^|/)\.env$', '(^|/)\.env\.local$', '(^|/)\.gss-live-ok$', '\.(pem|key|pfx|p12)$', '(^|/)id_(rsa|ed25519)$'

$violations = @()
foreach ($f in $changed) {
  if ($f -ne '') {
    foreach ($re in $forbiddenAlways) {
      if ($f -match $re) { $violations += "$f  (never commit this kind of file)"; break }
    }
    if ($null -ne $prefixes) {
      $ok = $false
      foreach ($p in $prefixes) { if ($f.StartsWith($p)) { $ok = $true; break } }
      if (-not $ok) { $violations += "$f  (not in $Branch's paths)" }
    }
  }
}

if ($violations.Count -gt 0) {
  Write-Host "FAIL: $Branch changed files it does not own:"
  $violations | Sort-Object -Unique | ForEach-Object { Write-Host "  $_" }
  Write-Host 'Ask the owner with a request file in docs/handoff/<you>/ (docs/contracts.md section 12).'
  exit 1
}
Write-Host "ok: $Branch touched $($changed.Count) file(s), all in its own paths."
exit 0
