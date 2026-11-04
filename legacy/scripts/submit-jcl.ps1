<#
.SYNOPSIS
  Submit a JCL file to the TK4- container (Hercules card reader 000C) and show
  what the job printed.

.DESCRIPTION
  Copies the file into the gss-legacy container, issues "devinit 000c <file> <mode>"
  through the Hercules HTTP console, waits for the JES2 "$HASP395 <job> ENDED"
  message, then prints the new hardcopy-log and printer lines.

  Mode "ascii" is for JCL text; "ebcdic" is for binary XMIT/XMI uploads.
  A job is never resubmitted automatically: if it times out, this script reports
  and exits (safe: a half-run job may already have changed data).

.EXAMPLE
  ./submit-jcl.ps1 -Jcl ../src/jcl/listcat.jcl
#>
param(
    [Parameter(Mandatory)][string]$Jcl,
    [ValidateSet("ascii", "ebcdic")][string]$Mode = "ascii",
    [int]$TimeoutSec = 180,
    # Hercules commands to issue BEFORE the job is submitted, e.g. mounting an
    # XMI on the 10C reader: "devinit 10c /tk4-/jcl/kicks.xmi ebcdic"
    [string[]]$PreCommand = @(),
    [string]$Container = "gss-legacy",
    [int]$ConsolePort = 8038
)
$ErrorActionPreference = "Stop"

$name = [IO.Path]::GetFileName($Jcl)
$jobName = ""
if ($Mode -eq "ascii") {
    $first = (Get-Content -LiteralPath $Jcl -TotalCount 1)
    if ($first -match '^//(\S+)\s+JOB') { $jobName = $Matches[1] }
}
$remote = "/tk4-/jcl/$name"

# TK4- runs unauthenticated batch jobs as user PROD (RAKF), which may not create
# HERC01.* datasets. JCL carries @MVS_USER@ / @MVS_PASSWORD@ placeholders; we fill
# them from legacy/.env (gitignored) or the environment, into a temp copy.
function Get-EnvValue($key) {
    $v = [Environment]::GetEnvironmentVariable($key)
    if ($v) { return $v }
    $envFile = Join-Path $PSScriptRoot "..\.env"
    if (Test-Path $envFile) {
        $line = Get-Content $envFile | Where-Object { $_ -match "^\s*$key=" } | Select-Object -First 1
        if ($line) { return ($line -split "=", 2)[1].Trim() }
    }
    return $null
}
$upload = $Jcl
$temp = $null
if ($Mode -eq "ascii") {
    $text = Get-Content -LiteralPath $Jcl -Raw
    if ($text -match "@MVS_(USER|PASSWORD)@") {
        $u = Get-EnvValue "MVS_USER"; $p = Get-EnvValue "MVS_PASSWORD"
        if (-not $u -or -not $p) { throw "MVS_USER / MVS_PASSWORD not set (legacy/.env or environment)" }
        $temp = Join-Path ([IO.Path]::GetTempPath()) $name
        $text.Replace("@MVS_USER@", $u).Replace("@MVS_PASSWORD@", $p) | Set-Content -LiteralPath $temp -NoNewline
        $upload = $temp
    }
}
docker cp $upload "${Container}:$remote" | Out-Null
if ($temp) { Remove-Item -LiteralPath $temp -Force }

function Get-Size($path) { [int](docker exec $Container sh -c "wc -c < $path") }
$logOff = Get-Size "/tk4-/log/hardcopy.log"
$e0 = Get-Size "/tk4-/prt/prt00e.txt"
$f0 = Get-Size "/tk4-/prt/prt00f.txt"

foreach ($pre in $PreCommand) {
    curl.exe -s -m 15 --http0.9 -d "command=$([uri]::EscapeDataString($pre))&send=Send" `
        "http://localhost:$ConsolePort/cgi-bin/tasks/syslog" | Out-Null
    Write-Host "pre-command: $pre"
    Start-Sleep -Seconds 2
}
$cmd = "devinit 000c $remote $Mode"
curl.exe -s -m 15 --http0.9 -d "command=$([uri]::EscapeDataString($cmd))&send=Send" `
    "http://localhost:$ConsolePort/cgi-bin/tasks/syslog" | Out-Null
Write-Host "submitted: $cmd"

$deadline = (Get-Date).AddSeconds($TimeoutSec)
$ended = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    $tail = docker exec $Container sh -c "tail -c +$($logOff + 1) /tk4-/log/hardcopy.log"
    if ($jobName -and ($tail -match "HASP395 $jobName\s+ENDED")) { $ended = $true; break }
    if (-not $jobName -and ($tail -match "HASP395\s+\S+\s+ENDED")) { $ended = $true; break }
}
Start-Sleep -Seconds 4  # let the printers flush
Write-Host "=== hardcopy log (new) ==="
docker exec $Container sh -c "tail -c +$($logOff + 1) /tk4-/log/hardcopy.log" |
    Select-String -Pattern "HASP|IEF|IEC|IEA|ABEND|ERROR|RECV" | ForEach-Object { $_.Line }
foreach ($p in @(@("prt00e.txt", $e0), @("prt00f.txt", $f0))) {
    Write-Host "=== $($p[0]) (new) ==="
    docker exec $Container sh -c "tail -c +$($p[1] + 1) /tk4-/prt/$($p[0])"
}
if (-not $ended) {
    Write-Warning "job did not report ENDED within $TimeoutSec s. Not resubmitting."
    exit 2
}
