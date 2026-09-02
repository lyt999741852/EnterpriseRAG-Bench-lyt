@echo off
REM ============================================================
REM EnterpriseRAG-Bench Full Corpus (500 questions, 9 sources)
REM Data: corpus/all_documents/
REM ============================================================
cd /d D:\EnterpriseRAG-Bench
if %ERRORLEVEL% NEQ 0 (echo FAILED: Cannot enter project dir & pause & exit /b 1)

if not exist "corpus\all_documents\slack" (
    echo ERROR: corpus\all_documents not found or incomplete
    pause & exit /b 1
)

echo.
echo ============================================================
echo Installing dependencies (fastembed + faiss)...
echo ============================================================
pip install fastembed faiss-cpu -q
if %ERRORLEVEL% NEQ 0 (echo FAILED: pip install & pause & exit /b 1)

echo.
echo ============================================================
echo Checking environment...
echo ============================================================
if "%DEEPSEEK_API_KEY%"=="" (
    echo ERROR: DEEPSEEK_API_KEY environment variable is not set.
    echo Set it via: set DEEPSEEK_API_KEY=your-key
    echo Or create a .env file and load it before running.
    pause & exit /b 1
)

echo.
echo ============================================================
echo Running pipeline (Full corpus, 500 questions, 9 sources)...
echo The run uses manifest checkpoints and resumes completed preprocessing.
echo ============================================================
python -m src.pipeline configs/full.yaml
if %ERRORLEVEL% NEQ 0 (echo FAILED: pipeline error & pause & exit /b 1)

echo.
echo ============================================================
echo SUCCESS! Check outputs\baseline_full\
echo ============================================================
pause
