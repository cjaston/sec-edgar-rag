#!/usr/bin/env bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "First time? Running setup first..."
    echo ""
    ./setup.sh
fi

source venv/bin/activate

if [ "$1" = "--cli" ]; then
    shift
    python scripts/query.py "$@"
elif [ "$1" = "--ui" ] || [ -z "$1" ]; then
    echo ""
    echo "  Launching SEC Filing Research Tool..."
    echo "  The app will open in your browser at http://localhost:8501"
    echo ""
    echo "  Options:"
    echo "    ./run.sh          Open web UI (default)"
    echo "    ./run.sh --cli    Command-line interface"
    echo "    ./run.sh --cli -v CLI with verbose pipeline"
    echo ""
    streamlit run src/ui/app.py --server.headless true
else
    # Pass flags like -v or --role directly to CLI
    python scripts/query.py "$@"
fi
