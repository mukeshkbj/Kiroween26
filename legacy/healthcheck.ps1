<#
.SYNOPSIS
  Demo readiness check (legacy-environment 7.1): is the stand-in serving a
  readable menu, with its keyboard unlocked, backed by the live TK4-?
.DESCRIPTION
  Connects to the stand-in's TN3270 port with the real bridge, waits for a
  stable screen with the keyboard unlocked, and asserts the Main Menu is
  present and a lookup of a seed policy returns data from the COBOL on TK4-.
  Exits 0 when ready, non-zero with a clear message otherwise. Timeout ~6 min
  (the first cold IPL of TK4- can be slow); here the container is assumed up.
.EXAMPLE
  mcp-server/.venv/Scripts/python legacy/healthcheck.py   # the real check
  powershell -File legacy/healthcheck.ps1                  # thin wrapper
#>
param([int]$TimeoutSec = 360)
$ErrorActionPreference = "Stop"
$py = Join-Path $PSScriptRoot "..\mcp-server\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py (Join-Path $PSScriptRoot "healthcheck.py") --timeout $TimeoutSec
exit $LASTEXITCODE
