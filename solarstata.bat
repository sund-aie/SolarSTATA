@echo off
REM SolarSTATA Windows launcher — double-click to boot the app.
REM
REM - Provisions .venv and node_modules on first run.
REM - Starts the FastAPI backend on :8000 and Vite frontend on :5173 in
REM   separate PowerShell windows.
REM - Opens http://localhost:5173 in the default browser.
REM
REM Close either PowerShell window to stop the corresponding server.

setlocal

cd /d "%~dp0"

echo.
echo   S o l a r S T A T A   v 3 . 0
echo   -------------------------------
echo.

REM First-run bootstrap
if not exist .venv (
    where python >nul 2>&1
    if errorlevel 1 (
        echo   [x] python not found. Install Python 3.11+ from python.org.
        pause
        exit /b 1
    )
    echo   First run - creating .venv and installing backend deps...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    python -m pip install -e backend
)

if not exist frontend\node_modules (
    where npm >nul 2>&1
    if errorlevel 1 (
        echo   [x] npm not found. Install Node 18+ from nodejs.org.
        pause
        exit /b 1
    )
    echo   Installing frontend dependencies (this can take a minute)...
    pushd frontend
    call npm install --no-audit --no-fund
    popd
)

echo   -^> Starting FastAPI on http://localhost:8000 (separate window)
start "SolarSTATA backend" powershell -NoExit -Command ^
    "$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe -m uvicorn solarstata.main:app --host 127.0.0.1 --port 8000"

echo   -^> Starting Vite on http://localhost:5173 (separate window)
start "SolarSTATA frontend" powershell -NoExit -Command ^
    "cd frontend; npm run dev -- --host 127.0.0.1 --port 5173"

REM Give Vite a moment to spin up, then open the browser
timeout /t 3 /nobreak >nul
start "" "http://localhost:5173"

echo.
echo   Both servers are running. Close the SolarSTATA backend/frontend
echo   PowerShell windows to stop them.
echo.

endlocal
