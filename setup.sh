#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "[ERROR] python3 not on PATH"; exit 1; }
if [ ! -x .venv/bin/python ]; then
    echo "[1/3] Creating venv..."
    python3 -m venv .venv
else
    echo "[1/3] venv exists"
fi
. .venv/bin/activate
echo "[2/3] Installing in editable mode..."
pip install --upgrade pip >/dev/null
pip install -e ".[dev]" 2>/dev/null || pip install -e .
echo "[3/3] Smoke tests..."
[ -d tests ] && (pytest -q || echo "[WARN] tests failed") || echo "[skip] no tests/"
echo "Library installed in editable mode."
