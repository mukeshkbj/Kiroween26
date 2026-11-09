<#
.SYNOPSIS
  Print the sorted names of every HERC01.* catalog entry (demo app + KICKS),
  one "TYPE NAME" per line. Used to fingerprint the mainframe before and after
  a migration or restore: the two lists must be identical.
.DESCRIPTION
  Submits listcat-herc01.jcl, takes the JES2 job number from the console log,
  then reads THAT job's section of the printer file (START JOB n .. END JOB n),
  waiting until its END banner has been flushed. Only the names reach stdout
  (submit-jcl's progress output is swallowed), so `> file` gives a clean list.
.EXAMPLE
  powershell -File legacy/scripts/catalog-names.ps1 > before.txt
#>
param([string]$Container = "gss-legacy", [int]$TimeoutSec = 90,
      # Write the list here (ASCII) instead of stdout. Prefer this over `>`:
      # IDE terminals inject shell-integration escape codes into redirected output.
      [string]$OutFile)
$ErrorActionPreference = "Stop"
$out = & (Join-Path $PSScriptRoot "submit-jcl.ps1") -Jcl (Join-Path $PSScriptRoot "../src/jcl/listcat-herc01.jcl") -TimeoutSec $TimeoutSec *>&1 | Out-String
$m = [regex]::Matches($out, 'JOB\s+(\d+)\s+\$HASP395 LCHERC\s+ENDED')
if (-not $m.Count) { throw "LCHERC did not end (see submit-jcl output)" }
$job = $m[$m.Count - 1].Groups[1].Value
$deadline = (Get-Date).AddSeconds(30)
do {
    $text = docker exec $Container sh -c "sed -n '/START  JOB *$job  LCHERC/,/END   JOB *$job  LCHERC/p' /tk4-/prt/prt00e.txt"
    $done = ($text -join "`n") -match "END   JOB +$job +LCHERC"
    if (-not $done) { Start-Sleep 2 }
} until ($done -or (Get-Date) -gt $deadline)
if (-not $done) { throw "printout of job $job not flushed within 30 s" }
$names = $text | ForEach-Object { if ($_ -match '^(NONVSAM|CLUSTER|DATA|INDEX|ALIAS) -+ (HERC01\.\S+)') { "$($Matches[1]) $($Matches[2])" } } |
    Sort-Object -Unique
if (-not $names) { throw "LISTCAT job $job returned no HERC01 entries" }
if ($OutFile) { $names | Set-Content -Encoding ascii -LiteralPath $OutFile } else { $names }
