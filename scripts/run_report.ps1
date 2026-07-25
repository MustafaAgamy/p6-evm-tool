# Interactive wrapper: prompts for the inputs instead of requiring
# command-line flags. Run this after scripts\install.ps1 has been run once.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".venv")) {
    Write-Error "No .venv found -- run scripts\install.ps1 first."
    exit 1
}

$venvPython = ".\.venv\Scripts\python.exe"

$xmlFile = Read-Host "Path to the P6 XML schedule file"
if (-not (Test-Path $xmlFile)) {
    Write-Error "File not found: $xmlFile"
    exit 1
}

$overrides = Read-Host "Path to an overrides JSON file (leave blank if none)"
$outPdf = Read-Host "Output PDF path [report.pdf]"
if ([string]::IsNullOrWhiteSpace($outPdf)) { $outPdf = "report.pdf" }

$argsList = @($xmlFile, "--out", $outPdf)
if (-not [string]::IsNullOrWhiteSpace($overrides)) {
    if (-not (Test-Path $overrides)) {
        Write-Error "Overrides file not found: $overrides"
        exit 1
    }
    $argsList += @("--overrides", $overrides)
}

& $venvPython generate_report.py @argsList
