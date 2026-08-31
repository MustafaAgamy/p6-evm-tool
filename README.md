# Controlyx

Computes Delay, Planned/Earned Value, SPI, CPI, and category-level Planned% / Actual%
from a Primavera P6 Professional XML export, and generates a one-page PDF weekly report.

Two ways to use it:

| Mode | Best for |
|------|----------|
| **Desktop app** (`.exe`) | Project controls engineers — double-click, no setup |
| **CLI** | Power users / scripting / CI |

---

## Desktop App (recommended)

### Option A — Download the `.exe`

Download `Controlyx.exe` from [Releases](../../releases) and double-click it.
No Python, no installation required. Chrome must be installed for PDF export.

### Option B — Run from source

```powershell
pip install -r requirements.txt
python app.py
```

### Option C — Build the `.exe` yourself

```powershell
pip install pyinstaller
pyinstaller controlyx.spec
# Output: dist\Controlyx.exe
```

### Using the app

1. Click **Browse File** or drag-and-drop a P6 XML export onto the window.
2. Results appear inline: 6 KPI tiles + category progress bars.
3. Click **Generate PDF Report** to save a one-page PDF.
4. The **Recent Projects** table shows the last 10 imports — click **Open** to re-load any of them.
   Files are cached locally so they re-open even if the original has been moved or deleted.

---

## CLI

### One-time setup

```bash
# Mac / Linux
scripts/install.sh

# Windows PowerShell
scripts\install.ps1
# (if blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)
```

This creates a `.venv` and downloads Chromium for PDF rendering.

### Usage

Text / CSV summary (no PDF, no Chromium needed):
```bash
python cli.py path/to/schedule.xml
python cli.py path/to/schedule.xml --overrides overrides.json --out activities.csv
```

PDF report:
```bash
python generate_report.py path/to/schedule.xml --out report.pdf
python generate_report.py path/to/schedule.xml --overrides overrides.json --out report.pdf
```

Interactive scripts (prompts for all inputs):
```bash
scripts/run_report.sh      # Mac / Linux
scripts\run_report.ps1     # Windows
```

---

## Configuration

**`config.json`** — defines progress categories, their weights, and WBS name matching.
Edit `weight` values or `wbs_match` strings to match a different project's structure.
Weights must sum to 1.0.

**Overrides file** (optional) — for categories tracked manually rather than in P6:
```json
{
    "Phase II Design": {"planned_pct": 0.81, "actual_pct": 0.09}
}
```
Pass via `--overrides` (CLI) or the app reads `overrides_path` from the parse request.
See `sample_overrides.json` for a working example.

---

## Local data storage

The app stores data locally — nothing is sent to any server.

| What | Where |
|------|-------|
| Project metrics DB | `%APPDATA%\Controlyx\controlyx.db` |
| Cached XML copies | `%APPDATA%\Controlyx\schedules\` |

Each Windows user account has its own isolated folder. Cached XMLs are capped at 20 files;
older ones are deleted automatically. To clear all app data, delete the `Controlyx` folder
from `%APPDATA%`.

---

## What the report does NOT include

Only data derivable from the P6 schedule is computed: Delay / Duration Status,
Planned Value, Earned Value, SPI, CPI, and category-level Planned% / Actual%.

Invoice Log, Manpower & Equipment, Procurement Status, Area of Concern, and
Progress Photos require data outside the P6 export and are out of scope.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "No Chrome/Chromium found" | Install Google Chrome, or run the installer (`scripts/install.*`) |
| Numbers look off | Check `config.json` `wbs_match` strings match your project's WBS names |
| CPI shows ≈ 1 always | P6 has AutoComputeActuals enabled — AC is derived from PV, not real cost data |
| Recent project won't open | Original file was deleted and no cached copy exists — re-import the file |
| Want to reset all history | Delete `%APPDATA%\Controlyx\` folder |
