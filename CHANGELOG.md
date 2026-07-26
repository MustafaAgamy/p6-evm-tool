# Changelog

All notable changes to this project will be documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)

---

## [v1.0.4] - 2026-07-26
### Added
- "Previously imported on [date] · results updated" note in the file info bar when the same XML is imported again

### Fixed
- Flash of dark theme on startup — theme class now applied synchronously before first paint
- Tooltips no longer clip at screen edges — replaced CSS pseudo-element tooltips with a single JS-positioned element that clamps to the viewport and flips direction automatically; all future `data-tooltip` elements get this behaviour for free

### Performance
- Opening an existing project from Recent Projects now loads stored metrics from SQLite instead of re-parsing the XML file

---

## [v1.0.3] - 2026-07-25
### Added
- Project delete button in Recent Projects table — removes all snapshots and metrics for a project
- Hover tooltips on KPI tiles explaining each metric
- 134 Python tests + 44 JavaScript tests covering all modules (metrics, parser, calendars, DB, server, report, CLI)

### Changed
- UI refactored from monolithic `app.js` into ES modules (`state.js`, `format.js`, `render.js`, `history.js`, `events.js`) — no functional change, better maintainability

### Fixed
- HTML injection in Recent Projects table: file paths and names are now properly escaped before being inserted into the DOM

---

## [v1.0.2] - 2026-07-25
### Fixed
- Disabled UPX compression in PyInstaller build to reduce antivirus false positives

---

## [v1.0.1] - 2026-07-25
### Changed
- Release workflow now auto-generates notes from commits between tags

---

## [v1.0.0] - 2026-07-25
### Added
- Desktop app (PyWebView) — native OS window, no terminal needed
- Import P6 XML by Browse button or drag-and-drop
- 6 KPI tiles: Finish Delay, SPI, Planned Value, Earned Value, Actual Cost, CPI
- Category progress bars (planned vs actual) for all configured WBS categories
- Dark / light theme toggle with localStorage persistence
- Generate PDF weekly report via Chrome headless
- Recent Projects table — last 10 imports with one-click re-open
- Local SQLite DB (`%APPDATA%\P6EVMTool\p6evm.db`) — all metrics persisted per import
- XML file caching — files reopen even if original is moved or deleted
- Per-user isolated storage — safe to share one `.exe` across multiple engineers
- Auto-migrates legacy `history.json` from pre-DB versions
- GitHub Actions release workflow triggered by version tags (`v*`)
