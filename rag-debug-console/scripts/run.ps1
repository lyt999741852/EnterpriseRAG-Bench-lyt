$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
Set-Location $appRoot
python -m backend.app.server --host 127.0.0.1 --port 8090
