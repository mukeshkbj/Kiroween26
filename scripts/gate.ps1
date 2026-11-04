<#
.SYNOPSIS
  Merge gate: run every check that exists for this checkout and print a summary. Exit 1 if any fails.

.DESCRIPTION
  Steps (each skipped with a note if its component is not there yet):
    ownership      scripts/check-ownership.ps1 (agent branches only)
    contracts      generated schemas/examples are fresh and valid (python -m seance_mcp.contracts.*)
    <component>    pytest for bridge, mcp-server, spirit-map, agent: once with a FIXED Hypothesis seed
                   (reproducible) and once with a random one (finds new cases)
    web            tsc --noEmit and vitest --run, if web/package.json exists and node_modules is installed
    mypy           only with -Mypy (tech.md: "mypy-clean where practical")
  Live tests never run here: they need GSS_LIVE_OK and TN3270_HOST (docs/contracts.md section 2.1).

.EXAMPLE
  powershell -File scripts/gate.ps1
  powershell -File scripts/gate.ps1 -Only mcp-server,contracts
#>
param(
  [string[]]$Only = @(),
  [switch]$Mypy,
  [int]$Seed = 20261124
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$results = [ordered]@{}

function Want($name) { return ($Only.Count -eq 0) -or ($Only -contains $name) }
function Note($name, $status, $detail) { $script:results[$name] = @{ status = $status; detail = $detail } }

function Venv-Python($dir) {
  $p = Join-Path $root "$dir/.venv/Scripts/python.exe"
  if (Test-Path $p) { return $p }
  $p = Join-Path $root "$dir/.venv/bin/python"
  if (Test-Path $p) { return $p }
  return $null
}

# Run a native command, show its output, return its exit code (python's stderr banner must not fail us).
function Run($exe, $argList, $cwd) {
  Push-Location $cwd
  try {
    & $exe @argList 2>&1 | ForEach-Object { "$_" } | Out-Host
    return $LASTEXITCODE
  } finally { Pop-Location }
}

$branch = (git branch --show-current).Trim()

if ((Want 'ownership') -and $branch -like 'agent/*') {
  $code = Run 'powershell' @('-NoProfile', '-File', (Join-Path $root 'scripts/check-ownership.ps1'), '-Branch', $branch) $root
  Note 'ownership' ($(if ($code -eq 0) { 'pass' } else { 'FAIL' })) $branch
} elseif (Want 'ownership') { Note 'ownership' 'skip' "branch '$branch' is not an agent branch" }

if (Want 'contracts') {
  $py = Venv-Python 'mcp-server'
  if ($null -eq $py) { Note 'contracts' 'skip' 'mcp-server/.venv missing' }
  else {
    $a = Run $py @('-m', 'seance_mcp.contracts.generate', '--check') (Join-Path $root 'mcp-server')
    $b = Run $py @('-m', 'seance_mcp.contracts.check') (Join-Path $root 'mcp-server')
    Note 'contracts' ($(if ($a -eq 0 -and $b -eq 0) { 'pass' } else { 'FAIL' })) 'fresh + valid'
  }
}

foreach ($comp in 'bridge', 'mcp-server', 'spirit-map', 'agent') {
  if (-not (Want $comp)) { continue }
  $dir = Join-Path $root $comp
  if (-not (Test-Path (Join-Path $dir 'pyproject.toml'))) { Note $comp 'skip' 'not created yet'; continue }
  $py = Venv-Python $comp
  if ($null -eq $py) { Note $comp 'skip' "$comp/.venv missing (create it, see the component README)"; continue }
  $fixed = Run $py @('-m', 'pytest', '-q', "--hypothesis-seed=$Seed") $dir
  $rand = Run $py @('-m', 'pytest', '-q') $dir
  Note $comp ($(if ($fixed -eq 0 -and $rand -eq 0) { 'pass' } else { 'FAIL' })) "fixed seed ${Seed}: exit $fixed; random seed: exit $rand"
  if ($Mypy) {
    $m = Run $py @('-m', 'mypy', 'src') $dir
    Note "$comp mypy" ($(if ($m -eq 0) { 'pass' } else { 'FAIL' })) "exit $m"
  }
}

if (Want 'web') {
  $web = Join-Path $root 'web'
  if (-not (Test-Path (Join-Path $web 'package.json'))) { Note 'web' 'skip' 'not created yet' }
  elseif (-not (Test-Path (Join-Path $web 'node_modules'))) { Note 'web' 'skip' 'run npm ci in web/ first' }
  else {
    $t = Run 'npx' @('--no-install', 'tsc', '--noEmit') $web
    $v = Run 'npx' @('--no-install', 'vitest', '--run') $web
    Note 'web' ($(if ($t -eq 0 -and $v -eq 0) { 'pass' } else { 'FAIL' })) "tsc exit $t; vitest exit $v"
  }
}

Write-Host ''
Write-Host '=== gate summary ==='
$failed = $false
foreach ($k in $results.Keys) {
  $r = $results[$k]
  Write-Host ("{0,-16} {1,-5} {2}" -f $k, $r.status, $r.detail)
  if ($r.status -eq 'FAIL') { $failed = $true }
}
if ($failed) { Write-Host 'GATE: FAIL'; exit 1 }
Write-Host 'GATE: ok'
exit 0
