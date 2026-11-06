<#
.SYNOPSIS
  Restore the 8 seed policies on the live TK4- mainframe (legacy-environment 7.2).
.DESCRIPTION
  Re-runs seed-policies.jcl through the Hercules card reader, which deletes and
  reloads HERC01.SEANCE.POLICY with the known 8 records (contracts section 10).
  Run this before each demo so "the demo path works three times in a row".
  The stand-in reads this file per request, so no stand-in restart is needed.
.EXAMPLE
  powershell -File legacy/reset-data.ps1
#>
param([int]$TimeoutSec = 90)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
Write-Host "Reseeding HERC01.SEANCE.POLICY (8 seed policies)..."
& (Join-Path $here "scripts/submit-jcl.ps1") -Jcl (Join-Path $here "src/jcl/seed-policies.jcl") -TimeoutSec $TimeoutSec |
    Select-String -Pattern "SEEDPOL|RC=|ENDED" | ForEach-Object { $_.Line }
Write-Host "Reset complete."
