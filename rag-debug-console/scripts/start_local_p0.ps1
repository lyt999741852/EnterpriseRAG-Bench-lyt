$ErrorActionPreference = "Stop"
$consoleRoot = Split-Path -Parent $PSScriptRoot
Set-Location $consoleRoot
python -m local_service.server --host 127.0.0.1 --port 8091
