#!/usr/bin/env bash
# Interactive wrapper: prompts for the inputs instead of requiring
# command-line flags. Run this after scripts/install.sh has been run once.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -d .venv ]; then
    echo "No .venv found -- run scripts/install.sh first." >&2
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

read -rp "Path to the P6 XML schedule file: " XML_FILE
if [ ! -f "$XML_FILE" ]; then
    echo "Error: file not found: $XML_FILE" >&2
    exit 1
fi

read -rp "Path to an overrides JSON file (leave blank if none): " OVERRIDES
read -rp "Output PDF path [report.pdf]: " OUT_PDF
OUT_PDF="${OUT_PDF:-report.pdf}"

ARGS=("$XML_FILE" --out "$OUT_PDF")
if [ -n "$OVERRIDES" ]; then
    if [ ! -f "$OVERRIDES" ]; then
        echo "Error: overrides file not found: $OVERRIDES" >&2
        exit 1
    fi
    ARGS+=(--overrides "$OVERRIDES")
fi

python generate_report.py "${ARGS[@]}"
