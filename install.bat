@echo off
REM VocTation Installation Script
REM Sets up Python virtual environment and installs dependencies

echo.
echo ===================================
echo VocTation - Installation Script
echo ===================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

echo [1/6] Python detected. Checking version...
python --version

echo.
echo [2/6] Creating virtual environment...
if not exist venv\ (
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created successfully.
) else (
    echo Virtual environment already exists.
)

echo.
echo [3/6] Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo [4/6] Upgrading pip and installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo [5/6] Creating required folder structure...
if not exist user-data\audio mkdir user-data\audio
if not exist user-data\transcripts mkdir user-data\transcripts
if not exist user-data\outlines mkdir user-data\outlines
if not exist user-data\prompts mkdir user-data\prompts
if not exist models\whisper mkdir models\whisper
if not exist logs mkdir logs

echo Folder structure created.

echo.
echo [6/6] Setting up .env configuration...
if not exist .env (
    copy .env.example .env
    echo Created .env file from .env.example
    echo IMPORTANT: Edit .env and add your GEMINI_API_KEY
) else (
    echo .env file already exists.
)

echo.
echo ===================================
echo Installation Complete!
echo ===================================
echo.
echo Next steps:
echo 1. Edit .env file and add your GEMINI_API_KEY
echo    Get your key at: https://makersuite.google.com/app/apikey
echo 2. Run "run.bat" to start the server
echo 3. Open http://127.0.0.1:8000 in your browser
echo.
pause
