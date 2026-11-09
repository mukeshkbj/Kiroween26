<#
.SYNOPSIS
  Install (or reinstall) the Seance Insurance demo app on TK4- from source.
.DESCRIPTION
  One command that rebuilds everything the stand-in needs on the mainframe:
    1. clean-seance.jcl      delete HERC01.SEANCE.COB/LOAD/TSOREQ (ours only)
    2. mkpds.jcl             create HERC01.SEANCE.COB (source PDS)
    3. submit-member.ps1     upload src/cobol/SEANCSVC.cob
    4. build-seancsvc.jcl    compile + link -> HERC01.SEANCE.LOAD(SEANCSVC)
    5. tso-reqs.jcl          TSO request cards (line-mode fallback)
    6. seed-policies.jcl     the 8 seed policies (same as reset-data)
    7. run-seancsvc.jcl      smoke test: lookup P0000003 must return A. ROSE
  Use it after a fresh container (e.g. `docker compose down` then `up`, which
  gives TK4- new, empty volumes). Does not touch KICKS or any other dataset.
  Stops at the first failing step; nothing is retried.
.EXAMPLE
  powershell -File legacy/setup-app.ps1
#>
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$jcl = Join-Path $here "src/jcl"
$submit = Join-Path $here "scripts/submit-jcl.ps1"

function Step([string]$title, [scriptblock]$run, [string]$expect) {
    Write-Host "== $title"
    $out = (& $run 2>&1 | Out-String)
    if ($out -notmatch $expect) {
        Write-Host $out
        throw "setup-app: step '$title' did not show /$expect/; stopping."
    }
    Write-Host "   ok"
}

Step "clean old datasets" { & $submit -Jcl (Join-Path $jcl "clean-seance.jcl") -TimeoutSec 60 } "CLNSEAN\s+DEL\s+IEFBR14\s+RC= 0000"
Step "create source PDS"  { & $submit -Jcl (Join-Path $jcl "mkpds.jcl") -TimeoutSec 60 } "MKPDS\s+S1\s+IEFBR14\s+RC= 0000"
Step "upload SEANCSVC"    { & (Join-Path $here "scripts/submit-member.ps1") -File (Join-Path $here "src/cobol/SEANCSVC.cob") -Dataset HERC01.SEANCE.COB -Member SEANCSVC } "HIGHEST CONDITION CODE WAS 0000000[04]"
Step "compile + link"     { & $submit -Jcl (Join-Path $jcl "build-seancsvc.jcl") -TimeoutSec 180 } "LKED\s+IEWL\s+RC= 0000"
Step "TSO request cards"  { & $submit -Jcl (Join-Path $jcl "tso-reqs.jcl") -TimeoutSec 60 } "TSOREQ\s+LOAD\s+IEBUPDTE\s+RC= 0000"
Step "seed 8 policies"    { & $submit -Jcl (Join-Path $jcl "seed-policies.jcl") -TimeoutSec 90 } "SEEDPOL\s+LOAD\s+IEBGENER\s+RC= 0000"
Step "smoke test"         { & $submit -Jcl (Join-Path $jcl "run-seancsvc.jcl") -TimeoutSec 90 } "OK\|R\|P0000003\|A\. ROSE"
Write-Host "Seance Insurance app installed. Start the stand-in, then run legacy/healthcheck.ps1."
