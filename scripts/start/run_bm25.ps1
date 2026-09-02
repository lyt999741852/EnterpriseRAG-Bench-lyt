# EnterpriseRAG-Bench BM25 Baseline Runner
Set-Location D:\EnterpriseRAG-Bench

Write-Host "============================================================"
Write-Host "[1/3] Installing dependencies..."
Write-Host "============================================================"
pip install numpy pyyaml rank-bm25 -q

Write-Host ""
Write-Host "============================================================"
Write-Host "[2/3] Checking environment..."
Write-Host "============================================================"
if (-not $env:DEEPSEEK_API_KEY) {
    Write-Host "ERROR: DEEPSEEK_API_KEY environment variable is not set." -ForegroundColor Red
    Write-Host 'Set it via: $env:DEEPSEEK_API_KEY = "your-key"'
    Write-Host "Or create a .env file and load it before running."
    pause; exit 1
}

Write-Host ""
Write-Host "============================================================"
Write-Host "[3/3] Running pipeline (BM25 baseline)..."
Write-Host "============================================================"
python -m src.pipeline configs/default.yaml

Write-Host ""
Write-Host "============================================================"
Write-Host "Done! Check outputs\baseline_bm25\"
Write-Host "============================================================"
