@echo off
REM ============================================================
REM EnterpriseRAG-Bench BM25 Baseline Runner
REM ============================================================
cd /d D:\EnterpriseRAG-Bench
if %ERRORLEVEL% NEQ 0 (echo FAILED: Cannot enter D:\EnterpriseRAG-Bench & pause & exit /b 1)

echo ============================================================
echo [1/3] Installing dependencies...
echo ============================================================
pip install numpy pyyaml rank-bm25 -q
if %ERRORLEVEL% NEQ 0 (echo FAILED: pip install & pause & exit /b 1)

echo.
echo ============================================================
echo [2/3] Checking environment...
echo ============================================================
if "%DEEPSEEK_API_KEY%"=="" (
    echo ERROR: DEEPSEEK_API_KEY environment variable is not set.
    echo Set it via: set DEEPSEEK_API_KEY=your-key
    echo Or create a .env file and load it before running.
    pause & exit /b 1
)

echo.
echo ============================================================
echo [3/3] Running pipeline (BM25 baseline)...
echo ============================================================
python -m src.pipeline configs/default.yaml
if %ERRORLEVEL% NEQ 0 (echo FAILED: pipeline error & pause & exit /b 1)

echo.
echo ============================================================
echo SUCCESS! Check outputs\baseline_bm25\
echo ============================================================
pause
