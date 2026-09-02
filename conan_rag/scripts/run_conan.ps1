$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
python -m src.conan_runner configs/eval_conan_next.yaml
exit $LASTEXITCODE
