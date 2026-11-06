<#
.SYNOPSIS
  Shut TK4- (MVS 3.8j) down cleanly and let the gss-legacy container stop.
.DESCRIPTION
  Use this before `docker compose down`, a backup or a host reboot. A plain
  `docker stop` kills Hercules mid-I/O; this runs TK4-'s own sequence on the
  Hercules console (`script scripts/shutdown`: stop JES2, end-of-day, quiesce,
  power off), after which Hercules exits by itself.
  The restart policy is switched off first (otherwise `unless-stopped` would
  restart the container as soon as Hercules exits). `docker compose up -d`
  restores it from the compose file. If MVS does not stop in time, nothing is
  forced: the policy is restored and the script fails.
.EXAMPLE
  powershell -File legacy/scripts/stop-mvs.ps1; docker compose -f legacy/docker-compose.yml down
#>
param([string]$Container = "gss-legacy", [int]$ConsolePort = 8038, [int]$TimeoutSec = 420)
$ErrorActionPreference = "Stop"
if ((docker inspect $Container --format "{{.State.Running}}") -ne "true") { Write-Host "$Container is not running"; return }
$policy = docker inspect $Container --format "{{.HostConfig.RestartPolicy.Name}}"
docker update --restart=no $Container | Out-Null
Write-Host "[stop-mvs] issuing TK4- shutdown (script scripts/shutdown); this takes 1-3 minutes"
curl.exe -s -m 15 --http0.9 -d "command=$([uri]::EscapeDataString('script scripts/shutdown'))&send=Send" `
    "http://localhost:$ConsolePort/cgi-bin/tasks/syslog" | Out-Null
$deadline = (Get-Date).AddSeconds($TimeoutSec)
while ((docker inspect $Container --format "{{.State.Running}}") -eq "true") {
    if ((Get-Date) -gt $deadline) {
        docker update --restart=$policy $Container | Out-Null
        throw "TK4- did not shut down within $TimeoutSec s; NOT forcing it. Restart policy restored ($policy)."
    }
    Start-Sleep 5
}
Write-Host "[stop-mvs] TK4- stopped cleanly (exit code $(docker inspect $Container --format '{{.State.ExitCode}}'))"
