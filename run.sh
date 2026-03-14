#!/usr/bin/env bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "First time? Running setup first..."
    echo ""
    ./setup.sh
fi

source venv/bin/activate

if [ -f "app.py" ]; then
    echo "Launching SEC Filing Research Tool..."
    echo "The app will open in your browser automatically."
    echo ""
    streamlit run app.py
else
    echo "Launching SEC Filing Research Tool (CLI)..."
    echo ""
    python scripts/query.py "$@"
fi
