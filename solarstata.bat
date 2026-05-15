@echo off
REM SolarSTATA Windows launcher — double-click to boot the app.
REM
REM Boots backend (FastAPI on :8000) and frontend (Vite on :5173) in two
REM separate cmd windows, then opens the browser. Close either window to
REM stop the corresponding server.
REM
REM The earlier PowerShell-based version of this file crashed with
REM "& was unexpected at this time." on a fresh Windows clone. cmd /k
REM with explicit `&&` joins (no escaping inside double quotes) is the
REM reliable pattern.

setlocal

cd /d "%~dp0"

echo.
echo   S o l a r S T A T A   v 3 . 0
echo   -------------------------------
echo.

REM ---- First-run bootstrap: create .venv if missing ----
if not exist .venv (
    where python >nul 2>&1
    if errorlevel 1 (
        echo   [x] python not found on PATH.
        echo       Install Python 3.11+ from https://python.org and re-run.
        pause
        exit /b 1
    )
    echo   First run - creating .venv and installing backend deps...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    python -m pip install -e backend
    call .venv\Scripts\deactivate.bat 2>nul
)

REM ---- First-run bootstrap: install frontend deps if missing ----
if not exist frontend\node_modules (
    where npm >nul 2>&1
    if errorlevel 1 (
        echo   [x] npm not found on PATH.
        echo       Install Node 18+ from https://nodejs.org and re-run.
        pause
        exit /b 1
    )
    echo   Installing frontend dependencies ^(this can take a minute^)...
    pushd frontend
    call npm install --no-audit --no-fund
    popd
)

REM ---- Activate venv so child cmd windows inherit Python on PATH ----
call .venv\Scripts\activate.bat

echo   -^> Starting FastAPI on http://localhost:8000 ^(new window^)
start "SolarSTATA backend"  cmd /k "cd /d %~dp0 && .venv\Scripts\python.exe -m uvicorn solarstata.main:app --host 127.0.0.1 --port 8000"

timeout /t 3 /nobreak >nul

echo   -^> Starting Vite on http://localhost:5173 ^(new window^)
start "SolarSTATA frontend" cmd /k "cd /d %~dp0\frontend && npm run dev -- --host 127.0.0.1 --port 5173"

timeout /t 5 /nobreak >nul

echo   Opening browser...
start "" "http://localhost:5173"

echo.
echo   Both servers are running in separate cmd windows.
echo   Close those windows to stop the servers.
echo.

endlocal
