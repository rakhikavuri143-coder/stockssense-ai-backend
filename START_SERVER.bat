@echo off
title StockSense AI — Indian Market Agent
color 0A
echo.
echo  ==============================================
echo     StockSense AI — Nifty 50 Trading Agent
echo  ==============================================
echo.

cd /d "E:\ricks ai agent"

echo Clearing any old process running on port 8000...
powershell -Command "Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue).OwningProcess -Force -ErrorAction SilentlyContinue" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
timeout /t 2 >nul

echo.
echo Starting server on http://localhost:8000
echo Open on Mobile: Check your local IP using ipconfig
echo.

set PYTHONUTF8=1
call .venv\Scripts\activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

pause

