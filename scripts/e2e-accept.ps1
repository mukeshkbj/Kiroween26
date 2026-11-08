<#
.SYNOPSIS
  Run the integrator acceptance conversation N times in a row against a fresh stack each time.

.DESCRIPTION
  For each run: stop any agent, start a fresh `python -m seance_agent` (scripted provider,
  SEANCE_ALLOW_COMMIT=1, its own audit log), wait for /api/health, run scripts/e2e-accept.mjs.
  The web dev server (VITE_MODE=live) is started once and kept. Nothing live is touched: the
  only app driven is the fake (kind "fake"). At the end everything this script started is
  stopped and both ports are checked closed.
  Run from the worktree that has agent/.venv and web/node_modules (normally the integration one).

.EXAMPLE
  powershell -File scripts/e2e-accept.ps1 -Runs 3
#>
param([int]$Runs = 3, [string]$OutDir = (Join-Path $env:TEMP 'gss-accept'))

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root 'agent/.venv/Scripts/python.exe'
if (-not (Test-Path $py)) { Write-Host "FAIL: $py missing"; exit 2 }
if (-not (Test-Path (Join-Path $root 'web/node_modules'))) { Write-Host 'FAIL: web/node_modules missing (npm ci in web/)'; exit 2 }

function Stop-Agents {
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'seance_agent' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
function Wait-Http($url, $secs) {
  for ($i = 0; $i -lt $secs; $i++) {
    try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 2 | Out-Null; return $true } catch { Start-Sleep 1 }
  }
  return $false
}

New-Item -ItemType Directory -Force $OutDir | Out-Null
$web = $null
if (-not (Wait-Http 'http://127.0.0.1:5173/' 1)) {
  $env:VITE_MODE = 'live'; $env:VITE_AGENT_URL = 'http://127.0.0.1:8000'
  $web = Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', 'npx --no-install vite --port 5173 --strictPort --host 127.0.0.1' `
    -WorkingDirectory (Join-Path $root 'web') -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $OutDir 'web.out') -RedirectStandardError (Join-Path $OutDir 'web.err')
  if (-not (Wait-Http 'http://127.0.0.1:5173/' 60)) { Write-Host 'FAIL: web dev server did not start'; exit 2 }
}

$results = @()
for ($n = 1; $n -le $Runs; $n++) {
  Stop-Agents; Start-Sleep 2
  $env:LLM_PROVIDER = 'scripted'; $env:SEANCE_ALLOW_COMMIT = '1'
  $env:AUDIT_LOG_PATH = "docs/audit/accept-$(Get-Date -Format yyyyMMdd-HHmmss)-run$n.jsonl"
  Start-Process -FilePath $py -ArgumentList '-m', 'seance_agent' -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $OutDir "agent-run$n.out") -RedirectStandardError (Join-Path $OutDir "agent-run$n.err") | Out-Null
  if (-not (Wait-Http 'http://127.0.0.1:8000/api/health' 30)) { $results += "run ${n}: FAIL agent did not start"; continue }
  $shots = Join-Path $OutDir "run$n"
  $line = node (Join-Path $root 'scripts/e2e-accept.mjs') --shots $shots 2>&1 | Select-Object -Last 1
  $ok = $LASTEXITCODE -eq 0
  $results += "run ${n}: $(if ($ok) { 'PASS' } else { 'FAIL' })  $line"
}

Stop-Agents
if ($web) {
  # Kill the whole tree we started (cmd -> npx -> node vite); matching on the command line misses the
  # node child, which then keeps the redirected output pipe open and hangs the caller.
  & taskkill.exe /PID $web.Id /T /F 2>&1 | Out-Null
  $listener = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
  if ($listener) { Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue }
}
Start-Sleep 2
$results | ForEach-Object { Write-Host $_ }
$open = @(8000, 5173 | Where-Object { Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue })
Write-Host "ports still listening after cleanup: $(if ($open.Count) { $open -join ',' } else { 'none' })"
$pass = @($results | Where-Object { $_ -match ': PASS' }).Count
Write-Host "ACCEPTANCE: $pass of $Runs runs passed"
if ($pass -eq $Runs) { exit 0 } else { exit 1 }
