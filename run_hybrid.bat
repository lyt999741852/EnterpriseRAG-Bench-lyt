@echo off
REM ============================================================
REM EnterpriseRAG-Bench Hybrid Baseline (BM70% + Dense30%)
REM Reuses existing index cache -- no rebuild needed.
REM ============================================================
cd /d D:\EnterpriseRAG-Bench
if %ERRORLEVEL% NEQ 0 (echo FAILED: Cannot enter project dir & pause & exit /b 1)

echo ============================================================
echo [1/2] Checking environment...
echo ============================================================
if "%DEEPSEEK_API_KEY%"=="" (
    echo ERROR: DEEPSEEK_API_KEY environment variable is not set.
    echo Set it via: set DEEPSEEK_API_KEY=your-key
    echo Or create a .env file and load it before running.
    pause & exit /b 1
)

echo.
echo ============================================================
echo [2/2] Running pipeline (Hybrid baseline)...
echo ============================================================
python -m src.pipeline configs/hybrid.yaml
if %ERRORLEVEL% NEQ 0 (echo FAILED: pipeline error & pause & exit /b 1)

echo.
echo ============================================================
echo SUCCESS! Check outputs\baseline_hybrid\
echo ============================================================
pause
