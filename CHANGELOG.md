# Changelog

All notable changes to this project will be documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)

---

## [Unreleased]
### Added — Calendar Timeline & Audit + Weather Impact
- **New "📅 Calendar Audit" analysis** — reads the P6 working calendars and shows, without opening Primavera: an executive dashboard (key dates + calendar statistics), a month-by-month **timeline**, monthly statistics, pop-open month calendars, exceptions grouped into **Holidays / Reduced-hours / Shutdowns** (a run of 5+ non-working P6 days = a shutdown; you can add your own and rename any block), a working-hours profile, calendar comparison & usage, a conflicts summary and an auto conclusion. **PDF + Excel** export. Isolated `p6_calendar` package; **no EVM number touched**.
- **Weather Impact (estimate)** — set the **project location on a map** and the tool estimates the **bad-weather days**, **milestone slip**, a **weather-adjusted finish** and **recovery options** for the remaining construction path. Free **Open-Meteo** data (live ~16-day forecast + historical climate + air-quality for dust), no key. Clearly an **estimate**, kept separate from the exact P6 Delay; offline-safe.
- **Editable stop-work limits** — a construction day counts as lost when any of your limits is met (rain ≥ 5 mm, heat ≥ 42 °C, wind off by default, dust on); each flagged day shows the **measured value vs your limit**, and days already off (weekend / holiday / shutdown) are never double-counted.

### Added — Calendar & Weather refinements (from testing)
- **Timeline starts at the data date** — the month strip (and its statistics + pop-open calendars) now begins at the P6 data date instead of the baseline start, hiding the already-actualised past; the headline totals still cover the whole project, and the number of hidden months is shown.
- **Pick the exact site on the map** — the location picker is now an **interactive map**: click, or drag the pin, to drop the project location precisely, with the coordinates and nearest place name read back. Still free OpenStreetMap, no key. (Search stays as a quick way to fly there first.)
- **Excel now includes the coloured calendar timeline** — the month-by-month grid (working / weekend / holiday / shutdown / special) is written above the monthly-statistics table, matching the PDF.
- **Weather source explained in the app** — the Weather Impact section now spells out how the estimate is built (the three Open-Meteo feeds, forecast vs expected) and exactly **what counts as a bad-weather day**.
- **What's driving the lost days** — a breakdown of the flagged days by cause (heat / dust / rain / wind), plus an **auto weather conclusion** paragraph that reads the numbers, names the main driver and points at the recommended action.

### Added — Calendar report, round 2 (from testing build #103)
- **Map centres reliably, and taps drop the pin** — fixed the map mis-sizing (pin at the edge) when the Calendar tab opens, **and** fixed clicking a point doing nothing: a real trackpad/touch tap moves a few pixels, which Leaflet treated as a pan, so no pin dropped. The pin now drops on any tap (mouse or touch) and the coordinates update immediately; a real pan still just pans.
- **Name your holidays & shutdowns, shown inside the day cell** — the exception Description is editable per project; the name you type now appears **inside that day's box** in the timeline (on screen and in Excel), same colour.
- **Excel exports the whole report** — a coloured timeline **for every assigned calendar** (names inside the cells) plus Monthly Statistics, Holidays & Exceptions, Shutdowns, Comparison, Usage and the Weather tables — each on its own sheet.
- **Bad-weather days name the activities they hit** — the Upcoming Bad-Weather Days table now lists the construction activities planned on each lost day (or says none is scheduled).
- **Monthly bad-weather histogram in the PDF** — the "When the risk falls" bars (bad-weather days per month) now print in the Weather section of the PDF too, not only on screen; the monthly counts are also written to the Excel Weather sheet.
- **Print only the sections you want** — a section picker on the Calendar Audit lets you choose which of the 10 sections go into the PDF.
- **Reduced-hours noise removed** — a "reduced hours" period within 5 minutes of the standard working day (P6 minute-rounding) is no longer reported; the Working-Hours Profile now explains how it differs from reduced hours.
- **Calendar Comparison reworked** — the Activities column is gone (counts live in Usage) and the last column now counts the **non-working days still ahead** (from the data date to finish), with the period stated.
- **Clearer tables** — plain-language legends for the Calendar Usage roles (Default / Non-default / Unused) and the Milestone Impact columns (Net = Before − Already in calendar).

## [v1.2.1] - 2026-08-13
### Added — Update vs Update: choose how the critical path is presented
- **Critical-path style picker** — the critical-path comparison can now be shown three ways, and you choose which: **Connected chain** (blocks end-to-end; one row when the route is unchanged — the default), **Date-axis timeline** (the finish-driving route on a real calendar, WAS over NOW, so you watch the finish slide), and **Compact table** (Was vs Now as text rows — the most print-dense). All three are drawn from the **same** data (route, dates, divergence, slip), so every figure is identical — only the drawing changes.
- **The choice carries into the PDF.** Pick a style on the on-screen card or in the Export-PDF preview; the exported report uses exactly that style (and the grouping you set), and your choice is remembered for next time.

## [v1.2.0] - 2026-08-13
### Added — Update vs Update (Windows Analysis)
- **New "Update vs Update" analysis** — the sibling of Consultant Review, but the reference is **last period**, not the baseline. Give it the current update and the previous one (auto-suggested from your import history, or pick a file); it shows *what moved this period*. Its own tab, in the same module style.
- **Progress measured against last period's forecast** — the dashboard leads with what you actually earned this period vs what the **previous update itself forecast** for it (e.g. *41% where you said 43%*), labelled **"forecast achievement"** (not SPI — that's reserved for the plan), plus the forecast-finish slip and the cumulative-delay change.
- **Progress by activity — % complete this period** — every activity whose % moved between the two updates (Activity ID · name · previous % · current % · signed variance), biggest gain first; any activity whose % went **backwards** is flagged as a data-integrity check.
- **Critical-path movement in this window** — the critical / near-critical (float ≤ 10 wd) activities whose finish slipped or that **newly entered the critical path**, with the driver (progress shortfall / logic changed / duration extended).
- **What moved this period** — finished / started / slipped / stalled / re-sequenced counts; "re-sequenced" reuses the logic/lag engine measured against last period.
- **Period S-curve** — actual to date vs the previous update's own forecast line; the gap at the data date is this period's shortfall.
- **Milestone finish trend (slip chart)** — each key milestone's forecast finish plotted across **every** update you've imported (rising = slipping), backfilled from stored schedules so it's populated from day one.
- **SPI, Delay & % Complete comparison strips** — the dashboard leads with three **Previous → Current → Variance** strips, each labelled with its **cutoff (data) date**: Overall % Complete, **SPI** (Earned ÷ Planned) and **Delay vs baseline**. SPI and Delay are the same figures the EVM tab shows at each cutoff. Sign rule: the arrow follows the number, the colour follows good/bad (SPI ▲ = better, Delay ▲ = worse).
- **Cutoff dates** stated at the top of the dashboard (previous vs current data date).
- **Activity-code slicer** on the Progress-by-activity table — pick a code type (Discipline / Area / Phase — whatever your schedule carries) and a value to see just those activities' current vs previous % complete.
- **Two conclusions** — an *Executive conclusion* for the period and a new *Project conclusion & outlook* for where the whole project stands.
- **Executive conclusion + PDF + Excel.** The Excel mirrors the PDF (one sheet: Progress-by-activity then Critical-path-movement sections under a project/cutoff header). Isolated `p6_period` engine; **EVM calculation untouched** and every figure (actual %, SPI, delay, finish) reuses what the EVM tab already computes.
- **Management-grade report (planning-manager enhancement).** The PDF/preview is now a two-audience report: **Page 1 — Execution Dashboard** for management (a status verdict banner, a four-card scorecard — % Complete, SPI, Delay and **Forecast finish, each Previous → Current** — a **Recovery outlook** projecting the landing date and the rate needed to hold the baseline, key facts incl. **schedule adherence**, the S-curve and a recommendation), and **Page 2 — planner detail** (progress, critical-path movement, a **next-period watch list** of near-critical work, what-moved, milestone trend, project conclusion). The recovery/adherence/watch figures are indicative planning projections, clearly flagged (not a P6 reschedule).
- **Export previews first.** Export PDF now opens a **preview** of the exact report before you choose where to save.
- **Right way round.** The two updates are ordered by **data date** — earlier = Previous, later = Current — regardless of load order.
- **Activity-code columns in Excel.** Every activity table in the Excel export (progress, critical-path, watch list) appends one column per activity code (Discipline / Area / Phase / …) so you can filter or pivot by any code; the on-screen progress table keeps its code slicer. PDF numeric columns now align under their headers.
- **Critical-path comparison, rebuilt for clarity (from testing).** The finish-driving route now reads as one **connected chain** of blocks — each labelled with the months it spans — led by a plain-English conclusion. When the route is **unchanged** you see a **single row**; only when it **reroutes** do two aligned rows appear (shared start in blue, the **new route in red**, the dropped route in grey), with the **total finish slip** called out. Replaces the earlier WBS "boxes" and an interim date-axis timeline (both read as too abstract / left floating gaps on real data). It reads your schedule's own WBS so it works for any construction type, and you can still regroup by any WBS level or activity code. Screen **and** PDF. Per-segment day-splits are deliberately not shown — attributing a slip to single activities needs a full P6 time-impact analysis, which this report does not do.
- **Exported PDF respects the activity-code filter (fix, from testing).** When you pick an activity code and export the report, every activity table now shows **only that code** — previously the PDF showed all activities regardless of the on-screen filter.

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

### Added — Constructability Review (rule-based + Knowledge Base)
- **New "🧠 Constructability" analysis** — reviews an imported schedule against a **local Construction Knowledge Base** for its project sub-type, entirely **offline** and at **no cost** (no AI, no API key). Detects the sub-type and reports, as clearly-labelled advisory findings: illogical relationships (with the engineering reason *why*) and the better logic to use (change / add / remove a link, multiple predecessors & successors supported); **missing activities** it would normally expect for that sub-type — each given a non-clashing suggested ID, a home WBS (or a suggested new one) and wired predecessor/successor; and a **WBS review** flagging missing branches.
- **Constructability Score /100** with a legend gauge — weighted **45% construction logic · 45% scope completeness · 10% structure**, derived from the finding counts (not a confidence number), with action bands (Ready / Minor / Significant / Major gaps).
- **Editable Construction Knowledge Base** — a two-level taxonomy (Category → Sub-type), seeded with **Infrastructure › Rail** and **Industrial › Factory** starter drafts. Ships as bundled defaults plus a per-user overlay, so standards can be added or refined without touching the app.
- **External AI is deferred to a future Professional Edition** (Decision 009): the community edition is rule-based and fully offline; the AI review engine stays in the codebase as a dormant module for later. `p6_evm` / `p6_audit` computations and the offline guarantee are untouched.
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

### Added — Weather Impact (Calendar Audit)
- **Weather Impact layer** — set the **project location on an interactive map** and the tool estimates **bad-weather days**, the **milestone slip** they cause, a **weather-adjusted finish** and recovery options. Construction-only, from the free Open-Meteo service; clearly an **estimate**, kept separate from the exact P6 Delay, and offline-safe once fetched. Added to the Calendar Audit's **PDF + Excel** export.

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
