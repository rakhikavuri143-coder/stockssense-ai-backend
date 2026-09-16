@echo off
chcp 65001 > nul
title StocksSense AI — Local Live Trader Pro
color 0b
echo ========================================================
echo   ⚡ Starting StocksSense AI Local Live Trader...
echo ========================================================
cd /d "e:\ricks ai agent"
call .venv\Scripts\activate.bat
python local_trader.py
pause
