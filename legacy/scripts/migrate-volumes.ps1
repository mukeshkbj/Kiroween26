<#
.SYNOPSIS
  One-time migration of gss-legacy's anonymous Docker volumes to named volumes,
  with a clean MVS shutdown, a tarball backup and a rollback container.
.DESCRIPTION
  The base image declares /tk4-/dasd (all MVS datasets), conf, local_conf,
  local_scripts, jcl, prt and pch as anonymous volumes, so `docker compose down`
  followed by `up` would start an empty TK4-. This script:
    1. refuses if a live explorer or the stand-in is still running;
    2. disables the restart policy, then shuts TK4- down cleanly through the
       Hercules console (`script scripts/shutdown`: JES2 stop, quiesce,
       power off). Hercules exits by itself; we wait for it and never force it;
    3. backs up every anonymous volume as a .tgz (plus sha1 manifests) into
       -BackupDir, read-only, using the gss-legacy:local image (no image pulls);
    4. copies each volume into a named volume gss-<name> and checks that the
       sha1 manifests match file for file;
    5. renames the old container to gss-legacy-pre-migration. That is the
       rollback, because its anonymous volumes are untouched;
    6. `docker compose up -d` with the named volumes (legacy/docker-compose.yml).
  The tk4-/log spool stays anonymous: the image declares it with a relative
  path and it holds only the console log.
  Rollback: docker compose -f legacy/docker-compose.yml down;
            docker rename gss-legacy-pre-migration gss-legacy; docker start gss-legacy
.EXAMPLE
  powershell -File legacy/scripts/migrate-volumes.ps1 -BackupDir legacy/backup/20261106
#>
param(
    [Parameter(Mandatory)][string]$BackupDir,
    [string]$Container = "gss-legacy",
    [int]$ConsolePort = 8038,
    [int]$ShutdownTimeoutSec = 420
)
$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "../..")
$image = "gss-legacy:local"
$names = @{ "/tk4-/dasd" = "dasd"; "/tk4-/conf" = "conf"; "/tk4-/local_conf" = "local_conf";
            "/tk4-/local_scripts" = "local_scripts"; "/tk4-/jcl" = "jcl"; "/tk4-/prt" = "prt"; "/tk4-/pch" = "pch" }

function Say($m) { Write-Host "[migrate] $m" }

# 1. preconditions -------------------------------------------------------------
$busy = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'live_explore|seance_spirit|seance_standin' }
if ($busy) { throw "a live explorer or the stand-in is running (pids $($busy.ProcessId -join ',')); stop it first" }
if ((docker inspect $Container --format "{{.State.Running}}") -ne "true") { throw "$Container is not running" }
if (docker ps -a --format "{{.Names}}" | Where-Object { $_ -eq "$Container-pre-migration" }) { throw "$Container-pre-migration already exists; already migrated?" }
$mounts = docker inspect $Container --format '{{range .Mounts}}{{.Name}}|{{.Destination}}|{{.Type}}{{println}}{{end}}' |
    Where-Object { $_ } | ForEach-Object { $p = $_ -split '\|'; [pscustomobject]@{ Vol = $p[0]; Dest = $p[1]; Type = $p[2] } }
$todo = $mounts | Where-Object { $names.ContainsKey($_.Dest) }
if ($todo.Count -ne $names.Count) { throw "expected $($names.Count) mounts, found $($todo.Count): $($todo.Dest -join ', ')" }
New-Item -ItemType Directory -Force $BackupDir | Out-Null
$bk = (Resolve-Path $BackupDir).Path

# 2. clean shutdown ------------------------------------------------------------
docker update --restart=no $Container | Out-Null
Say "restart policy off; issuing TK4- shutdown (script scripts/shutdown)"
curl.exe -s -m 15 --http0.9 -d "command=$([uri]::EscapeDataString('script scripts/shutdown'))&send=Send" `
    "http://localhost:$ConsolePort/cgi-bin/tasks/syslog" | Out-Null
$deadline = (Get-Date).AddSeconds($ShutdownTimeoutSec)
while ((docker inspect $Container --format "{{.State.Running}}") -eq "true") {
    if ((Get-Date) -gt $deadline) {
        docker update --restart=unless-stopped $Container | Out-Null
        throw "TK4- did not shut down within $ShutdownTimeoutSec s; NOT forcing it. Restart policy restored; check the console."
    }
    Start-Sleep 5
}
Say "TK4- stopped cleanly (exit code $(docker inspect $Container --format '{{.State.ExitCode}}'))"

# 3. backup + 4. copy into named volumes --------------------------------------
foreach ($m in $todo) {
    $n = $names[$m.Dest]; $named = "gss-$n"
    Say "backup $($m.Dest) ($($m.Vol.Substring(0,12))) -> $n.tgz"
    docker run --rm --entrypoint sh -v "$($m.Vol):/from:ro" -v "${bk}:/bk" $image -c `
        "cd /from && tar czf /bk/$n.tgz . && find . -type f -exec sha1sum {} + | sort -k2 > /bk/$n.sha1" | Out-Null
    if ($LASTEXITCODE) { throw "backup of $n failed" }
    docker volume create $named | Out-Null
    docker run --rm --entrypoint sh -v "$($m.Vol):/from:ro" -v "${named}:/to" -v "${bk}:/bk" $image -c `
        "cp -a /from/. /to/ && cd /to && find . -type f -exec sha1sum {} + | sort -k2 > /bk/$n.named.sha1" | Out-Null
    if ($LASTEXITCODE) { throw "copy of $n failed" }
    if ((Get-FileHash "$bk/$n.sha1").Hash -ne (Get-FileHash "$bk/$n.named.sha1").Hash) { throw "sha1 manifest mismatch for $n" }
    $files = (Get-Content "$bk/$n.sha1").Count
    Say "  $named verified: $files files identical"
}
"$(Get-Date -Format o) migrated $($todo.Count) volumes from $Container; old container kept as $Container-pre-migration" |
    Set-Content "$bk/MIGRATION.txt"
$todo | ForEach-Object { "$($_.Dest) $($_.Vol) -> gss-$($names[$_.Dest])" } | Add-Content "$bk/MIGRATION.txt"

# 5. keep the old container as rollback, 6. recreate with named volumes -------
docker rename $Container "$Container-pre-migration"
Say "old container renamed to $Container-pre-migration (rollback)"
Push-Location $repo
# docker writes progress ("legacy Built") to stderr; under Windows PowerShell 5
# with ErrorActionPreference=Stop that is a terminating error, so relax it here
# and judge by the exit code only.
$ErrorActionPreference = "Continue"
try { docker compose -f legacy/docker-compose.yml up -d --build 2>&1 | ForEach-Object { "  $_" } } finally { Pop-Location }
$rc = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($rc) { throw "docker compose up failed (rc=$rc); roll back as described in the header" }
$new = docker inspect $Container --format '{{range .Mounts}}{{.Name}}={{.Destination}} {{end}}'
Say "new container mounts: $new"
Say "done. Wait for IPL (~1 min), then run setup-app, the health check and the demo path."
