# Thin wrapper: the build logic (compile, allowlist check, fixtures, pin) lives in build.py so there is exactly
# one build path (BMREC-04b). Usage:  .\integrations\bookmap\build.ps1 [--update-pin]
$ErrorActionPreference = 'Stop'
python (Join-Path $PSScriptRoot 'build.py') @args
exit $LASTEXITCODE
