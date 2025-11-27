@echo off
chcp 65001 >nul
echo Starting Hospital Registration System Frontend...
echo Frontend will be available at: http://localhost:8081
cd frontend
python -m http.server 8081 --bind 0.0.0.0
pause
