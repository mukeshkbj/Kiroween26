#!/bin/sh
# Demo readiness check (legacy-environment 7.1): menu reachable and a seed
# policy lookup returns data from the COBOL on TK4-. POSIX wrapper around
# healthcheck.py; on Windows use healthcheck.ps1 or run the .py directly.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
py="$here/../mcp-server/.venv/Scripts/python.exe"
[ -x "$py" ] || py="$here/../mcp-server/.venv/bin/python"
[ -x "$py" ] || py="python"
exec "$py" "$here/healthcheck.py" "$@"
