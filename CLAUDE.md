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
| **Database** | `db.py` | SQLite schema, XML caching, all DB read/write operations |
| **Utils** | `utils.py` | `resource_path()` for PyInstaller, `app_data_dir()` / `schedules_dir()` for per-user storage |
| **Build** | `p6evm.spec` | PyInstaller spec → `dist/P6EVMTool.exe` |

---

## Key data flow

```
app.py starts server on random port → injects window.__SERVER_PORT__ into index.html
  ↓
User picks XML file (Browse button or drag-drop)
  ↓
POST /api/parse  →  parse_file() + compute()  →  JSON result (records stripped)
              →  hash_file() dedup → cache_xml() copies to %APPDATA%/schedules/
              →  upsert_project() + insert_snapshot() + insert_metrics() + insert_category_metrics()
  ↓
renderResults() fills KPI tiles + category progress bars inline
  ↓
POST /api/report  →  resolve_xml_path() (original → cached fallback)
              →  re-parses XML → render_html() → Chrome headless → PDF saved
```

---

## API routes (server.py)

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/` | — | `ui/index.html` with `window.__SERVER_PORT__` injected |
| GET | `/ui/*` | — | Static CSS / JS |
| GET | `/api/history` | — | JSON array of last 10 projects (most recent snapshot each) |
| POST | `/api/parse` | `{path, overrides_path}` | `{ok, result, cached_path}` |
| POST | `/api/report` | `{xml_path, cached_path, output_path, overrides_path}` | `{ok}` or `{ok, error}` |

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

## Persistence (db.py)

**DB location:** `%APPDATA%\P6EVMTool\p6evm.db` (Windows) / `~/.p6evmtool/p6evm.db` (Mac/Linux) — one per OS user, gitignored.

**XML cache:** `%APPDATA%\P6EVMTool\schedules\{hash12}_{filename}` — capped at 20 files, oldest deleted on overflow. Dedup by SHA256: importing the same file twice stores one copy.

**Schema:**

```
projects         — one row per unique P6 project (identified by p6_project_id, fallback to name)
snapshots        — one row per import event (original_path, cached_path, file_hash, data_date)
metrics          — EVM numbers per snapshot (pv, ev, ac, spi, cpi, delay_days, overall_pcts)
category_metrics — per-category rows per snapshot (name, weight, planned_pct, actual_pct, bac, ac)
```

**Key functions in db.py:**
- `init_db()` — creates schema + indexes; called by `make_server()` on startup
- `hash_file(path)` — SHA256 of file content
- `cache_xml(path, hash)` — copies XML to schedules dir, reuses existing if hash matches
- `upsert_project(p6_id, name)` — returns existing project id or inserts new
- `insert_snapshot / insert_metrics / insert_category_metrics` — called together after every successful parse
- `get_recent_projects(limit)` — one row per project, most recent snapshot, used by `/api/history`
- `get_project_snapshots(project_id)` — all snapshots for one project, for future trend dashboards
- `resolve_xml_path(original, cached)` — returns best available path for PDF re-generation
- `migrate_history_json(path)` — one-time import of legacy `history.json` → renames to `.migrated`

**Dashboard-ready queries (already supported by schema):**
```sql
-- Weekly SPI trend for a project
SELECT data_date, spi FROM snapshots JOIN metrics USING(id) WHERE project_id = ?

-- Multi-project delay comparison
SELECT p.name, m.delay_days, m.spi FROM projects p
JOIN snapshots s ON s.id = (SELECT id FROM snapshots WHERE project_id=p.id ORDER BY imported_at DESC LIMIT 1)
JOIN metrics m ON m.snapshot_id = s.id
```

---

## Do not touch

- `p6_evm/` — core computation modules; changes here break CLI + GUI
- The `records` key is stripped server-side — never include it in JSON responses (large + non-serialisable)
- `server.py` port injection: `window.__SERVER_PORT__` must be set before `app.js` runs
