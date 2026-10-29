@echo off
setlocal
title HydroScan AI Launcher

set "PROJECT_ROOT=D:\HydroScan-AI"
set "FRONTEND_DIR=D:\HydroScan-AI\artifacts\hydroscan-ai"

if not exist "%PROJECT_ROOT%\pnpm-workspace.yaml" (
    echo ERROR: Could not find HydroScan AI at %PROJECT_ROOT%
    echo Edit this file if your project is stored in a different folder.
    pause
    exit /b 1
)

echo Starting HydroScan AI backend...
start "HydroScan AI Backend" cmd /k "cd /d ""%PROJECT_ROOT%"" && pnpm.cmd --filter @workspace/api-server dev"

timeout /t 3 /nobreak >nul

echo Starting HydroScan AI frontend...
start "HydroScan AI Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && set PORT=5173&& set BASE_PATH=/&& set HYDROSCAN_LOCAL_API_TARGET=http://127.0.0.1:8080&& pnpm.cmd dev"

timeout /t 5 /nobreak >nul
start "" "http://localhost:5173/"

echo.
echo HydroScan AI launch commands have been started.
echo Keep both terminal windows open while using the application.
echo If the frontend reports another missing environment variable, share that error.
endlocal
