@echo off
REM VocTation Server Startup Script

echo.
echo ===================================
echo VocTation - Starting Server
echo ===================================
echo.

REM Check if venv exists
if not exist venv\ (
    echo ERROR: Virtual environment not found
    echo Please run install.bat first
    pause
    exit /b 1
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Check if .env exists
if not exist .env (
    echo WARNING: .env file not found
    echo Copy .env.example to .env and add your API keys
    pause
)

echo Starting VocTation server...
echo.
echo Server will be available at: http://127.0.0.1:8000
echo Press Ctrl+C to stop the server
echo.

REM Run the application
python main.py

pause
