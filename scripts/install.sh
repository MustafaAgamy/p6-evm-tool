#!/usr/bin/env bash
# Sets up everything needed to run this tool on Linux/macOS.
#
# - cli.py (text/CSV report) needs nothing beyond a plain Python 3 install.
# - generate_report.py (PDF report) additionally needs a Chromium/Chrome
#   binary for the HTML -> PDF step; this script fetches one via Playwright
#   so you don't have to track down a system Chrome install yourself.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Error: $PYTHON_BIN not found. Install Python 3.9+ first (python.org, or your OS package manager)." >&2
    exit 1
fi

echo "Using $($PYTHON_BIN --version)"

echo "Creating virtual environment in .venv ..."
"$PYTHON_BIN" -m venv .venv

# shellcheck disable=SC1091
source .venv/bin/activate

echo "Installing Python dependencies (playwright, for the PDF step) ..."
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

echo "Downloading a Chromium build for PDF rendering ..."
python -m playwright install chromium

cat <<'EOF'

Setup complete.

Every time you use the tool, activate the virtual environment first:
    source .venv/bin/activate

Then run either:
    python cli.py <schedule.xml> [--overrides overrides.json] [--out activities.csv]
    python generate_report.py <schedule.xml> --out report.pdf [--overrides overrides.json]
EOF
