@echo off
chcp 65001 > nul
title StocksSense AI — Local Live Trader Pro
color 0b
echo ========================================================
echo   ⚡ Starting StocksSense AI Local Live Trader...
echo ========================================================
cd /d "e:\ricks ai agent"

echo Closing any old background local trader processes...
powershell -Command "Get-CimInstance Win32_Process -Filter \"name = 'python.exe'\" | Where-Object { $_.CommandLine -like '*local_trader.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 1 >nul

call .venv\Scripts\activate.bat
python local_trader.py
pause
