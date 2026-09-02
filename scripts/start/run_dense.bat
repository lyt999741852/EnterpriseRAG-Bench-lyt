@echo off
REM ============================================================
REM EnterpriseRAG-Bench Dense Embedding Baseline
REM Fill configs/dense.yaml with your embedding API before running.
REM ============================================================
cd /d D:\EnterpriseRAG-Bench
if %ERRORLEVEL% NEQ 0 (echo FAILED: Cannot enter project dir & pause & exit /b 1)

echo ============================================================
echo [1/3] Installing dependencies...
echo ============================================================
pip install faiss-cpu -q
if %ERRORLEVEL% NEQ 0 (echo FAILED: pip install faiss-cpu & pause & exit /b 1)

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
REM Embedding: all-MiniLM-L6-v2 (local, free). First run downloads ~80MB model.

echo.
echo ============================================================
echo [3/3] Running pipeline (Dense baseline)...
echo ============================================================
python -m src.pipeline configs/dense.yaml
if %ERRORLEVEL% NEQ 0 (echo FAILED: pipeline error & pause & exit /b 1)

echo.
echo ============================================================
echo SUCCESS! Check outputs\baseline_dense\
echo ============================================================
pause
