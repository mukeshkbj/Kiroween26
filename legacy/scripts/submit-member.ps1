<#
.SYNOPSIS
  Add/replace a single PDS member on gss-legacy from a local source file,
  using IEBUPDTE, by generating JCL on the fly and submitting it through
  submit-jcl.ps1. Agent A only (live container).
.DESCRIPTION
  Wraps the local file in:
    ./ ADD  NAME=<member>
    ./ NUMBER NEW1=... (we let IEBUPDTE renumber; source has no seq numbers)
  into DSN=<dataset>. The dataset must already exist (KICKS install datasets do).
  Credentials come from legacy/.env via submit-jcl.ps1's @MVS_USER@ placeholders.
.EXAMPLE
  ./submit-member.ps1 -File ../src/kicks/map/SMENMAP.bms -Dataset HERC01.KICKS.V1R5M0.MAPSRC -Member SMENMAP
#>
param(
    [Parameter(Mandatory)][string]$File,
    [Parameter(Mandatory)][string]$Dataset,
    [Parameter(Mandatory)][string]$Member,
    [int]$TimeoutSec = 150
)
$ErrorActionPreference = "Stop"
$src = Get-Content -LiteralPath $File
# Guard: member source must fit in columns 1-72 (card image); warn on overflow.
$long = $src | Where-Object { $_.Length -gt 72 }
if ($long) { throw "$File has $($long.Count) line(s) longer than 72 columns; fix before upload." }

$jcl = @()
$jcl += "//UPDMEM  JOB (ACCT),'ADD $Member',CLASS=A,MSGCLASS=A,"
$jcl += "//         USER=@MVS_USER@,PASSWORD=@MVS_PASSWORD@"
$jcl += "//UPD     EXEC PGM=IEBUPDTE,PARM=MOD"
$jcl += "//SYSPRINT DD SYSOUT=*"
$jcl += "//SYSUT1   DD DSN=$Dataset,DISP=SHR"
$jcl += "//SYSUT2   DD DSN=$Dataset,DISP=SHR"
$jcl += "//SYSIN    DD DATA"
$jcl += "./ ADD NAME=$Member"
$jcl += "./ NUMBER NEW1=10,INCR=10"
foreach ($line in $src) { $jcl += ($line.PadRight(72).Substring(0, 72)).TrimEnd() }
$jcl += "./ ENDUP"
$jcl += "/*"
$jcl += "//"

$tmp = Join-Path ([IO.Path]::GetTempPath()) "upd-$Member.jcl"
$jcl -join "`n" | Set-Content -LiteralPath $tmp -NoNewline
try {
    & (Join-Path $PSScriptRoot "submit-jcl.ps1") -Jcl $tmp -TimeoutSec $TimeoutSec
} finally {
    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
}
