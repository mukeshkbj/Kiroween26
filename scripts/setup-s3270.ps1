<#
.SYNOPSIS
  Downloads the official x3270 suite (includes s3270) Windows noinstall ZIP
  and extracts s3270.exe into .tools/.

.DESCRIPTION
  s3270 is the script-mode (display-less) 3270 client used by the
  screen-bridge Session layer. It is part of the x3270 suite, distributed
  under a BSD-style licence. This script downloads the stable Windows
  noinstall ZIP from SourceForge, verifies the SHA-256, and extracts the
  binaries into the repo-local .tools/ directory.

  The x3270 suite: https://x3270.bgp.nu
  SourceForge:      https://sourceforge.net/projects/x3270/

.NOTES
  Run from the repo root:  powershell -ExecutionPolicy Bypass -File scripts/setup-s3270.ps1
  Re-run is safe — skips if s3270.exe already present.
#>

$ErrorActionPreference = "Stop"

# --- config ---------------------------------------------------------------
$version      = "4.5ga6"
$arch         = "64"          # "64" or "32"
$zipName      = "wc3270-$version-noinstall-$arch.zip"
$expectedHash = "eb3a7a6aacaa769f00676ca56a5f1718b9068f359a96bdf26477499e4aed7468"
$mirrorUrl    = "https://x3270.bgp.nu/download/wc3270/$version/$zipName"
$sfUrl        = "https://sourceforge.net/projects/x3270/files/wc3270/$version/$zipName/download"

# --- paths ----------------------------------------------------------------
$repoRoot     = Split-Path -Parent $PSScriptRoot
$toolsDir     = Join-Path $repoRoot ".tools"
$zipPath      = Join-Path $toolsDir $zipName
$s3270Exe     = Join-Path $toolsDir "s3270.exe"

# --- main -----------------------------------------------------------------

if (-not (Test-Path $toolsDir)) {
    New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null
}

if (Test-Path $s3270Exe) {
    Write-Host "s3270.exe already present at $s3270Path — nothing to do." -ForegroundColor Green
    return
}

Write-Host "Downloading $zipName …" -ForegroundColor Cyan
try {
    Invoke-WebRequest -Uri $mirrorUrl -OutFile $zipPath -UseBasicParsing
} catch {
    Write-Host "Mirror failed ($($_.Exception.Message)); trying SourceForge …" -ForegroundColor Yellow
    Invoke-WebRequest -Uri $sfUrl -OutFile $zipPath -UseBasicParsing
}

# verify hash
$actualHash = (Get-FileHash $zipPath -Algorithm SHA256).Hash.ToLower()
if ($actualHash -ne $expectedHash) {
    Write-Host "SHA-256 mismatch!"                                       -ForegroundColor Red
    Write-Host "  expected: $expectedHash"                               -ForegroundColor Red
    Write-Host "  actual:   $actualHash"                                 -ForegroundColor Red
    Remove-Item $zipPath -Force
    throw "Download integrity check failed"
}
Write-Host "SHA-256 verified." -ForegroundColor Green

Write-Host "Extracting to .tools/ …" -ForegroundColor Cyan
Expand-Archive -Path $zipPath -DestinationPath $toolsDir -Force

# the noinstall ZIP may extract into a subdirectory — find s3270.exe
if (-not (Test-Path $s3270Exe)) {
    $found = Get-ChildItem -Path $toolsDir -Recurse -Filter "s3270.exe" | Select-Object -First 1
    if ($found) {
        Copy-Item $found.FullName $s3270Exe -Force
        # also copy any sibling DLLs s3270 needs
        $dlls = Get-ChildItem -Path (Split-Path $found.FullName) -Filter "*.dll"
        foreach ($dll in $dlls) {
            Copy-Item $dll.FullName $toolsDir -Force
        }
    } else {
        Remove-Item $zipPath -Force
        throw "s3270.exe not found in archive"
    }
}

Remove-Item $zipPath -Force
Write-Host "s3270.exe installed at $s3270Exe" -ForegroundColor Green
