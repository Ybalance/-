@echo off
chcp 65001 >nul
echo Starting Hospital Registration System Backend...
echo Backend will be available at: http://127.0.0.1:50002
cd backend
python app.py
pause
