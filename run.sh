#!/bin/bash
# LessonForge — Quick Start Script for Linux/Mac
# =============================================

echo ""
echo "🎓 LessonForge — AI-Powered Lesson Creator"
echo "============================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Install Python 3.11+ first."
    exit 1
fi

# Check venv
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt --quiet

# Check .env
if [ ! -f ".env" ]; then
    echo ""
    echo "⚠️  No .env file found!"
    echo "   Copy .env.example to .env and fill in your API keys:"
    echo "   cp .env.example .env"
    echo ""
    cp .env.example .env
    echo "Created .env from .env.example — please edit it with your API keys."
    echo ""
fi

echo ""
echo "Starting LessonForge..."
echo ""
streamlit run app.py

