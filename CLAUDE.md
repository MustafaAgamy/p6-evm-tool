# P6 EVM Tool — Project Brain

## What this is

A desktop app (and CLI) that parses Primavera P6 XML exports, computes EVM metrics
(Planned Value, Earned Value, SPI, CPI, Delay in days, category-level progress), and
generates a one-page PDF weekly report. Distributed as a standalone `.exe` — no Python
required on the target machine.

---

## Architecture

| Layer | File(s) | Role |
|-------|---------|------|
| **Entry point** | `app.py` | PyWebView window + native file-picker `Api` |
| **HTTP server** | `server.py` | stdlib `http.server` on a random port; injects port into HTML |
| **UI** | `ui/index.html`, `ui/style.css`, `ui/app.js` | Single-page app inside the WebView |
| **Parser** | `p6_evm/parser.py` | Parses P6 XML → `ScheduleData` |
| **Metrics** | `p6_evm/metrics.py` | `compute(data, config, overrides)` → EVM dict |
| **Report** | `p6_evm/report.py` | `render_html(result, meta)` → HTML string; Chrome headless → PDF |
| **CLI** | `cli.py` | Terminal usage (no GUI needed) |
| **Utils** | `utils.py` | `resource_path()` for PyInstaller, `exe_dir()` for history.json |
| **Build** | `p6evm.spec` | PyInstaller spec → `dist/P6EVMTool.exe` |

---

## Key data flow

```
app.py starts server on random port → injects window.__SERVER_PORT__ into index.html
  ↓
User picks XML file (Browse button or drag-drop)
  ↓
POST /api/parse  →  parse_file() + compute()  →  JSON result (records stripped)
  ↓
renderResults() fills KPI tiles + category progress bars inline
  ↓
POST /api/report  →  re-parses XML → render_html() → Chrome headless → PDF saved
```

---

## API routes (server.py)

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/` | — | `ui/index.html` with `window.__SERVER_PORT__` injected |
| GET | `/ui/*` | — | Static CSS / JS |
| GET | `/api/history` | — | JSON array of last 10 imports |
| POST | `/api/parse` | `{path, overrides_path}` | `{ok, result}` |
| POST | `/api/report` | `{xml_path, output_path, overrides_path}` | `{ok}` or `{ok, error}` |

---

## compute() return shape (metrics.py)

```python
{
  'data_date':          datetime,
  'categories':         {name: {weight, planned_pct, actual_pct, bac, ac, activity_count, overridden}},
  'overall_planned_pct': float,
  'overall_actual_pct':  float,
  'pv': float, 'ev': float, 'ac': float,
  'spi': float|None, 'cpi': float|None,
  'variance': float,
  'delay_days': int|None,
  'records': list,   # stripped by server before JSON — do not expose to UI
}
```

`activity_count`, `calendar_count`, `project_name` are added by `_handle_parse()` from the parsed `ScheduleData`.

---

## Theme system (CSS)

`:root` = dark default. `:root.light` = light override (set by JS on `<html>`). Sidebar stays dark in both modes. `localStorage` key: `p6_evm_theme`. Default: `'light'`.

---

## PyInstaller build

```powershell
pip install pyinstaller
pyinstaller p6evm.spec
# → dist\P6EVMTool.exe
```

Data bundled: `ui/`, `p6_evm/`, `config.json`. `resource_path()` in `utils.py` resolves paths correctly in both dev and bundle.

---

## PDF generation

`/api/report` re-parses the XML (needs full `ScheduleData` for `baseline_by_id`), calls `render_html()`, writes a temp HTML file, then spawns Chrome headless. Chrome is located via Playwright's bundled Chromium first, then Windows install paths. End users need Chrome installed (or Playwright Chromium in the `.exe` bundle).

---

## history.json

Saved next to the `.exe` (prod) or project root (dev) — user-specific, gitignored. Stores last 10 imports: `path`, `filename`, `data_date`, `delay`, `spi`, `construction_pct`.

---

## Do not touch

- `p6_evm/` — core computation modules; changes here break CLI + GUI
- The `records` key is stripped server-side — never include it in JSON responses (large + non-serialisable)
- `server.py` port injection: `window.__SERVER_PORT__` must be set before `app.js` runs
