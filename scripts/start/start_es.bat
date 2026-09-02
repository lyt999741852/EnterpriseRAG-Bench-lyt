@echo off
REM ============================================================
REM EnterpriseRAG-Bench: Start Elasticsearch via Docker Compose
REM Prerequisites: Docker Desktop running, docker CLI in PATH
REM ============================================================
cd /d D:\EnterpriseRAG-Bench

echo ============================================================
echo Checking Docker...
echo ============================================================
docker --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: docker CLI not found in PATH.
    echo Make sure Docker Desktop is running and docker is in your PATH.
    pause & exit /b 1
)
docker info >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Docker engine is not responding.
    echo Wait for Docker Desktop to fully start, then try again.
    pause & exit /b 1
)
echo Docker is ready.

echo.
echo ============================================================
echo Pulling ES image and starting container...
echo ============================================================
docker compose up -d
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: docker compose failed.
    pause & exit /b 1
)

echo.
echo ============================================================
echo Waiting for ES health check (green)...
echo ============================================================
:wait_es
curl -s http://localhost:9200/_cluster/health >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo ES is ready!
) else (
    timeout /t 5 /nobreak >nul
    goto wait_es
)

echo.
echo ============================================================
echo ES cluster health:
echo ============================================================
curl -s http://localhost:9200/_cluster/health
echo.

echo.
echo ============================================================
echo Elasticsearch is running at http://localhost:9200
echo ============================================================
echo.
echo Useful commands:
echo   docker compose ps          - check container status
echo   docker compose logs -f     - follow logs
echo   docker compose down        - stop and remove
echo   docker compose down -v     - stop and delete data volume
echo.
pause
