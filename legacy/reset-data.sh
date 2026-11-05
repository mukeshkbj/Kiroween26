#!/bin/sh
# Restore the 8 seed policies on TK4- (legacy-environment 7.2).
# POSIX wrapper around the PowerShell script that drives the Hercules card
# reader; on Windows use reset-data.ps1 directly.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
pwsh -File "$here/reset-data.ps1" "$@" 2>/dev/null \
  || powershell -File "$here/reset-data.ps1" "$@"
