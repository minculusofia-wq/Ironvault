#!/bin/bash
# IRONVAULT Trading Bot - Launch Script

cd "$(dirname "$0")"

# Check for virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    /usr/local/bin/python3.13 -m venv venv
    source venv/bin/activate
    pip install PySide6
else
    source venv/bin/activate
fi

echo "🏦 Launching IRONVAULT Trading Bot..."
python main.py
