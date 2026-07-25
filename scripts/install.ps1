# Sets up everything needed to run this tool on Windows.
#
# - cli.py (text/CSV report) needs nothing beyond a plain Python 3 install.
# - generate_report.py (PDF report) additionally needs a Chromium/Chrome
#   binary for the HTML -> PDF step; this script fetches one via Playwright
#   so you don't have to track down a system Chrome install yourself.
#
# Run from PowerShell:  .\scripts\install.ps1
# If script execution is blocked, run once:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

$ErrorActionPreference = "Stop"

Set-Location (Split-Path $PSScriptRoot -Parent)

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
    Write-Error "Python not found. Install Python 3.9+ from python.org first (check 'Add python.exe to PATH' during install)."
    exit 1
}
$pythonExe = $python.Source
Write-Host "Using $pythonExe"
& $pythonExe --version

Write-Host "Creating virtual environment in .venv ..."
& $pythonExe -m venv .venv

$venvPython = ".\.venv\Scripts\python.exe"

Write-Host "Installing Python dependencies (playwright, for the PDF step) ..."
& $venvPython -m pip install --upgrade pip | Out-Null
& $venvPython -m pip install -r requirements.txt

Write-Host "Downloading a Chromium build for PDF rendering ..."
& $venvPython -m playwright install chromium

Write-Host ""
Write-Host "Setup complete."
Write-Host ""
Write-Host "Every time you use the tool, activate the virtual environment first:"
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "Then run either:"
Write-Host "    python cli.py <schedule.xml> [--overrides overrides.json] [--out activities.csv]"
Write-Host "    python generate_report.py <schedule.xml> --out report.pdf [--overrides overrides.json]"
