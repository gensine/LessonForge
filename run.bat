@echo off
REM LessonForge — Quick Start Script for Windows
REM =============================================

echo.
echo  🎓 LessonForge — AI-Powered Lesson Creator
echo  ============================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found. Install Python 3.11+ first.
    exit /b 1
)

REM Check venv
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt --quiet

REM Check .env
if not exist ".env" (
    echo.
    echo ⚠️  No .env file found!
    echo    Copy .env.example to .env and fill in your API keys:
    echo    copy .env.example .env
    echo.
    copy .env.example .env
    echo Created .env from .env.example — please edit it with your API keys.
    echo.
)

echo.
echo Starting LessonForge...
echo.
streamlit run app.py

