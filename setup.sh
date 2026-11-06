#!/usr/bin/env bash
# OctoDesk one-shot setup (macOS/Linux): venv + install + how to launch.
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
. .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -e .
echo ""
echo "🐙 OctoDesk installed. Release the Kraken with:"
echo "   . .venv/bin/activate && octodesk"
echo "   then open http://127.0.0.1:8917"
echo "Offline check any time:  octodesk demo"
