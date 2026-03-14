#!/usr/bin/env bash
set -e

# Navigate to script's directory (handles double-click execution)
cd "$(dirname "$0")"

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║       SEC Filing Research Tool        ║"
echo "  ║            Setup Installer            ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# ── Step 0: Check Git LFS ──
if ! command -v git-lfs &>/dev/null && ! git lfs version &>/dev/null 2>&1; then
    echo ""
    echo "  Git LFS is required to download the pre-built vector index."
    echo ""
    echo "  To install:"
    echo "    macOS:   brew install git-lfs"
    echo "    Linux:   sudo apt install git-lfs"
    echo "    Windows: https://git-lfs.github.com/"
    echo ""
    echo "  After installing, run: git lfs install && git lfs pull"
    echo ""
    [ -t 0 ] && read -p "  Press Enter to exit..."
    exit 1
fi

# Check if LFS files were actually downloaded (not just pointers)
if [ -f "chroma_db/chroma.sqlite3" ]; then
    SIZE=$(wc -c < "chroma_db/chroma.sqlite3" | tr -d ' ')
    if [ "$SIZE" -lt 1000 ]; then
        echo ""
        echo "  Git LFS files not downloaded. Running git lfs pull..."
        git lfs pull
    fi
fi

# ── Step 1: Check Python ──
echo "[1/4] Checking Python installation..."

PY=""
for cmd in python3.11 python3.12 python3.13 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')" 2>/dev/null)
        major=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
        minor=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 8 ]; then
            PY="$cmd"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    echo ""
    echo "  Python 3.8 or higher is required but was not found."
    echo ""
    echo "  To install Python:"
    echo "    macOS:   brew install python@3.11"
    echo "    Windows: https://www.python.org/downloads/"
    echo "    Linux:   sudo apt install python3.11"
    echo ""
    [ -t 0 ] && read -p "  Press Enter to exit..."
    exit 1
fi

echo "  Found Python $ver ($PY)"

# ── Step 2: Virtual environment ──
echo "[2/4] Setting up virtual environment..."

if [ ! -d "venv" ]; then
    $PY -m venv venv
    echo "  Created virtual environment."
else
    echo "  Virtual environment already exists."
fi

source venv/bin/activate

# ── Step 3: Install dependencies ──
echo "[3/4] Installing dependencies (this may take a minute)..."
pip install --upgrade pip -q 2>/dev/null
pip install -r requirements.txt -q 2>/dev/null
echo "  All dependencies installed."

# ── Step 4: Environment config ──
echo "[4/4] Checking configuration..."

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  Created .env configuration file."
fi

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║          Setup Complete!              ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""
echo "  Next steps:"
echo ""
echo "    1. Add your API key to .env"
echo "    2. ./run.sh"
echo ""
echo "  Or manually:"
echo "    source venv/bin/activate"
echo "    python scripts/query.py"
echo ""

[ -t 0 ] && read -p "  Press Enter to close..."
