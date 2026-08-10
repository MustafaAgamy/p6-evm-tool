# Changelog

All notable changes to this project will be documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)

---

## [Unreleased]
### Added — Update vs Update (Windows Analysis)
- **New "Update vs Update" analysis** — the sibling of Consultant Review, but the reference is **last period**, not the baseline. Give it the current update and the previous one (auto-suggested from your import history, or pick a file); it shows *what moved this period*. Its own tab, in the same module style.
- **Progress measured against last period's forecast** — the dashboard leads with what you actually earned this period vs what the **previous update itself forecast** for it (e.g. *41% where you said 43%*), labelled **"forecast achievement"** (not SPI — that's reserved for the plan), plus the forecast-finish slip and the cumulative-delay change.
- **Progress by activity — % complete this period** — every activity whose % moved between the two updates (Activity ID · name · previous % · current % · signed variance), biggest gain first; any activity whose % went **backwards** is flagged as a data-integrity check.
- **Critical-path movement in this window** — the critical / near-critical (float ≤ 10 wd) activities whose finish slipped or that **newly entered the critical path**, with the driver (progress shortfall / logic changed / duration extended).
- **What moved this period** — finished / started / slipped / stalled / re-sequenced counts; "re-sequenced" reuses the logic/lag engine measured against last period.
- **Period S-curve** — actual to date vs the previous update's own forecast line; the gap at the data date is this period's shortfall.
- **Milestone finish trend (slip chart)** — each key milestone's forecast finish plotted across **every** update you've imported (rising = slipping), backfilled from stored schedules so it's populated from day one.
- **Executive conclusion + PDF + Excel.** Isolated `p6_period` engine; **EVM calculation untouched** and every figure (actual %, delay, finish) reuses what the EVM tab already computes.

### Fixed — Consultant Review (from real-project testing)
- **Baseline finish** now shows when the baseline is a XER — it falls back to the latest activity finish (the XER reader stores no project finish, so it was blank).
- **Driving successor changes** are now highlighted in the change table; previously only the predecessor side was checked.
- **Change tables filtered to construction/execution** — submittals, approvals, deliveries and milestone activities are dropped (engineering/design/procurement WBS phases and milestone types excluded), so the table shows the work that actually drives the delay.
- **Impact shows the overall completion only** — the long per-milestone list was dropped from the screen and the PDF.
- **Export PDF / Excel** no longer silently do nothing — they use the report currently on screen (a background re-import used to null the state) and surface any error.
- **Corrected XML** step now also points out you can apply the reverts **by hand in P6** using the driving logic & lag table, then F9.

### Added — Baseline for XER updates (EVM now matches the XML exactly)
- **Attach a baseline to a XER update** — a P6 `.xer` *update* export doesn't carry its baseline, so its Planned Value was only approximate. You can now attach the baseline (the `.xer` exported from the baseline project) after importing the update; the EVM report then matches the XML export and P6 **exactly** — Planned Value, SPI, CPI, Finish Delay and every category, verified to the penny on real projects (Alstom, Saint-Gobain).
- **Baseline banner** on the EVM view — amber *"No baseline attached — Planned Value is approximate"* with an **Attach baseline XER** button, turning green *"Baseline attached · N/N activities matched — matches P6"* with **Replace / Remove** once attached; the Planned Value and Delay tiles are flagged "approx" until a baseline is attached.
- **"Import the baseline first" prompt** — opening the EVM view for a XER update with no baseline offers to import it first (skippable), so approximate figures are never read by accident.
- **Wrong-file guard** — attaching a baseline that matches no activities warns instead of showing a false match.
- **XER working-calendars** are now read from the file (working week, holidays, hours — including P6's finish-first shift format), so a XER's Planned % and Finish Delay match the XML instead of counting every day as working.
- **Automated match check** — a golden test confirms *XER + baseline == XML* to the penny on real exports, guarding against regressions.

### Added — Consultant Review: Baseline vs Current Update (Slice 1)
- **New Consultant Review analysis** — give it the approved **baseline** and the **current update**; it flags whether a delay is genuine or **manufactured by editing the logic, lags or durations** against the baseline. Its own tab, in the same style as the other modules.
- **Driving logic & lag change table** — only the activities whose driving predecessor/successor relationship or lag changed vs the baseline, with each side's driving links (ID + relationship + name), multiple driving links per activity, and added / changed / removed highlighting, above a "total changes" summary.
- **Duration & remaining table** — baseline original duration vs current, and remaining vs the baseline allowance ("extended / not burning down / on track").
- Isolated `p6_compare` engine (matches by Activity ID, derives the driving links); **EVM calculation untouched**.

### Added — Consultant Review: corrected "but-for" XML (Slice 2a)
- **Corrected but-for XML** — from the baseline + current update, generate a corrected P6 **XML** with the flagged manipulations reverted to baseline: relationship types and **lags**, added links removed, removed links restored, and **durations / remaining** reset to the baseline pace. Your **actuals and % complete are never touched**. Open it in P6, press **F9**, and read the genuine delay — the tool never computes a date itself; P6 does the scheduling.
- **Pick what to revert** — a tick-list of every flagged change (relationship / lag / duration) so you strip only the manipulations you reject and keep any legitimate re-sequencing ("Select all / none").
- The output is clearly a **but-for analysis file** (saved as `*_but-for.xml`, with a note inside), never mistaken for your official schedule. Requires the update as a P6 **XML** export.

### Added — Consultant Review: delay before vs after (Slice 2b-i)
- **Delay before/after the changes** — after you F9 the corrected file in P6 and re-export it, load it back in and the tool shows the **reported delay** (after) beside the **but-for delay** (before) and the **manufactured** days between them. The delay is P6's own finish-milestone float — the exact number the EVM tab shows — so nothing is re-derived.
- **Forecast completion + per-milestone before/after** — baseline, before-changes and after-changes finish, for the project and for each milestone, side by side.
- **Consultant recommendation** — an auto paragraph: how many of the reported delay days are genuine vs introduced by editing the schedule, the corrected forecast completion, and the recommendation (reinstate the baseline logic, or substantiate each change).

### Added — Consultant Review: S-curve + PDF/Excel export (Slice 2b-ii/iii)
- **Three-way S-curve** — baseline plan vs **before changes** (but-for) vs **after changes** (reported), cumulative planned % over time on a shared monthly axis. The gap between the before and after curves is the manufactured slip, made visible. (An illustrative progress profile from each schedule's dates & durations — the exact delay stays the P6 finish-milestone number above it.)
- **Export the report to PDF** — a landscape consultant page: dashboard, driving logic & lag change table, duration table, and — once the rescheduled file is loaded — the delay before/after, milestone before/after, the S-curve and the recommendation.
- **Export the change table to Excel** — the driving logic & lag change table (multi-driving links flattened per cell) as a single sheet.
- This completes **Consultant Review — Baseline vs Current Update** through Slice 2 (comparison tables, corrected but-for XML, delay before/after, S-curve, PDF + Excel).
- **Guarded the round-trip** — the "load rescheduled file" step now checks what you loaded and warns if it's the current update (nothing reverted) or a corrected file you haven't F9'd yet (finish unchanged). The screen also spells out the two ways to use the corrected file: **read the delay straight from P6** after F9 (no re-export), or re-export and load it back for the full before/after report.

---

## [v1.1.0] - 2026-08-08
### Added — EVM Results V2 (consultant report)
- **New EVM view + PDF** in a consultant format: SPI% headline (ahead / on-schedule / behind), equal-size KPI tiles, Baseline/Expected Finish + Delay, Planned-vs-Earned bar (Actual Cost removed from the bar).
- **Editable Actual Cost** (defaults to P6, or entered when P6 = Earned Value) with **auto-CPI**, and **editable category weights** (add categories, Planned Weight % column) via an Edit-Inputs panel, saved per project.
- **Engineering Progress** section: from **P6 (Mode B)** on import, with **"Upload E1 Log" → auto-switch to the Excel data (Mode A)**; reproduces the E1 Log status counting (Submitted/Approved/Not Approved, %Submitted = (Submitted − Not Approved) ÷ Req).
- **PV–EV Gap Analysis** grouped by a selectable P6 **activity code** (uncoded activities excluded), with an Engineering Gap by trade.

### Changed — Schedule Audit V2 (isolated module reports)
- **Report isolation** — each audit check is now an independent module with its own dashboard, KPIs, findings, score, PDF, and Excel. The audit is no longer mixed into the EVM weekly PDF.
- **Dangling Activities module** — Primavera Start/Finish/Start+Finish definition (absorbs the old Open Ends check), one merged row per activity, with Predecessor(s)/Successor(s) and a short Suggested Logic Fix.
- **Float Analysis module** — one row per over-threshold (or negative-float) activity, an Impact ratio (float ÷ threshold), a WBS summary of where excessive float concentrates, and per-activity severity.
- **Out of Sequence module** — a consultant-grade review report that matches P6's out-of-sequence detection: activities progressed against their logic, with predecessor/successor context, WBS grouping, and a suggested review.
- **Calendar Timeline & Audit module** — a calendar timeline view plus an audit of calendar definitions (working days/hours, holidays) used across the schedule, surfacing calendar-driven inconsistencies.
- **%-based module scoring** — each module scores from its own KPI % (Dangling % / Float %) with a 4-level grade (Excellent / Acceptable / Needs Attention / Critical). The overall Schedule Health Score is deferred until all modules exist and will be computed from module scores × weights, never from findings.
- **Consultant-grade PDF reports** — cover block, executive dashboard, Summary Statistics, WBS summary, refined findings tables (row numbers, short WBS with full-path tooltip, Impact, DCMA references) with headers repeating on every page.
- **Engineering reasoning** — the Dangling *Suggested Logic Fix* now names the specific relationship to review from the activity's existing predecessors/successors and WBS sequence (a suggestion only, never an edit), with a separate engineering *Recommendation*; Float recommendations are context-aware (impact + WBS) alongside a clean *Status* column.

### Added
- **AI Schedule Audit** — the tool now reviews a schedule's quality alongside the EVM numbers:
  - **Schedule Audit screen** (new sidebar shield + tab on the results view) showing a **Schedule Health Score** out of 100 with a grade, honestly labelled "based on 2 of 5 review areas".
  - Four rule-based checks: **Open Ends**, **Dangling Logic**, **Circular Logic**, and **Float Analysis** (negative and excessive float).
  - Findings list with **Activity ID + name + full WBS path**, plain-English issue and recommendation, and a stable reference code per finding; filterable by severity, check type, WBS, and free-text search.
  - **XER import** — Primavera `.xer` exports are read into the same schedule model as XML (Browse, drag-drop, and the XER card).
  - Audit results are **stored per import** so re-opening a project shows them instantly with no re-parse.
  - Audit added to the **PDF report** (new Schedule Health section) and a new **Excel export** of the findings.
### Changed
- Schedule Health score tuned harsher so serious issues (logic loops, critical-path open ends) pull the score down clearly.

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
