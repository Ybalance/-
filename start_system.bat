@echo off
chcp 65001 >nul
title Hospital Registration System - Startup Script
color 0A

echo ========================================
echo    Hospital Registration System
echo ========================================
echo.
echo Starting backend service...
echo Backend URL: http://127.0.0.1:50002
echo.

cd backend
start "Backend Service" python app.py

echo Waiting for backend to start...
timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo Starting frontend service...
echo Frontend URL: http://localhost:8081
echo ========================================
echo.

cd ..\frontend
start "Frontend Service" python -m http.server 8081

echo.
echo ========================================
echo System startup completed!
echo ========================================
echo.
echo Frontend: http://localhost:8081
echo Backend API: http://127.0.0.1:50002
echo.
echo Test Accounts:
echo Admin: admin/admin123
echo Doctor: doctor1/doctor123
echo Patient: patient1/patient123
echo.
echo Features:
echo   - Database Management
echo   - Conflict Resolution
echo   - Multi-database Sync
echo   - Real-time Updates
echo.
echo Press any key to open browser...
pause >nul

start http://localhost:8081

echo.
echo System is running...
echo Close this window to stop services
echo.
pause
