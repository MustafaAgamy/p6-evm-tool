# Changelog

All notable changes to this project will be documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)

---

## [Unreleased]

### Changed — Overview, WBS and Schedule (Gantt): cost-loaded progress, critical-only Gantt (comments 63, 64, 65, 93, 94)
- **Overview = the cost-loaded activities only (comment 93).** Planned %, Actual %, Planned value and Earned value are now taken from the activities that carry a budget in P6, each weighted by its budget as P6 weights it; activities with no cost (Engineering, Procurement) take no part. SPI follows (Actual % ÷ Planned %). The CPI and Actual cost tiles are gone. A line under the tiles says how many activities the figures come from. A schedule with no cost loading at all keeps its duration-weighted figures and says so.
- **Progress by WBS or by any activity code (comment 94).** A new *Show by* list on the Overview groups the cost-loaded activities by WBS or by any P6 activity code assigned to them, and shows Planned % against Actual % for each value of that code (budget-weighted). The Excel export follows the grouping picked on screen.
- **WBS: no percentages for a WBS that is not cost-loaded (comment 63).** Planned % and Actual % are not calculated for such a WBS — its two cells read “no cost”; a main branch with no cost at all (e.g. Engineering) drops the two columns and says “not cost-loaded”. Same in the report and in Excel.
- **WBS: no sideways scroll (comment 64).** The timeline now fits the width of the screen, so the whole WBS shows at once. The WBS column is as wide as its longest level needs and a longer name wraps onto a second line, so no WBS level is cut short.
- **Schedule (Gantt): critical activities only (comment 65).** The chart, its report and its Excel sheet list only the activities P6 flags as Critical (work not finished), with the count out of all activities.
- **Overview charts: a Planned column beside an Actual column.** *Progress by …* is now drawn as two columns per value — Planned % (blue) and Actual % (amber), each with its figure on top. A new tick box, *Hide Planned 0 % and Actual 0 %*, drops the values with no progress planned or achieved yet (the Excel export follows it). The words “cost-loaded” no longer sit beside Planned % and Actual %.
- **WBS: P6's own order, delay in working days, cut-off date.** WBS are listed in the order P6 lists them (its WBS sequence — e.g. Submittal before Approval), not alphabetically. Delay is now the WBS's Total Float on the update read as days late — its latest Late Finish against its latest Early Finish on the project calendar (was Expected Finish − Baseline Finish in calendar days). The bar chart marks the cut-off date (data date) with its date.
- **Schedule Gantt (Critical activities): construction only, Delay, Expected dates, activity-code column.** The chart lists the critical activities of the construction works only (the WBS that holds the cost-loaded work). Start / Finish are named Expected Start / Expected Finish, a Delay column follows them (the activity's Total Float on the update read as days late — float −12 d = 12 d of delay), and a new *Activity code column* list lets the planner pick any P6 activity code to show beside the Activity ID. Column widths follow the longest ID / name, and a long name wraps, so no activity is cut. Report and Excel follow.
- **Gantt and WBS match P6's Critical-filter layout.** Reconciled against a P6 sheet of the 09-Aug-2026 update: the Gantt is now banded by every WBS level in P6's order, and each band carries P6's summary of its critical activities — earliest Expected Start, latest Expected Finish, the band's own Total Float as Delay, and the Activity Count. The WBS screen gains an *All activities / Critical activities* switch; the Critical view summarises each WBS over its critical activities only, with new optional columns Total Float, Activity Count, Original Duration, Planned Value Cost, Earned Value Cost and Budgeted Total Cost. On that update every figure equals P6 (Construction: 668 activities, 267 d, 19-Jun-2026 → 22-May-2027, Schedule 52.49 %, Performance 9.18 %, PV 282,072,014.17, EV 49,338,040.31, budget 537,420,292.67, Total Float −72).
- **Schedule (Gantt): Activity ID in its own column.** The chart now has separate *Activity ID* and *Activity name* columns instead of the ID stacked above the name.

### Changed — Productivity & Resources: the rate follows the Project type; no Location setting (comments 61, 62)
- **The Project type changes the rate by itself (comment 62).** Controlyx now holds a built-in factor for every project type and trade, so the same work item has a different productivity on each kind of project: Internal Cement Plaster gives 21.74 m2 per crew-day on a Residential project, 20.83 on an Industrial one, 20 on a Commercial one and 16.67 in a Hospital; RC Columns (100 m3) take 1,764 man-hours on Residential, 1,857 on Commercial, 2,043 on Industrial and 2,191 on Oil & Gas. No two project types share a productivity within a trade. Eight trade groups (earthworks, infrastructure roads / networks / bridges, concrete structure, structural steel, finishes & masonry, MEP services, mechanical / piping / instrumentation, testing & commissioning) × nine project types cover all 236 work items; Commercial is the base (the library norm). The factors are a general estimate of how the trades compare, not yet verified against an Egyptian reference, and live in one file (`productivity_kb/project_type_factors.json`) where a single work item can also be given its own number.
- **Seen, not hidden.** A new table, *This work item on every project type*, lists the factor, the output per day, the man-hours per unit, the total man-hours and the duration for all nine project types — click a row to pick that type. The chosen factor shows beside the Project type (“built-in × 1.15”) and under the item title, in the report and in Excel, which gains a **By project type** sheet.
- **Your own factor still wins.** A factor typed beside the Project type replaces the built-in one for that type (the built-in value stays visible).
- **Methodology = the estimate: Optimistic, Most likely, Pessimistic.** The Methodology setting no longer lists construction methods (Conventional / Jump-form / Climbing form / Precast) that changed nothing by themselves. It is now the estimate the result uses: **Optimistic** needs the lowest duration (best case), **Pessimistic** the highest (hard case) and **Most likely** is the library norm. Each is the work item's own low / likely / high rate from the library, and a table shows the three side by side — RC Columns, 100 m3, Commercial: Optimistic 12.31 m2 per crew-day, 1,530 man-hours, 18.3 days · Most likely 10 m2, 1,857 man-hours, 22.5 days · Pessimistic 8 m2, 2,280 man-hours, 28.1 days. Click an estimate and the rates, man-hours and duration follow everywhere, including the report and Excel (new **Methodology** sheet). It works together with the project-type factor.
- **Infrastructure works added to the library.** A new **Infrastructure** discipline holds 47 work items with their rates, crews and the three estimates: Roads (subgrade, base and sub-base, prime / tack coat, asphalt, kerbs, interlock, marking, signs, guardrail), Water Network (HDPE and ductile-iron mains, valve chambers, hydrants, house connections, pressure test), Sewer Network (uPVC and GRP sewers, manholes, house connections, CCTV), Stormwater Drainage (RC pipes, gullies, box culverts, channel lining), Irrigation, Electrical Network (cable trench, MV / LV cables, duct banks, joints, substations), Street Lighting, Telecom Network, Gas Network and Bridges. The road and drainage items the library already had moved there from Civil. The new rates are general estimates (draft), not yet verified against an Egyptian reference.
- **Rates in three tiers, each one saying where it comes from.** (1) **Egyptian reference** — 51 rates taken from Egyptian sources: *معدلات الأداء و الإنتاجية* by Eng. Mostafa Afifi, Technical Office (Egypt, 2017) for formwork and reinforcement of footings, pile caps, rafts, columns, slabs and walls, brick masonry, internal and external plaster, ceramic floor and wall tiles, marble floors, membrane waterproofing and excavation in soil and rock, with its general reinforcement rate (1 tonne a day for a team of six = 48 man-hours per tonne) for every other reinforcement; and slab reinforcement **measured on an Egyptian site** by Cairo University (2019): 59 to 69 man-hours per tonne, median 63.4. (2) **Derived from an Egyptian reference** — 10 rates the reference does not list, worked out from it as the normal Egyptian productivity: formwork of beams, ribbed, waffle and post-tensioned slabs, bridge decks and culverts from the nearest element it gives, a full paint system from its putty and paint per-coat rates, trench excavation from its excavator rate. (3) **International / general industry norm** — the 305 rates for which no Egyptian reference was found (all infrastructure networks, MEP, steel, piping, commissioning). Formwork and reinforcement, given by the reference per m3 of concrete, are converted with the work item's own quantities. Each rate keeps its tier and basis in the library data; the list of references is not shown on screen, in the report or in Excel. No rate claims an “Egypt norm” without a source any more, and no work item was removed.
- **Complex industrial MEP works added.** 45 new work items for industrial projects: **Industrial Power** (MV switchgear, power transformer, diesel generator, UPS, heavy cable ladder, large power cables, motors, VFD panels, high-bay lighting, earthing grid, Ex fittings, heat tracing, cathodic protection), **Instrumentation & Control** (control valves, tubing and impulse lines, instrument cables, junction boxes, DCS / PLC cabinets, calibration, fire & gas detectors, analyzer shelters), **Material Handling** (belt, chain and screw conveyors, bucket elevators, dust collectors, steel silos, overhead cranes), **Process & Utility Equipment** (fans, compressors, cooling towers, boilers, process ducting, alignment, water-treatment skids, fuel systems), **Utility Piping** (supports, compressed air, steam and condensate, GRE / GRP, valves, painting) and **Industrial Fire Protection** (ring main, deluge, foam, monitors). They are international norms (tier 3). The library now holds 236 work items.
- **Location removed (comment 61).** The Location setting and its factor box are gone from the settings, the results, the report and the Excel export — the tool is for planning engineers working in Egypt.

### Changed — Baseline Revision: a ledger that names every count; critical counted as P6 counts it (comments 59, 60, 103)
- **Comparison ledger (comment 60).** Every row now carries one named count. Before, “New / removed activities” showed 524 under Rev.00 and 43 under Rev.01 with nothing saying which was added and which removed; the same went for modified / ID changes, the relationship changes and critical-path in / out. Now: **Added — new in Rev.01** 524 (under Rev.01), **Removed — deleted from Rev.00** 43 (under Rev.00), Modified 944, Activity ID changed 103; total relationships 1,696 → 2,631 with added 1,497, removed 562, type changed 55, lag changed 73; critical activities 214 → 410 with became critical 295, no longer critical 99, critical path 58 d shorter. A **What it means** column gives one plain line per row, and the arithmetic is printed under the table where it closes (1,022 + 524 added − 43 removed = 1,503 activities). Screen, PDF, Word and Excel.
- **Schedule-quality signals table removed (comment 59)** from the screen, the report and the Excel workbook; the ledger takes the full width.
- **Critical activities as P6 counts them (comment 103).** Baseline Revision used its own rule (task activities only, total float ≤ 0 days). It now uses P6's own Critical flag — every activity type, milestones included, by the project's critical float limit or its Longest Path setting — in the critical counts, the became / no longer critical lists and the float-movement register. Checked against the raw P6 tables on Grain Bulk Rev.00 ↔ Rev.01 and REV.01 → REV.03: activities, relationships, critical activities (214 / 410), every float band and the negative-float counts equal P6. A baseline exported without total float (Saint Gobain) has no P6 flag to compare; the longest-path chain is used there, as before.

### Changed — Bad Weather: one Conclusion & Recovery Recommendation (comment 58)
Section 7 is now a single summary instead of a table that repeated the same three options for every delayed milestone (13 rows on Grain Bulk) and never stated the total. It shows the **total weather impact** on the project finish (Grain Bulk: +10 wd, 02-May.2027 → 19-May.2027), one **recovery recommendation — a second shift** over the months that lose the most working days to weather (“Add a second shift in Jan 2027, Feb 2027 and Apr 2027 — the months with the most bad weather — to recover the 10 working days lost (about 80 work-hours)”; under the total, how it is counted: “13 bad-weather days expected − 2 on days already off (weekend / holiday) = 11 working days lost”), and the **conclusion** paragraph, which used to sit apart as a footnote. The conclusion names the same peak months as the recommendation. Screen, PDF, Word and Excel show the same summary; the delay of each milestone stays in section 6. When weather adds no delay the section says no recovery is needed.

### Changed — Bad Weather: results only after Apply & Recalculate; the Project Type stays as chosen; the finish month in full (comment 58)
- **No result before the inputs.** Bad Weather shows no result until the planner has picked the **Project Type** and the **Location** and clicked **Apply & Recalculate** — the button stays disabled until both are set. A saved type, location and limits are pre-filled on re-opening, but a saved estimate is no longer shown by itself, and the PDF / Excel exports wait for the on-screen result.
- **Project Type stays.** Editing a stop-work limit no longer switches the Project Type to another type or to “Custom limits”: the type stays as chosen, the edited limits are used, and the criteria panel reads e.g. “Marine / Port · limits edited”.
- **Finish month in full.** Every month of the chart is shown to its end, so the month the bad-weather completion falls in shows all its working days (a completion on the 1st showed that month with 1 working day). Weather is still counted only up to the completion.

### Fixed — Bad Weather: the months chart runs to the bad-weather completion; Excel cells centred (comment 58)
- **Weather window.** The estimate now reads the weather up to the **bad-weather completion**, not only to the schedule's own finish. Before, the months chart stopped at the forecast completion, so when weather moved the finish into a later part of the month that month still showed 1 working day and no weather (Grain Bulk: forecast 02-May.2027, bad-weather completion 19-May.2027, May 2027 showed 1 working day — now 11). The days the finish — and each milestone — is pushed into are themselves checked for bad weather, so a bad day there adds to the delay.
- **Excel.** In the Bad Weather and P6 Calendar Audit workbooks the data sits in the middle of the cells (centred across and down, wrapped); titles stay left. Every word of a wrapped cell is shown: each row is as tall as its longest cell needs (a long reason or activity list was cut off at the row height), and the day columns of the Bad-Weather Calendar sheet are wider so a bad-weather day's reason reads in full.

### Changed — Consultant Review: table borders, highlights in every export, untrimmed preview (comment 57)
- **Borders.** The **Driving logic & lag changes vs baseline** table — and the Duration table in the report — draw a full grid: every cell is boxed, on screen, in the PDF and in Word. Before, the report had only a pale line under each row and the screen had no lines between the columns.
- **Highlights in PDF / Word / Excel.** The marks the screen table shows are now in every export: the **driving link** is bold with a ▶ before its ID, a link **changed** vs the baseline is red, an **added** link green and a **removed** link struck through — one link per line, with the legend under the table. Before, the exports listed the links as plain text joined with “/” and coloured every update relationship red whether it had changed or not.
- **Print preview no longer trimmed.** A landscape report (Consultant Review, Update Analysis, Update vs Update, Critical Path Analyzer, Baseline Revision, Knowledge Base) is now previewed on the landscape page it prints on. It was laid out on the portrait width, so its wide tables ran past the page edge and were cut off in the preview while the PDF was complete.

### Added — Lag Report: how the lag charts are counted (comment 55)
Under **Lags by relationship type** and **Lags by WBS area** the Lag Report now says how each number is worked out — on screen, in the PDF and in Excel. Both are counted from the relationships that carry a lag or a lead (Grain Bulk: 406 of 2,631 relationships); each bar is the lagged links of that type, or of that WBS area, and its % is that count ÷ all lagged links (FS 256 ÷ 406 = 63.1%). A lagged link is counted under its **successor** activity's WBS area — the WBS level just below the project — and when there are more than 10 areas the note says the 10 with the most lags are shown.

### Changed — The same bands for every Schedule Health sub-feature
Every sub-feature now grades its score on the one band legend — **Pass ≥ 95 · Review 90–95 · Critical < 90** — with no exceptions: the grade beside each score (was Excellent / Good / Acceptable / Critical, and CPLI's own 100 / 90 / 85 / 75 / 60 steps), the colours (green / amber / red were ≥ 85 / 60–84 / < 60 on the gauges and Float Health), the WBS rows, the Summary's checks-status donut (Relationship Types used to pass at 90 and review from 85) and every "how this score is calculated" legend. Each check keeps its own score formula. The Summary headline's completion total float is shown in whole days (−104 d, was −104.11212121212121 d).

### Added — Schedule Health Summary: the legend under the overall score (comment 54)
The overall score now carries its legend, on screen and in the PDF: the submission scale the verdict uses (Not ready < 80 · Acceptable to submit 80–90 · Ready to submit ≥ 90 — the 80% rule is kept) and where the same score falls on the per-check bands (Critical < 90 · Review 90–95 · Pass ≥ 95). An overall 81.2 now reads "Acceptable to submit — on the per-check bands the overall 81.2 would be Critical", so it is never taken for a pass.

### Changed — Relationship Types: total activities and how SS % / FF % are worked out (comment 47)
The Relationship Types check now shows **Total Activities** and **Remaining Activities** (as P6 counts them) and the count behind every percentage — FS 88.9% (4,380), SS 5.1% (252), FF 5.9% (292), SF (1) on Alstom — with one line saying how each % is worked out: that type's relationships ÷ all relationships (SS % = 252 ÷ 4,925 = 5.1%). The Excel export lists the four counts too.

### Changed — Schedule Health shows rounded numbers (comments 51, 53)
Days are shown as whole numbers everywhere in the Schedule Health results — total float, durations, lags, variances, the Float Analysis averages and highest float, and the Milestone Check's **Total Float** column, which showed raw values like −10.4375 d (now −10 d). Percentages and scores keep one decimal (26.8%, 95.8), so a small share such as 0.2% stays visible. The Whole-Day check still shows the exact duration (51.71 d), because that decimal is what it reports.

### Fixed — Schedule Health counts activities the way P6 does (comments 48, 49, 50, 52)
Critical, near-critical and negative-float activities are now counted as P6 counts them: **every activity type** (tasks, milestones, Level of Effort, WBS summaries), critical by P6's own setting in the file ("Define critical activities as" — total float ≤ the project's limit, or the longest path). Before, only task-dependent activities were counted, so on Alstom UP-006 the CPLI and Float Analysis showed 483 critical where P6 shows **497** (483 tasks + 8 finish milestones + 6 LOE), 306 near-critical where P6 has **325**, 410 negative-float where P6 has **421**, and 2,450 activities where P6 lists **2,502**. Every percentage is now over the **remaining activities** (Not Started + In Progress — every activity when nothing is completed), the same base in every check (CPLI showed 19.7% and Float Analysis 23.5% for the same 483; both now 497 ÷ 2,102 = 23.6%). Each Health check shows **Total Activities** (completed included) and **Remaining Activities**; checks that examine the task activities only (open ends, dangling, constraints, durations, whole days) label their own base "Tasks Checked". Checked on Alstom, Saint Gobain, Grain Bulk and MAFI — every count equals P6.

### Changed — One date style everywhere: 03-Dec.2026 (comment 46)
Every date in every feature's results now reads **03-Dec.2026** — on screen, in the PDF, Word, HTML and Excel exports, in the chat answers and the Narrative report. Before, the same date showed as 03-Dec-2026, 03 Dec 2026, 3 December 2026 or 2026-12-03 depending on the feature (the Critical Path chain, the Calendar Audit key dates, the Update vs Update tables and the Narrative were the main ones). Excel date cells use the same style (`dd-mmm.yyyy`) and stay real dates. Dates written in the older styles — a contract date typed as 9-Feb-2027, a saved report — are still read. Month-only labels on chart axes (Dec-26) are unchanged.

### Added — Baseline Narrative: put the activity codes in the order you want (comment 45)
- **Sequence of Work (§11) — ⇄ swaps the two codes of an analysis.** Pick "Type of Works" then "Type of Civil Works", press ⇄, and "Type of Civil Works" becomes the 1st code and "Type of Works" the 2nd — the section then groups the sequence by Type of Civil Works instead of by Type of Works. Checked on Grain Bulk ("Type of Works" ⇄ "Type of Civil Work").
- **▲ ▼ move a whole sequence analysis up or down**, so the analyses print in the order you choose.
- Both in the setup panel and in the guided setup questions; the Scope of Work codes keep their ▲ ▼. The order is saved with the project.

### Fixed — Every feature checked against P6 by its own function (comment 44)
The P6 test now covers every feature's own function, on the baselines **and** the updates (MAFI, Grain Bulk, Saint Gobain, Alstom — 11 files, XER and XML): **619 checks on single schedules and 222 on six baseline → update pairs, all equal to the values P6 wrote into the files.** Added to the 183 of comment 5: the **WBS** view (every element's activity count, start and finish), **Earned Value** by P6's own formulas (BAC, EV = BAC × % complete, AC — incl. costs held on resource assignments — PV = BAC × schedule % complete, CPI; against the baseline inside the file where P6 earns against it), **P6 Calendar Audit** working days per month, the scheduler behind **Consultant Review**'s but-for delay, and the two-schedule features — **Baseline Revision / Update vs Update** (activities added / removed / renamed, every relationship change, milestone dates, budgets), **Consultant Review** (matched activities, both finishes and the slip, milestones, every changed-logic and duration row), **Critical Path Analyzer** (counted / critical activities, governing finish and its baseline finish) and **Update Analysis** (actual and planned status counts). An update exported as XER and as XML now gives the same answer on every one of them.
- **Consultant Review — the but-for now equals P6's own schedule.** Its in-tool scheduler counted whole days, ran lags on the successor's calendar, let Level of Effort activities drive their successors and ignored P6's "start-to-start lag from early start" option — so on MAFI, compared with itself, it reported 53 days of but-for delay (P6: none), and on Alstom 7 months. It now schedules in working minutes on each activity's calendar, the lag on P6's lag calendar, with P6's rules for Level of Effort, started activities (a start-to-start lag counts the working time the predecessor has already run), finish-to-finish links (a finish that lands on the next morning's start is the close of the day before, as P6 shows it), finish milestones and start / finish constraints. And it keeps P6's own dates for every activity a reverted change cannot reach — dates P6 may have set by **resource leveling** (MAFI, Grain Bulk, Saint Gobain are leveled) or before a later calendar / duration edit (Saint Gobain), which no logic-only scheduler can rebuild from the file; only the activities a change reaches are rescheduled. With no change applied the but-for is therefore P6's schedule exactly: the project finish to the minute and **every** open activity's early finish on all 11 files (was 94–99%).
- **Two links between the same two activities (an SS and an FF) are now two links everywhere.** The comparison kept only the last one, so a changed FF lag was hidden in Consultant Review's logic table, two lag changes were counted as one "type change" in Baseline Revision, and the revert plan / corrected XML / but-for finish set **both** links to one type and lag (turning the FF into an SS). Each link is now listed, counted and reverted to its own baseline type and lag.
- **Baseline Revision — no more false "rate changes" between an XER and an XML.** A P6 19.x XML states no price on a resource assignment; an XER holds the rate captured when it was costed. Comparing the two reported 441 rate changes on Saint Gobain that P6 does not show; where either side's price is derived, the effective cost per unit is compared instead.
- **Critical Path Analyzer — an XER update is measured against the baseline you pick.** An XER update carries no baseline rows, so its own Planned dates stood in even with a Baseline file picked (BL finish 07-Sep-2026 instead of 24-Aug-2026 on Alstom). The picked baseline now applies, exactly as the same update exported as XML with the baseline inside; an embedded or attached baseline is kept.
- **Consultant Review — the finish slip is counted between the two finish dates** (a 17:00 → 08:00 finish 14 dates apart is 14 days, not 13).

### Fixed — Every keyboard shortcut works on every feature (comment 43)
Every shortcut was pressed in the running app, on every feature, with a schedule imported: the 20 feature jumps (Alt+1 … Alt+0, Alt+Shift+1 … Alt+Shift+0), and on each of the 18 features Ctrl+↵, Ctrl+P, Ctrl+S, Ctrl+E, Ctrl+Shift+E, Ctrl+Shift+W, Ctrl+Shift+H and Ctrl+R, plus Ctrl+K, Ctrl+Shift+R, Ctrl+B, Ctrl+D, Ctrl+Shift+A, F1, Ctrl+/, Ctrl+F, ?, Esc and Ctrl+O. Every feature has its own jump and every jump opens it. What did not act, now fixed:
- **Ctrl+E (Export to Excel) on Overview, WBS, Earned Value and Productivity & Resources** saved nothing — it said "This view exports to PDF" or "Run this module's analysis first", although the views have Excel. It now saves the view's own workbook, or opens the preview and presses its ⬇ Excel.
- **Ctrl+Shift+W / Ctrl+Shift+H on the Knowledge Base** opened the preview but saved nothing. They now save Word / HTML.
- **Ctrl+R and Ctrl+↵ on a Consultant Review or Baseline Revision result** said "use this feature's own Run button". They now run the comparison again with the same files.
- **Ctrl+↵ on Bad Weather** said "assign this feature's input files" — it now says what it needs: the project location.
- **Schedule Health before its run:** the export shortcuts said "Open a schedule and pick a module first" while a schedule was open; they now say to enter the contract milestones and run the review (Ctrl+↵).
- **Ctrl+↵ / Ctrl+R on Overview, WBS and the Gantt** say they are built when the schedule is imported and already up to date, instead of doing nothing.
- A browser test now presses these shortcuts in the real page on every build (tests/test_shortcuts_browser_comment43.py).

## [v2.10.0] - 2026-10-02

### Fixed — Results checked against Primavera P6, feature by feature (final test)
The values P6 itself stores in the export file — every activity's Start, Finish, status, % complete and total float, every relationship's type and lag, the calendars' hours and the budgeted and actual costs — were read independently of the tool and compared with what each feature reports, on Grain Bulk (three baselines), Saint Gobain (two baselines, two updates) and Alstom: about 380 checks. They agree, except for three differences, now fixed:
- **Consultant Review — milestone table.** A milestone that is already achieved showed its planned date in the "update finish" column (for example 27 Mar where P6 shows the actual 23 Mar). It now shows the date P6 shows in Finish: the actual date once achieved, the forecast otherwise.
- **Baseline Revision — dates.** In a revision that already carries progress, a finished activity showed its planned finish. Start and Finish are now the dates P6 shows (actual where the work has happened).
- **Baseline Revision — relationship count.** P6 allows two links between the same two activities (for example an SS and an FF). They were counted as one, so "Total relationships" read 2,589 where P6 holds 2,631 (Grain Bulk Rev.00). The count now equals P6's, and a change to either link is reported.
- Also from the final sweep: the Reporting Studio's Excel now carries the real tables and figures of reused report sections (it had a one-line placeholder).
- **Schedule (Gantt) in Word — the bars are back.** The printed Gantt's time-line column (each bar from Start to Finish with its % complete fill, the milestone diamonds, the data-date line and the month scale) was left out of Word, so Word had the table without its bars. Word now draws every bar in that column as native Word shapes — same colours as the PDF (red for critical), selectable and editable, no pictures. Excel leaves the column out, as before (the dates are in the other columns).
- **AI Chat — the Professional Dashboard saves to Excel.** It had Download PDF only, although the cost answer advises exporting the one-pager to Excel. A **Download Excel** button now sits beside Download PDF and saves the figures the page shows: the headline and verdict, the six key figures, SPI and CPI, the time status, planned vs actual by discipline, the EV vs PV gap by activity code and the monthly S-curve values (planned, earned, expected).
- **AI Chat — the Manager's briefing now has the answer charts (comment 33, the part left open).** The charts added to the chat answers were on screen only. The one-page Manager's briefing, and the PDF saved from it, now show under its S-curve the same charts as the chat: progress by discipline (done against planned), then the milestones running late in working days (or, when none are, the client items overdue). Every bar is the tool's own number.
- **Baseline Revision — a long list of logic changes in Word.** Above 60 changed links, Logic & sequence changes reached Word as thousands of loose text lines. Word now gets them as one table, one row per changed link (#, change, Rev.00 link, Rev.01 link, predecessor, successor, on critical path, WBS). Up to 60 links Word still draws each lane as the PDF shows it. The screen, the PDF and the HTML file are unchanged.
- **Bad Weather — Excel now has the whole report.** The workbook carried only the day list, causes, milestone impact and recovery. Its Weather Detail sheet now starts with the same figures as the PDF: the Execution Dashboard (Baseline Finish, schedule slip, Forecast Completion, what weather adds, Bad-weather Completion, expected bad-weather days), the days per month (net working / bad-weather / non-working), the Stop-Work Criteria table with the limits in use, and how each limit performed (limit, days flagged, highest value seen).

**Final P6 test completed on MAFI (comment 5).** MAFI (the revised schedule, 6,005 activities, 15,304 relationships, XML), Grain Bulk, Saint Gobain and Alstom were each imported and every figure the tool shows was compared with the value P6 wrote into the file, read by a separate reader that does not use the tool: 183 checks, all equal to P6. On MAFI, whose XML stores no total float, P6's float was rebuilt from P6's own remaining early / late finish dates and calendars, and the tool's float and critical flag equal it for all 3,215 open activities. Every feature was also run end to end on all four projects — run, preview, PDF, Word, HTML and Excel: 128 of 128 steps each; two-schedule features run on a schedule against itself report exactly no change. Fixed by this test:
- **Schedule Health — Resource Dependent activities are checked.** Only Task Dependent activities were counted, so every Resource Dependent activity was left out of all 13 checks (Grain Bulk: 1,466 where P6 has 1,467). P6 and DCMA count both as tasks.
- **Lag Report — a part-day lag is a lag.** A lag shorter than half a day was dropped because it rounds to 0 whole days (Saint Gobain: 182 lags where P6 holds 183 — one of 0.12 hours). It is now listed with its value in days (e.g. FS+0.01).
- **Update vs Update — the verdict line names the SPI change.** It read "SPI 0.0" on screen and "SPI 0%" in the PDF when the SPI did not move (the SPI itself was 0.99); it now reads "SPI change 0%", in whole percent like the screen's SPI.
- The check can be re-run on your PC at any time: `CONTROLYX_P6_FILES=<folder of schedules> pytest tests/test_p6_reconciliation_files.py`.

### Changed — Keyboard shortcuts: every feature has one, and all of them work (comment 42)
- **Removed: Previous feature (Ctrl+[) and Next feature (Ctrl+]).** They are gone from the keyboard, from the View menu and from the Help list.
- **Every feature now has its own shortcut**, in the same order as the navigator. Alt+1 Overview · Alt+2 WBS · Alt+3 Schedule (Gantt) · Alt+4 Schedule Health · Alt+5 Baseline Narrative · Alt+6 Lag Report · Alt+7 Earned Value · Alt+8 Out of Sequence · Alt+9 Update Analysis · Alt+0 Critical Path · Alt+Shift+1 Update vs Update · Alt+Shift+2 Consultant Review · Alt+Shift+3 Baseline Revision · Alt+Shift+4 P6 Calendar Audit · Alt+Shift+5 Bad Weather · Alt+Shift+6 Reporting Studio · Alt+Shift+7 Productivity & Resources · Alt+Shift+8 Knowledge Base · Alt+Shift+9 AI Chat · Alt+Shift+0 back to the import screen. Before, only seven features had one. (Earned Value moves from Alt+1 to Alt+7 so the numbers follow the navigator.) Recent Projects stays on Ctrl+Shift+R.
- **Ctrl+Enter runs every feature.** It already pressed Run on the features with one schedule and on the comparison features. It now also presses Schedule Health's "Run Schedule Health Review" on the milestone step, the Baseline Narrative's Continue / Generate, and the Reporting Studio's Preview. On the two library pages, which have nothing to run, it says so instead of doing nothing.
- The shortcut shown beside each feature in Help ▸ Feature Guide, in the navigator tips and in the command palette is the one that fires.
- **All shortcuts were pressed one by one in the app** — 59 checks: the 20 jumps, Ctrl+Enter on each of the 18 features, and every File, Run, Navigate, View and Help shortcut — and all work.

### Changed — Word: charts are real, editable Word content, not pictures (comment 41)
- **The Word file now matches the PDF as Word, not as a picture of it.** Every chart, gauge, ring, tile row and dashboard card is rebuilt in Word from the PDF's own drawing: each bar, track, ring segment and card border is a Word shape you can select, recolour, resize or delete, and each label and number is Word text you can click and retype — in the same font, size, colour and position as the PDF. There is no picture left in the file. Tables were already real Word tables.
- This applies to every report saved from the print preview (Schedule Health checks and summary, Lag Report, Out of Sequence, Earned Value, Update Analysis, Update vs Update, Critical Path, Consultant Review, Baseline Revision, P6 Calendar Audit, Bad Weather, Overview, WBS, Gantt, Productivity, Knowledge Base) and to the Reporting Studio's Word file, where reused report sections used to be placed as page pictures; they are now Word shapes and text as well.
- **Same fonts as the PDF.** Word now uses Segoe UI where the PDF does (some reports came out in Arial), including its Semibold and Black weights, so text has the same width and line breaks.
- A chart taller than a page is continued on the next page between two rows of cards, never through a card.
- The file opens quickly: the labels of one chart share a few transparent text layers instead of hundreds of separate text boxes.

### Fixed — Schedule Health: the file's milestones after re-opening a project
- After a project was re-opened from Recent Projects, **Step 1 · Enter your contract milestones** said "0 milestone activities found in the file" and offered no names to pick. The file's milestone activities are listed again (36 on the Grain Bulk baseline), exactly as after a fresh import.

### Changed — Every report saves as PDF, Word, HTML and Excel from the same preview (comment 2)
- **The preview of every report now has four save buttons: PDF · Word · HTML · Excel** (plus Print). Before, only Earned Value, Calendar Audit and the Gantt offered Word and HTML. This covers the Schedule Health checks and summary, Lag Report, Out of Sequence, Update Analysis, Update vs Update, Critical Path, Consultant Review, Baseline Revision, Bad Weather, and the screen views printed with File ▸ Print (Overview, WBS, Productivity, Knowledge Base).
- **Word looks like the PDF.** Charts, gauges, tile rows and dashboard cards go into Word as editable Word shapes and text that look exactly like the PDF (see comment 41 above); tables stay real Word tables and text stays text. What you untick in the Report Contents list is left out of Word and HTML too.
- **Excel from the preview is the feature's complete workbook** — every table with all its rows and every chart as its numbers (the workbooks completed under comment 29).
- **Fixed:** the bars of the Lag Report charts were almost invisible (in the PDF as well); they now use the report's accent colour.
- **Fixed:** in Update Analysis, "Planned vs Actual by count" was split into three oddly named parts in the Report Contents list; it is one item now.
- **Overview, WBS and the Gantt** now have the Excel button in their print preview too (their own workbook), and the P6 Calendar Audit preview saves its complete workbook (Summary, monthly working time, calendar issues) instead of a shorter extract.
- **Knowledge Base:** File ▸ Print / Export to PDF, Word, HTML and Excel now work on the Knowledge Base page (the menu said "This view has no report"); the page's Export ▸ PDF preview carries the Excel button too.
- **Fixed:** small display flaws — the Gantt's first month label no longer prints under the next month when only a few days of it are shown; "Last period:" in Update vs Update has its space back; the Excel Summary sheets write "Lagged %" instead of "lagged pct".
- **Lag Report Excel:** the Summary sheet no longer shows a score and grade (the Lag Report itself has none). **Baseline Revision Excel:** a difference such as −0.06 is no longer written as −0.06000000000000005.
- **Reporting Studio:** a feature whose results are only partly available now reads "18 of 21 ready" instead of "No data" (the ready results could always be ticked; the badge was misleading).
- **Fixed:** in Word, a narrow table column broke its values across lines (row number "10" as "1" over "0", an Activity ID after its last digit). Every column is now at least as wide as its longest word; the room comes from the wider columns.
- Known limit: in the Baseline Revision report, the very long change lists (thousands of rows) go into Word as plain text lines, not as formatted tables.

### Changed — Every report: pick any sub-feature, or any single table / chart inside it (comment 1)
The print preview's **Report Contents** list has two levels: tick a whole section, or open it (▸) and tick single parts. Until now only Earned Value and Calendar Audit had the second level.
- **All reports now list their parts.** Inside each section the single tables, charts and tile groups are found automatically and named (for example "Lags by relationship type", "Table — Activity ID · Activity Name"). Unticking one removes just that piece from the preview, the PDF and the print-out. This covers the Schedule Health checks and summary, Lag Report, Out of Sequence, Float, Consultant Review, Baseline Revision, Bad Weather, and the screen views printed with File ▸ Print (Overview, WBS, Gantt, Productivity, Knowledge Base).
- **Update Analysis, Update vs Update and Critical Path** now open the same preview as every other report (they had their own older one with whole sections only). Their parts are named — e.g. each milestone's path, each dashboard chart, "Recovery outlook", "Scope weight bars" — and sections can be dragged to reorder. Their own options stay in the preview, under the list: the activity-code filter and critical-path style (Update vs Update), and which milestone paths to draw (Critical Path).
- The Schedule Health summary keeps its cards whole: each card is one tick.
- Nothing changes when everything is ticked — the reports look and paginate as before.

### Added — Knowledge Base: 48 more project types, with every infrastructure network (comment 38)
The library grows from 77 to 125 project types. Each new type is a full page — plain-language brief, scope, key terms, what must be got right, components, sequence of work by trade, suggested WBS, basis of planning with long-lead items — and each downloads as a detailed baseline (about 1,200 activities) and as Excel.
- **New shelf: Infrastructure Networks (17 types).** Every network is now its own project type: Potable Water Supply · Sewerage (gravity sewers & rising mains) · Stormwater Drainage · Irrigation & TSE · Fire Water Ring Main & Hydrants · Overhead Transmission Line · Underground Power Cables (HV / MV) · Power Distribution (MV / LV) · Street Lighting · Telecom / Fibre · Gas Distribution · Cross-Country Pipeline · District Cooling Network · Traffic Signals & ITS · Common Utility Tunnel · and **Site Infrastructure — Roads & All Utility Networks**, which explains how the networks are sequenced together (deepest first, tested before being covered, road crossings before road base).
- **Industrial & Manufacturing (22 more):** Precast Concrete · Ready-Mix Batching Plant · Asphalt Plant · Brick & Block · Ceramic & Tile · Gypsum Board · MDF / Wood Panel · Rebar Rolling Mill · Pipe Factory · Cable & Wire · Automotive · Battery Cell (Gigafactory) · Semiconductor Fab · Textile · Sugar · Tyre · Plastics · Paint & Coatings · Furniture · Aluminium Smelter · Shipyard · Steel Structures (fabrication & erection).
- **Power & Energy (6 more):** Battery Energy Storage (BESS) · Green Hydrogen · Hydropower · Nuclear · Concentrated Solar Power · EV Charging Infrastructure. **Oil, Gas & Process (2 more):** Fertilizer / Ammonia-Urea · Offshore Platform / FPSO. Also **Light Rail / Tram** and **Irrigation Canals**.
- 13 of the networks also get a starter baseline entry, so the tool can recognise those schedule types.

### Changed — Knowledge Base baseline files and Excel
- **Detailed baseline (XER): each trade's activities now sit under their own WBS branch.** Before, all the trades of one discipline were placed under the first branch of that discipline (for example, pipe laying under "Fire Water Tank"), and some under Procurement. Now a trade goes to the branch that carries its name. This also corrects the 77 existing types.
- **Knowledge Base Excel** now includes the sequence overview, the chart-by-trade figures and the list of standards, and opens with a title line.

### Changed — Excel exports now carry all the data of each feature (comment 29)
Every feature's Excel was compared, table by table, with what its screen and PDF show. Where the workbook had less, the missing parts were added as extra sheets — the existing first sheet of each workbook is unchanged.
- **Baseline Narrative Report** — the Excel was a short status summary. It is now the whole report: one sheet per section (all 19 — overview, brief, milestones, key dates, contract value, scope of work, calendars, WBS, activity codes, sequence, activity IDs, resource loading, materials, productivity, volume of work, critical path and the appendices), every table with all its rows and every chart as its numbers. A new **Export Excel** button sits beside Word / PDF / HTML on the Narrative screen and follows the Report Contents selection.
- **Schedule Health checks (all 13)** — besides the findings list, each workbook now has a **Summary** sheet (score, grade, how the score was worked out, all key figures, the severity rules), a **By WBS** sheet, the **Management View** for Float Analysis, and the schedule's own milestones for the Milestone Check.
- **Calendar Audit** — added **Summary** (key figures, conclusions, working time and working-hours patterns per calendar), **Monthly Working Time** for every assigned calendar, the exceptions of the other calendars, and **Calendar Issues**.
- **Critical Path Analyzer** — the Float migration sheet now lists every activity behind the four counts, with its total float before and now.
- **Update vs Update** — added **S-Curve** (the monthly figures), **Progress by Code** (every activity code, not only the first), **Critical Path** (previous and current lists) and **What Moved** (the activities behind each count).
- **Update Analysis** — scope weight for every activity code, not only the one shown first.
- **Consultant Review** — the milestone table (baseline finish against update finish).
- **Constructability** — the WBS review, findings by work stage and what to look at first.
- Checked and already complete: EVM, Overview, WBS, Schedule (Gantt), Baseline Revision Comparison, Productivity, AI Copilot.

### Added — AI Chat: charts in the answers (comment 33)
- **Each answer now shows the one or two charts that fit its question**, right under the short answer: where the project stands (SPI, progress, days late) and progress by discipline; milestones by working days late; the critical path by area; how total float is spread; what to fix in the schedule logic; value of work planned against done by package; design approvals planned against received; client items by working days late. 14 of the 15 questions get charts; the weather question has no figures in the P6 file to chart.
- Every chart is drawn from the tool's own numbers — the same ones the answer quotes — and follows all six appearance modes. A chart whose figures are not in the file is left out, never drawn empty.
### Fixed — AI Chat dashboard
- The month labels under the S-curve no longer print on top of each other near the data date, and the first and last labels stay inside the chart.
- The Start and Finish labels of the time bar stay inside the card.
- When the finish is late but the value of work done is ahead of plan (or the reverse), the headline now says what that means instead of only "BEHIND · SPI 1.63".
- The Delay tile reads "+104 days" (working days) instead of "+104 wd".

### Changed — AI Chat: every answer is now short, clear and tells you what to do (comment 14)
- **Each of the 15 answers opens with four short parts: The problem · Where it is · Why · What to do.** About 150–270 plain words instead of 2,000–10,000. It names the activity (name and ID), its area, its planned and forecast dates, and the numbers from your P6 file.
- **Advice you can act on.** For example, instead of "aim recovery at the chain that sets the finish": "Start Drilling For Piles (CONS.PL.S9.1000) now. Ask the team responsible why it has not started and get a firm start date. Each day it waits adds a day to the finish." At most four steps, each naming the activity or the screen to use.
- **The full analysis is still there**, one click away under "Show the full analysis" — the detailed tables, each library question one by one, and how each figure is measured.
- **No planner shorthand.** "wd", "chain", "trunk", "danglers", "TIA", "EOT" are written out ("working days", "critical path", "activities with a missing link", "time impact analysis", "extension of time") in the answers, the tables and the follow-up questions. Activity names are never reworded.
- **It says only what the file shows.** No late client item in the file: it says the delay reads as the contractor's own. No real actual cost: it says CPI means nothing. Project on time or ahead: it does not talk about a delay.
- Copy puts the short answer first, then the full analysis.

### Fixed — AI Chat: answer paragraphs were written out but stayed invisible
- The word-by-word writing added for comment 15 left every paragraph of an answer invisible (headings, tables and chips showed; the sentences did not). The text is now visible as it is written and after it.

### Added — AI Chat: Stop and Copy, like Claude (comment 15)
- **Stop.** While an answer is being worked out or written on screen, the Send button becomes a red Stop button. Pressing it while the answer is still being computed cancels it ("Stopped. Ask again whenever you are ready."); pressing it while a finished answer is being written shows the whole answer at once.
- **Copy.** Every answer has a Copy button. It puts the answer on the clipboard as clean text — the verdict, the key figures, each section, the actions — with tables tab-separated so they paste into Excel or Word as tables.
- **It analyses first, then writes.** After you click a question the chat shows its analysis steps one at a time ("Analysing your P6 file…"), then writes the answer out a few words at a time, with tables and figures arriving whole.
- Already in place and unchanged: your question appears as your own message, and follow-up questions are offered under the answer. Enter sends; Shift+Enter starts a new line.

### Added — AI Chat: download the dashboard as a PDF (comment 39)
- **A "Download PDF" button on the Professional Dashboard.** It saves the dashboard exactly as shown — same figures and charts, in the format you picked (Executive, Midnight or Blueprint) — on one A4 landscape page with a report head line (product, "Professional Dashboard", date generated). The file is named after the project.
- **Amounts no longer carry a pound sign.** The dashboard printed "£" on every amount although the P6 file does not say which currency its costs are in; amounts now read "370.4M".
### Fixed — Baseline Narrative: the 31 failing automated checks, and what they uncovered (comment 23)
- **The Reporting Studio offered only 11 of the Narrative's 19 sections.** Activity IDs, Resource Loading, Material Resources, Productivity Rates, Volume of Work and the three appendices (Critical Path, Critical Path From P6, Mapping Sheet) can now be picked into a Studio report too.
- **Scope of Work ignored an activity code named "Discipline"** when the schedule also had a "Type of Works" code, and used the work type as the discipline. A code named Discipline is now the discipline, and Type of Works the work type under it. Grain Bulk, Saint Gobain, MAFI and Alstom are unaffected (none has a code named Discipline).
- **"1 calendars assigned"** now reads "1 calendar assigned" in the PDF and in Word.
- **Project Brief table** is kept whole on one page when the Narrative is printed through the Reporting Studio (it could be cut after six rows).
- The remaining failures were checks written for the first version of the report and never updated after the section-by-section review. They now check the approved report: the 19 sections in order, the WBS overview and branch breakdown (Level 4 when a branch has four or fewer Level-4 nodes, else Level 3), the sequence read from the logic, the calendar section, and the Word look (logo-only header, cover, Times New Roman body, native charts and drawings with no pictures).

### Fixed — Baseline Narrative: critical path on a baseline exported without float (comment 17)
- **The Narrative said "no critical path" on the Saint Gobain baseline.** That XER was exported with the Total Float column empty for every activity. The float is now rebuilt from each activity's own early and late dates, exactly as P6 computes it, so the Appendix (Critical Path) is drawn: 223 critical activities, 19 Dec 2024 to Project Completion 30 Aug 2025. Grain Bulk is unchanged (410 critical activities).
- When a file carries neither float nor early / late dates, the report now says what to do: schedule the project in P6 (F9), export it again and re-import it.
### Fixed — Productivity & Resources: the settings now change the rate (comment 37)
- **Project type, Location and Methodology did nothing** — the library holds one norm per work item and no factor for any of them, so changing a setting never moved a rate. Each setting now has a **"your factor ×" box**: type your own man-hour factor for that choice (1.20 = 20% more man-hours, slower; 0.85 = faster) and every rate, man-hour figure and duration follows it. The factor is remembered for that choice on this computer, so switching country switches the factor.
- **A factor now also changes the output per day and the duration.** Before, a factor could only touch the man-hours, leaving the crew output and the duration unchanged.
- **The screen says what each setting did**: "your factor ×1.25", or "no factor, library norm". An adjusted rate shows the library norm it came from. Controlyx supplies no factor of its own.
- **Project type** also warns when the chosen work item is not normally part of that kind of project.
- The Excel lists the factors and the library norm beside the adjusted rate. Messages on this screen appear in the page (pop-ups did nothing in the desktop window).

### Fixed — Schedule (Gantt): shown after re-opening, current dates, true WBS groups, and it prints (comment 26)
- **The Gantt (and the WBS view) is still there after a project is re-opened from Recent Projects.** Their rows are now stored with the import; a project imported with an older version is rebuilt once from its saved schedule file, then read from the database.
- **Bars use the current dates, as P6 shows them in Start / Finish:** actual dates where the work has started or finished, the remaining early dates for the rest. They used to be drawn from the Planned dates, so on a progressed update finished work appeared in the wrong place.
- **Grouping is by the real top-level WBS.** The old chart grouped by each activity's lowest WBS name and merged different WBS that shared a name (e.g. every "Civil"). The WBS path now reads from the top level down.
- **Start and Finish columns, a pinned activity column and a pinned month header**, so a bar can always be tied to its activity and date however far the chart is scrolled. Hovering a row shows its dates, status, % complete, total float and WBS.
- **Critical milestones are red** (they were always dark); finished work is never shown as critical. The legend says "not critical" instead of "on track".
- **File ▸ Print / PDF / Word / HTML now work for the Gantt** (it was Excel-only): a summary plus one table per WBS group with the bar on a page-wide time scale, with the Report Contents picker. The Excel gains Status, Planned Start / Finish and Total Float.
- **Any printed screen report longer than one page was cut off after its first page** (Overview, WBS, Gantt) — fixed.

### Changed — Opening Controlyx: the small dark unpack window is removed (comment 40)
- **The small dark window that appeared first — with a line naming each file being unpacked — is gone.** The first thing on screen is now the app window with its loading screen counting to 100 %. The loading screen keeps the same dark look it had before. Note: the exe still needs a few seconds to unpack itself after the click, and nothing is shown during those seconds.

### Changed — Reporting Studio lists the analysis features only
- **The Overview group is no longer offered in the Reporting Studio** (Project snapshot, Key indicators, Progress by category). The list now starts at the analysis features, so you choose among their results. The Overview screen itself is unchanged and keeps its own Print.
- A report you saved earlier that included Overview results still opens: those results are left out, the screen says how many, and the report exports as before. Saving it again stores it without them.


### Fixed — Reporting Studio reports print at full size and break cleanly
- **A Studio report no longer prints small.** When one part of a report was wider than the page, the whole PDF was shrunk to two-thirds size — body text near 5 pt and one table at 2.7 pt, too small to read. Reports now print at full size. The page checker also flags any report whose text prints too small.
- **Consultant Review — driving logic table.** Inside the Studio it uses a portrait layout: each side's predecessor and successor links are stacked in one cell (ID, relationship, name). Same rows, same data; the Consultant Review's own landscape report is unchanged.
- **Update vs Update.** The critical-path comparison wraps onto a second line instead of running off the page, and each block shows its full name (long names were cut). The milestones drift chart is readable on a portrait page. The same on screen.
- **Critical Path Analyzer.** A path title is never left alone at the bottom of a page; the "New on path / Left path" label sits inside its card; day counts read as P6 shows them (−42.7 wd, not −42.666666666666664) in the report, Excel and on screen.
- **Baseline Revision.** Each finding prints on one row as on screen (predecessor → link → successor), about three to four findings a page instead of one; a finding is never cut by a page break; total float is rounded.
- **Word from the Studio matches the PDF.** The Word button now exports the .docx built from the same content and page layout as the PDF (tables and text editable, chart sections as pictures).


### Changed — Help, the version shown and the release check
- **Help, About and What's New show the real version.** The version is read from the newest release in this changelog, so it can no longer show an old number (Help used to name a release six versions old). **Help ▸ What's New** now lists that release's changes, read from the same changelog, plus the changes already in this build.
- Help ▸ Getting started now says "P6 XML or XER export".
- The release build now stops if the version being released has no matching section at the top of this changelog, so the app can never ship showing an old version number.

### Fixed — The app sometimes opened on a black screen
- **Cause:** the start-up screen was only removed once every program file had loaded. If one file failed to load (for example while antivirus was scanning the freshly unpacked app), the window stayed black with no message, and only closing and reopening helped.
- **Now:** the app retries a file that fails to load, reloads itself automatically if needed, and if it still cannot start it shows a message with a **Retry** button instead of a black window. A slow start says "Still starting…".
- **Faster start:** the app no longer loses time on every file it loads through its own local connection. In tests the start-up page loaded in about 0.1 s instead of about 3 s.
- **Damaged history database:** the app now opens anyway. The damaged file is kept as a backup, a fresh one is started, and a notice explains it. Recent Projects says when it cannot load and offers Retry.
- **Opening the app twice** brings the window that is already open to the front instead of starting a second copy.
- **The app's first page is held by antivirus for a moment:** the window now says "Starting…" and tries again by itself, instead of showing a line of technical text on a white page.
- **The window's web view does not start at all** (a graphics or WebView2 problem on this PC): the app now opens itself again once in a safer graphics mode and closes the black window, so you no longer have to close and reopen it yourself. If the page itself is running, it is never restarted over its own Retry message.
- Start-up problems are written to a log file (`logs\startup.log` in the app's data folder) so a future problem can be traced.
- **Help ▸ Contact & Support ▸ Safe graphics.** If the window ever opens black, tick **Safe graphics**: the app then draws its window without the graphics card from the next start. The app turns it on by itself after a start that never showed the page; the same switch turns it off again. It says whether it is on, since when and why.
- The app's local connection now queues a burst of requests at start-up instead of refusing all but 5 of them (in a test, 40 requests at once: all accepted, where before 34 were refused; one refused program file could leave the window black).
- **Something shows at once when you double-click the app.** The single-file app first unpacks about 1,000 files (about 230 MB) before it can start, and nothing was visible for those seconds, so it was easy to click again. A start-up picture now appears straight away, with a line saying what it is doing, and closes when the app window opens.
- **The window's web view starts from the same folder each time.** Before, it built a brand-new temporary profile at every start (while the window was still dark) and could leave folders behind in the Windows temporary folder. It now keeps one folder in the app's data folder and reuses it. If a start never showed the page, that folder is started afresh next time; if another copy of the app is still running, that start uses a separate folder so one stuck window can never stall the new one. Your screen preferences are kept exactly as before.
- **Help ▸ Contact & Support ▸ Open log folder.** Opens the folder with `startup.log` so you can send it to support, and always shows where the file is. The log now also records when the window appeared and when the page finished loading, so a slow or black start shows which step was late.
- **The loading screen now tells the truth.** Before, the opening screen was plain dark while the program loaded, then the loading presentation walked through made-up steps ("Loading knowledge base", "Loading calendars", "Ready") on a fixed timer, whatever was really happening. Now the loading screen appears from the very first moment and shows the real steps: **Starting local server** (until the app's local server answers), **Loading program files**, **Building the screen**, **Opening project history**. The bar never gets ahead of a step that has not finished, and **Ready** only shows when everything is done. The presentation keeps its usual length. If the start fails, the loading screen gives way at once to the message with **Retry**, instead of finishing onto an empty window.
- The product name on the loading screens, the menu bar, the account panel and the start page now comes from one place, like the rest of the app. Nothing on them spells it out separately.
- **The start-up picture now really ships in the released app.** The picture file was never saved with the project, so the released app was built without it and nothing showed while it unpacked. It is now part of the project, and the release build stops with an error instead of quietly leaving it out.
- **Closing and reopening straight away no longer waits 12 seconds.** When the copy you just closed was still shutting down, the new copy waited the full 12 seconds before opening. It now opens the moment the old copy has gone (in a test: after 1 second instead of 5 of a 5-second wait), and does not wait at all for a copy whose window is already shut. The start-up picture says it is waiting.
- **A damaged project history database is now found and can be replaced from the app.** Damage inside the stored records (not just the file header) used to pass the start-up check, and then Recent Projects failed on every Retry with no reason given. The app now checks the database in the background after the window appears. Recent Projects shows the real error, and a notice offers **Set the damaged database aside and start fresh (a backup is kept)**. Every record that can still be read is copied into the new database, and the damaged file is kept as `controlyx.db.corrupt-bak-<date>`.
- **A black window caused by the graphics card is now recovered.** If WebView2's graphics process fails, the app reloads the page and turns on Safe graphics for later starts. If it fails a second time, the app opens itself again once in Safe graphics. If WebView2 itself stops, the app opens itself again once and closes the dead window. The app now watches for this from the moment the window opens. Before, it started watching only after the page reported ready, so a failure during start-up went unnoticed and the page could say "ready" over a black window.
- **Safe graphics is switched on only when the graphics really are the problem.** Before, closing the "couldn't finish starting" message (for example after antivirus held a file) or closing a slow first start after 8 seconds turned Safe graphics on for every later start, so charts and the Gantt were drawn more slowly until it was switched off in Help. Now it is switched on only when the page never appeared at all.
- **A slow first start is no longer treated as a failed one.** If the app's start-up check could not answer while the program files were still loading (for example while antivirus scanned them), the page reloaded itself three times and then showed Retry, although it would have opened a few seconds later. It now keeps waiting; a real failure is still caught.

### Fixed — Dark report PDFs had a white border
- In the Dark, Midnight, Blueprint and Sepia looks, every PDF page had a white frame round the edges (the page margins). The whole page is now coloured, on every page, with the same margins and page numbers as before. Checked on the Earned Value and Baseline Revision Comparison PDFs. Light and High-contrast PDFs, Word and Excel are unchanged.
- Re-checked on the finished tool across all six looks: Schedule Health (summary and float), P6 Calendar Audit, Bad Weather, Earned Value, the Reporting Studio document and the Report Contents export — every page of all 42 PDFs is coloured to the sheet edge, and a Word file exported while the app is in a dark look comes out white with dark text. A new check now stops any future report from printing a white frame in a dark look.

### Fixed — Web links and online services
- **Every web link opens in your web browser.** LinkedIn (Help ▸ Contact / About), the map's Leaflet and OpenStreetMap credits and the Open-Meteo weather-source link now open in your default browser instead of taking over the app window. If a link cannot be opened, a note shows the address to copy. Only these known sites are allowed.
- **Bad Weather without internet:** the tool now says plainly that it could not reach the weather service and keeps your last estimate. It no longer shows (or saves) an empty download as "zero bad-weather days". Missing forecast or dust data is listed on screen and in the PDF with its source. It stops after the first failed call instead of waiting on every year.
- **Bad Weather PDF with no estimate yet:** if no weather estimate has been saved (for example the first Calculate ran with no internet), each section you tick keeps its heading and says "No data available" instead of printing an empty report. No figures are made up.
- **Place names are in English.** Place search and naming a pinned site used to return names in the local script (for example Arabic for Dammam), which then appeared on the Bad Weather screen and in its PDF.
- **Place search without internet** says you are offline, not "no match". Typed coordinates (for example `31.26, 32.30`) and the map pin still work offline. When the map tiles cannot load, a note says so.
- **AI Chat brain download:** the larger (7B) brain pointed at a file the download site does not have, so it always failed. It now downloads the two published parts. A download that is cut short is never installed. The tool checks free disk space first. When offline it shows a plain message, and the setup buttons come back.
- **AI Chat brain download continues where it stopped.** If the internet drops, the tool tries again by itself after a short wait (3, 10 and 30 seconds) and keeps what it has already downloaded. If the connection is still down, it says so and keeps the downloaded part. Press **Set up the AI brain** again when you are back online and it continues from that point, not from zero (the brain is 2 to 4.7 GB). A file that changed on the download site is started again, never joined onto an old part.
- **No long waits on a blocked network.** When the internet is blocked rather than simply off (a firewall, a hotel or site Wi-Fi login page, a broken proxy), place search and Bad Weather now give up connecting after about 6 seconds and say the connection looks slow or blocked. Before, the place search waited 15 seconds and Bad Weather 20 seconds. A slow but working weather service still has time to send five years of history. The dust data is now fetched at the same time as the weather history, not after it.
- **The map says when the connection is lost after it has drawn.** Before, the "no internet" note only appeared if no part of the map had ever loaded. Now it also appears when you move the map after the internet drops, and it goes away when the map pictures load again.
- **AI Review:** when the AI service does not answer in time, the message now says so. Before, it said the service "returned an unexpected response". A connection that drops mid-answer gives the same plain network message.
- The online services identify the app honestly, as their usage rules ask. All addresses were checked: the 3 web pages, the 6 online-service calls and the 3 brain downloads answered HTTP 200. LinkedIn answered with its usual reply to automated checks (999), which means the site is up.

### Fixed — Your settings are kept
- **Project Setup category weights and Actual Cost** are saved with the project, so they come back when you re-open or re-import the project and after the app is closed and opened again. Before, they were kept only by the app window, which forgot them at restart.
- **Screen preferences** (Appearance mode, Report Contents choices, table and chart choices) are kept when the app restarts. Before, the app window forgot them each time it was opened.
- **Baseline Narrative project setup** (location, contract type, revision, parties, logos and the layout drawing) is saved with the imported schedule in the app's database, so it is filled in again after the app is closed and opened. Before, it was lost at every restart, and a setup with a layout drawing was too large to keep at all. When you re-import the schedule or import its next update, the project's last setup is filled in; your first change saves it with the new import. Before, the setup started empty after a re-import.
- **P6 Calendar Audit:** saving a shutdown reason or working-hours note no longer clears the notes already saved on other rows. If a note cannot be saved, the screen says so.
- **Bad Weather:** the location, Site Type and weather limits stay as you last set them when you run the feature again in the same session. Before, they went back to the values from when the file was imported. They are also saved when the weather service cannot be reached.
- **Lag & Lead justifications:** if a reason cannot be saved, a note beside the box says so and asks you to edit it again. Before, a failed save gave no message.
- **Schedule Health contract milestones:** **Edit contract milestones** now shows the milestones you saved. It used to open empty after a run or a re-import, so running again kept only the rows you typed again. Blank rows are ignored. If the milestones are saved but cannot be checked against the baseline, the screen says so.
- **AI Chat:** if the AI brain you choose cannot be saved on this PC, the chat says so. Before, the app went back to the previous brain at the next restart and gave no message.

### Changed — One baseline rule for XER and XML
- **Every feature finds the baseline the same way:** the baseline inside the file (an XML exported with its baseline project), otherwise the baseline you attached for that update. An update plus its attached baseline now gives the same results as the XML exported with its baseline, whether the update is XER or XML.
- **Attach a baseline (XER or XML) to an XML update too**, not only to an XER. Before this, an XML exported without its baseline showed zero Planned Value and no SPI, and there was no way to fix it except re-exporting.
- **The attached baseline is used everywhere,** not only in Earned Value. Update Analysis, the weekly report, the gap chart, WBS, P6 Calendar Audit, Bad Weather, Update vs Update, Critical Path, Reporting Studio and AI Chat all use it. It stays attached when you re-open the project or import the same file again.
- **Update Analysis:** an update with no baseline inside it and none attached is no longer measured against its own planned dates. The screen says so and offers **Attach baseline (XER or XML)** on the spot.
- Without a baseline, an XML now shows the same approximate figures as the XER, marked approximate, where it used to show zeros.
- A baseline from another project (no Activity IDs match) is refused and never remembered.
- **The tool names the baseline P6 expects.** When the update names its baseline (an XER always does; an XML does when exported with it), Earned Value and Update Analysis say which P6 project to export and attach. If the file you attach is a different project or revision (for example REV.01 instead of REV.03), or leaves some of the update's activities out, the banner turns amber and says so — "P6 names X; you attached Y" — and every report's Baseline line says it too.
- **"Approximate" is marked everywhere, not only on Earned Value.** When the update carries no baseline and none is attached, its own planned dates stand in. Every value that depends on the baseline is now marked "approx", with one "Baseline:" line: Project Overview, WBS, P6 Calendar Audit (the tile reads "Baseline (approx)", not "plan of record"), Bad Weather, Critical Path Analyzer, Update vs Update and the Earned Value Planned % figures. The mark appears on the screen, in the PDF and in the Excel file.
- **Reporting Studio follows the Update Analysis rule.** An update with no baseline inside it and none attached shows its Update Analysis results as "needs input", with the reason. They are never measured against the update's own planned dates.
- **Command line: `--baseline PATH` (XER or XML).** The terminal version (`cli.py`) can now be given the baseline for an update that does not carry it, and it prints a **Baseline:** line first. Without a baseline its Planned Value, SPI, Planned % and Delay are marked approx. Before, an XER update printed figures measured against its own planned dates as if they were exact.
- **Projects imported before this version re-open with the right baseline.** The first time such a project is opened from Recent Projects, it is recalculated once, the same way as a new import. An XML exported without its baseline then shows the approximate figures and the **Attach baseline** button, instead of zero Planned Value and nothing to click.
- **Earned Value names the baseline inside the file on screen too**, e.g. "Baseline: inside the schedule file (…Rev.01 Clean)", the same line as the PDF. The Excel header now carries the baseline's name as well.
- **The baseline attached to an update now fills the Baseline slot in Critical Path Analyzer, Consultant Review and Reporting Studio.** It is named "attached to this update", and you can still pick another file (or go back to the attached one). The reports name your baseline file, not the copy the tool keeps. Before, each of these asked for the baseline file again.
- **Attaching a baseline is faster:** the update and the baseline are each read once, not twice (on a large schedule this saves about 20 seconds). The "nothing to attach" message now says XER or XML to match your file. After removing a baseline, the Attach offer and the approx marks come back straight away.
- **An XML that carries more than one baseline project** is measured against the one P6 names as the project's current baseline, the same rule the XER uses. Before, the XML took whichever came first.
- A failed baseline attach is now shown on the "No baseline is assigned to this project in P6" banner too. Before, nothing visible happened.
- "Import baseline XER" (Earned Value) and "Baseline XER" (Reporting Studio) are now labelled **XER or XML**.
- **An XER that includes its baseline project is read like the XML with it:** the baseline dates and baseline budget come from the baseline project inside the file, so Planned Value, SPI and Delay match the XML. A normal XER update export (which carries only a pointer to its baseline) still names the baseline it needs, so you know which file to attach.
- **24-hour calendars in XER files:** a 24-hour working day (and a shift that runs to midnight) was read as a non-working day, and a 24-hour exception day as a holiday. They now count as working, the same as in the XML, so working hours, float in days, lags and P6 Calendar Audit figures match.
- **XER WBS no longer starts with the project name:** the project's own top node was read as a WBS level, so every WBS path gained the project name, the WBS view gained an extra level and the top-level branches collapsed into one (for example a whole civil package filed under Construction in Out-of-Sequence). The XER WBS now matches the XML.
- **XER activity status and constraints read in P6's words** (Not Started / In Progress / Completed, Start On, Finish On or Before, Mandatory Finish, ...). Completed activities in an XER were never seen as completed by Float Management and Engineering progress, and hard constraints were invisible to the Hard Constraints and Milestone checks. The secondary constraint is now read from both formats.
- **Total Float from an XML now equals P6's:** P6 does not write activity float to the XML, so it is rebuilt from the early/late dates. It was rebuilt as start float in whole days; it now follows the project's "Compute Total Float as" option (Finish Float by default) in working hours on the activity's calendar, the same number the XER carries. Critical flags, negative-float counts and CPLI now match between XER and XML.
- **Total Float from an XER with no float stored:** some XER exports (for example an unscheduled baseline) leave every activity's float blank, so no float, no critical path and no CPLI came out. The float is now rebuilt from the early/late dates the same way as for the XML.
- **XML working hours are no longer one minute short:** P6 writes the end of a shift as its last working minute (15:59), which was read as the end, so an 8-hour day counted 7.97 hours (and 10.97 for 11). It now counts 8.0, the same as the XER, in the P6 Calendar Audit and in Planned %.
- **An XML with its baseline no longer lists the baseline's calendars as project calendars.** The calendar count and the P6 Calendar Audit now show the same calendars for the XER and the XML (no extra "Unused calendar" conflicts).
- **Calendar type and default read from the XER too:** the P6 Calendar Audit now shows Global / Project / Resource and which calendar is the default for an XER, and the working weekdays for an XML, so both formats show the same calendar table.
- **Project dates read from the XER too:** the project's Planned Start, Scheduled Finish and Must Finish By now come from an XER as they do from the XML, so the P6 Calendar Audit's project window is no longer blank for an XER. Must Finish By is now read from both formats.
- **Quotes and line breaks in XER names:** P6 writes a " inside an XER name as "" and a line break as two hidden characters. Both were shown as written (for example `65"" inch`, or a box character in an activity name), and resources with a " in their name or ID did not match between the XER and the XML. They are now read as the real " and line break, the same as the XML.
- **Lags in days follow P6's lag calendar:** a lag in hours was turned into days on the successor's calendar. P6 counts it on the calendar set in the project's "Calendar for scheduling Relationship Lag" option (the predecessor's calendar by default, as in every schedule tested). Lags between an 8-hour and a 24-hour calendar showed up to 3 times too long or too short (35 such links in Grain Bulk REV.03). XER and XML are read the same way, and a lag kept by Out-of-Sequence Resolve & Correct is written back in the same hours.
- **Relationships listed in one order for XER and XML** (predecessor Activity ID, then successor, type and lag). The two files list links in different orders, so a finding that shows one example link (for example Lags & Leads) could quote a different link for the same schedule. The links themselves were always the same.
- **Calendars listed in one order for XER and XML** (calendar name, then its P6 ID). The two files list calendars in different orders, so the P6 Calendar Audit usage table and the "Unused calendar" findings listed the same calendars in a different order, on screen and in the report. The calendars themselves were always the same.
- **Activity code types from an XER are the ones this project uses:** the XER lists every code type in the file, including ones no activity in the project carries (Grain Bulk REV.03 showed 28 instead of 27). It now lists the same code types as the XML.
- **Units % Complete from an XER counts labour and nonlabour units**, as P6 does. It counted labour units only, so an activity with equipment units showed the wrong progress.
- **Resource price per unit from an older (P6 19.x) XML:** P6 19.x does not write the price on each resource assignment, so it came out blank for every assignment (1,561 in Grain Bulk REV.03). It is now taken from the assignment's planned cost / planned units, or the resource's rate when those are not linked, and matches the XER.
- **Dates read the same way from XER and XML, and an unreadable date is reported:** a date written with fractional seconds or a time zone (for example `2025-03-05T17:00:00.000` or `...Z`) stopped an XML import with an error and was silently left blank from an XER. Both formats now read these dates. A value that is still not a date is left blank, and the file bar after import says how many date values could not be read, with an example. All dates in the real test schedules are read exactly as before.
- **One set of resource types for XER and XML:** Labour / Equipment / Material mean the same in every feature, whichever file you import. A resource type P6 does not normally use is shown as written in both formats (an XER showed it as blank). The narrative report's resource loading uses the same types. An older XER's `RT_Nonlabor` resources were counted there as manpower and are now counted as equipment. Each resource's Unit of Measure is now read from both formats.
- **Free float:** P6 writes free float to an XER but not to an XML. No feature uses free float, and a test now stops a feature from using it until the tool can work it out for an XML as well, so an XER and an XML cannot give different answers because of it.

### Fixed
- **PDF exports could fail on some computers.** The tool used to pick a browser to print with that, on some PCs, cannot start at all ("side-by-side configuration is incorrect"), and it did not try another one. It now checks which browser can really print (Google Chrome first, then Microsoft Edge, then a spare built-in one), remembers the one that works, and moves on to the next if one fails. This applies to every PDF in the tool and to the pictures inside Word exports. If a PDF you are replacing is still open in another program, you now get a message asking you to close it, and the old file is never passed off as the new one.

## [v2.9.1] - 2026-09-29

### Fixed — Productivity & Resources opens again
- **Library ▸ Productivity & Resources (and Tools ▸ Productivity & Resources) showed nothing** — the page, with its productivity rates, crews, man-hours and duration estimate, never appeared. It opens again with all 151 work items. The page was lost from the app window in an earlier update; the calculations themselves were unaffected.

## [v2.9.0] - 2026-09-29

### Changed — Knowledge Base is now Construction Project Knowledge (Project Type Playbooks)
- **Navigator ▸ Library ▸ Knowledge Base (and Tools ▸ Knowledge Base) opens the new Playbooks page**, which replaces the previous Knowledge Base page. There is one playbook for each of **77 project types**, covering the brief and components, MEP systems, the construction sequence by trade (with a Focus filter), a suggested WBS in P6 tree style, and the Basis of Planning.
- **Exports:** the playbook as PDF, the suggested WBS as Excel, and a **baseline XER** per project type (a detailed baseline with 1000+ activities, or a skeleton).
- **Removed:** the previous Knowledge Base page (knowledge projects table, reference-standard tree and example baselines) and the **Constructability** entry in the navigator.

### Fixed — The app opens even with a damaged database
- A corrupt or locked `controlyx.db` no longer stops the app from starting. Saving to the database is switched off for that session; the Knowledge Base and the analysis screens still work.

### Added — Tool-wide enhancement, part 1: one report picker and one-document exports
- **Two-level Report Contents picker.** The print preview now lists each report's sections and, inside them, each table, chart and KPI group. Untick any part and it is left out of the report entirely. Sections can be reordered by dragging, and the choice is remembered per feature.
- **PDF, Word, HTML and Excel from the same preview.** All four are made from the one report you see, so they carry the same sections, tables and numbers. Earned Value and P6 Calendar Audit have all four now; the other features follow in the next parts.
- **Word and Excel always use the standard light style**, whatever Appearance mode is chosen. The screen and the PDF still follow the mode.
- **File ▸ Export to Word / Export to HTML** (Ctrl+Shift+W / Ctrl+Shift+H) open the report preview and save from its export bar.

### Added — Earned Value: engineering log in any format
- **The E1 / E2 engineering log is read by its content, not its exact layout.** Column names, heading rows, two-row headings, discipline sheets, text dates, duplicate "Type" columns and code legends (A/B/C/D/W, Code 1–4, or words) are recognised automatically.
- **"Check how the log was read" panel.** Before counting, the tool shows which column it read as what and how sure it is, plus the review codes it found. You can change any of them, then press **Confirm and count**. A confirmed layout is remembered for the next log of the same kind.
- **Counting rules:** each drawing counts once. Approved at any revision stays approved. Otherwise the latest revision decides, so a drawing rejected and then resubmitted counts as under review and submitted. Approved = A, B, Code 1, Code 2, "approved as noted", "no objection"; Not approved = C, D, Code 3, Code 4, "revise and resubmit", "rejected"; Under review = W, P, pending, or submitted with no reply yet. Statuses such as "Under preparation" or "Not submitted" are not counted as sent.

### Added — Shortcuts, Help and contacts
- **31 keyboard shortcuts** (was 10), including Alt+1…9 to jump to features, **Ctrl+K** to search any feature or command, Ctrl+Shift+W / H / E for Word / HTML / Excel, F1 for Help, and next / previous feature. Shortcuts are shown beside the menu items and in Help.
- **Help ▸ Feature guide: what each feature needs** — the files (how many, XER or XML, baseline or update) and other inputs for every feature, also shown as a "Needs:" hint in the Analysis menu and the navigator.
- **Mostafa Agamy's LinkedIn** in Help ▸ Contact & support and About; links open in your web browser.
- The version shown in Help and About now comes from one place.

### Fixed
- Reporting Studio: the Excel export failed, and File ▸ Export to Excel / Print / Export to HTML went to the wrong place.
- Overview, WBS, Narrative and Productivity PDFs and prints could come out blank.
- File ▸ Print on Schedule (Gantt) now says it has an Excel export only.

## [v2.8.0] - 2026-09-26

### Added — Offline AI Chat: 15 complete answers, read straight from your P6 file
- **15 questions instead of 182.** The question library is regrouped into **15 comprehensive questions** under eight topics: Status & finish, Delay & critical path, Recovery, Schedule quality, Cost & resources, Delivery & construction, Claims & weather, and Reporting. Each one gives a single full answer in the same order every time:
  - the **verdict** first, with status tags;
  - sections with tables, covering the finish chain, key-date slips, client inputs and disciplines;
  - **How this is measured — from your P6**;
  - **What I'd do**;
  - evidence;
  - drill-ins to the related questions.
- **Nothing is lost.** Every one of the original 182 questions is still answered inside its merged question, under **"Your questions, one by one"**. The **Browse all 15 questions** drawer also searches all 182 of them. The job-title filter is gone; the drawer is grouped by topic.
- **Answers read your actual P6 file, not just stored totals.** The chat re-reads the file you sent and names, from your own data:
  - the chain of activities that sets the finish;
  - the head of that chain;
  - the milestone slips;
  - the late client inputs;
  - the deepest float;
  - whether commissioning is programmed at all.
- **Ask in your own words, and follow up.** A typed question goes to the right one of the 15. "Why?", "How do I fix it?" or "More detail" carries on from your last question. If a question isn't understood, the chat offers the closest questions instead of guessing.
- **It shows its working.** Each answer opens with the steps it took on your file (for example "Analysed your file · 5 steps"), then reveals section by section.
- **Every part of an answer agrees with every other part.**
  - When actual cost equals earned value, cost is shown as **not measured**. It is never called "on budget", "holding" or "green".
  - Re-importing the same update doesn't count as a trend or as update history.
  - The delay is always described as P6's own figure: the finish milestone's date against its baseline.
  - Late client inputs are named as employer-side evidence.
  - No answer claims a cause, such as manpower or "execution", that one update can't prove.
- **All offline, no AI model needed.**

### Changed — Offline AI Chat
- **"Which part of the project is causing the delay?"** now names the discipline that moves the finish most, weighing how far behind it is by its share of the job. It no longer names a small line just because its raw gap is biggest, and when the project isn't late it says no part is delaying the finish.
- **"What does this project type usually need?"** reads the project type from your file's WBS and activity names (Knowledge Base best fit) instead of the project name, and checks each item the type usually needs against your file (present / not visible).
- **Manager's briefing:** the finish tile and the trend line keep late and ahead the right way round, and the finish dates are read from the file when an older import has none stored.

### Added — Baseline Narrative Report: conversational guided setup
- **The setup form is replaced by a guided conversation.** The tool reads your P6 file first, pre-fills everything it can detect (tagged "· detected"), then asks one question at a time:
  - location;
  - contract type and revision;
  - parties, logos and layout;
  - milestones and key dates;
  - scope codes;
  - sequence codes.

  It finishes on a single **Generate report** step. The contract value is never asked; the report works it out from the cost loading.
- **Scope and sequence code steps** support **add above / add below**, reorder and remove. **Edit setup** re-opens the conversation at any time. Word, PDF and screen stay identical.
- **The questions appear instantly and the report is built once**, when you press Generate. Detecting your file's values is now about 30× faster.

### Fixed
- **AI Chat answers no longer show "None"** in place of a finish date when an older import carries no stored baseline or forecast finish; the dates are read from the P6 file instead.

## [v2.7.0] - 2026-09-24

### Added — Baseline Narrative Report: Productivity, Volume of Work, and the Critical-Path Appendix
- **Productivity Rates & Resources Assigned (§15).** For every quantity of work in the baseline the report now states the planned **production rate per day** — the total quantity divided by the working days its activities span — the spread of that rate across the individual activities, and the crew (labour and plant) planned to deliver it. A short method note explains exactly how each figure is worked out; a **breakdown by activity** lists every activity behind each quantity (Activity ID · Quantity · Working-days · Rate/day); and a summary table gives the headline rate, range and crew per quantity. Every figure is read from your schedule's own resource loading — where a resource carries no unit of measure the rate columns are left blank with a short explanation instead of an empty figure.
- **Volume of Work (§16).** A single chart shows the planned **value of work month by month** (columns) against the **cumulative planned-value S-curve**, both spread from the baseline cost loading the same way P6's Resource Usage does, with a short summary of the total and the peak month.
- **Appendix — Critical Path.** The report closes with a **"critical-path sweep"**: your schedule's critical activities — taken straight from P6's own total float, with nothing re-scheduled — distilled into the project's zones and swept month by month, coloured by trade, so hundreds of critical activities read as one clear staircase from start to completion instead of an unreadable list.
- **Appendix — Critical Path From P6 & Mapping Sheet.** Two cover pages ready for you to attach P6's own critical-path output and your project mapping sheet.
- Every new section and chart is **native and editable in Word** and matches the on-screen and PDF versions exactly.

## [v2.6.2] - 2026-09-15

### Changed — Excel exports are clearer across the whole tool
- **Every Excel export now opens self-explaining.** A header block at the top of the first sheet names the tool, the feature, your **project**, the **data date**, and when the file was generated — so a workbook you send on stands on its own, without the screen next to it.
- **Titled sections instead of one bare grid.** Each export mirrors the sections you see on screen as its own clearly-titled table, columns are widened to fit their content (no more cut-off text), percentages read as "45.7%", and dates as "09 Feb 2026".
- **Severity is coloured to match the screen** (Critical / High / Medium), with a small legend, wherever a feature shows it.
- **Four exports were rebuilt where they were unclear or incomplete:**
  - **Consultant Review** now exports the whole review — the summary, the driving-logic changes, the duration changes, and the before/after (but-for) impact with the per-milestone comparison and the recommendation — not just the logic table.
  - **Update Analysis** now carries context and full column names with units (it was a bare grid of cryptic numbers), laid out as Time Status, By Activity Code, Driving Path, Activity Counts and Scope Weight.
  - **Constructability** splits its finding types into separate titled sheets with a neutral headline (counts and coverage — no score/verdict), instead of cramming everything into one table.
  - **Critical Path** now uses the same standard workbook as the rest of the tool (Census, Milestones, Driving path, Float migration) with the critical/near-critical rows coloured.
- **Bad Weather export fixes:** columns are sized correctly per table, and dates read as "09 Feb 2026" instead of raw computer dates.
- **Calendar Audit and Bad Weather now open with the same header block** as every other export (tool · feature · project · data date · generated), so those two workbooks match the rest of the tool.

## [v2.6.1] - 2026-09-14

### Fixed
- **Importing a file — or returning to the import screen — now clears every Library page from underneath it.** Previously, importing a P6 file while viewing **Knowledge Base** (or Recent Projects / Productivity & Resources) left that page showing beneath the import/results screen. The import and results screens now always appear on their own, whatever page you were on before.

## [v2.6.0] - 2026-09-13

### Added — Dangling Activities: Resolve & Correct
- **The Dangling Activities check can now fix the logic, not just flag it.** Each dangling finding shows a concrete fix — change a wrong-type link to a real driver (Finish-to-Finish / Start-to-Start → **Finish-to-Start**, or the valid alternative) — with **Apply** (per activity) and **Apply all recommended fixes**, plus a per-finding drawer to pick the link, type, lag and a reason. Where an activity has **no predecessor or no successor at all**, it's marked **Needs Planner Review** — the tool never invents a link.
- **Apply re-checks with the same detection engine** and moves a finding to **Resolved** only when the activity is genuinely no longer dangling. **Download Corrected Schedule** writes the accepted changes into a copy of your file in the **same format (XER / XML)** — actuals, %-complete and dates are never touched; open it in P6 and press **F9**.
- **Contract-milestone guard.** A fix that would push your contractual **completion milestone** past its date is held back with **"Changing this could exceeds the contractual milestone"** — it is not applied and never written to the corrected file. (The tool is offline, so the impact is an estimate from its built-in forward-pass.)
- **The score updates live as you solve.** The Dangling score gauge and KPI tiles, the **Dangling tab** score, and the **Summary** roll-up all rise automatically as findings resolve (a "Preview" note reminds you nothing is written to P6 until you Download), and each Apply shows exactly which relationship was changed and to which type.
- **New "Dangling Type" column** (Dangling Start / Dangling Finish / both) beside each activity in the results.

### Changed
- **The per-user data folder is now `.controlyx`** (Windows `%APPDATA%\.controlyx`, Mac/Linux `~/.controlyx`). Your existing data — recent projects, settings, cached schedules, knowledge base, database — is **migrated automatically on first run** from the previous `Controlyx` folder (and the older `P6EVMTool` / `.p6evmtool` folders), so nothing is lost.

### Fixed
- **The app opens straight into the loading presentation** — no more black/blank screen for a moment on launch. The window background now matches the splash, and the branded loading screen ("Starting local server…") appears the instant the window opens and runs ~11 seconds before revealing the app.
- **Once loading reaches 100%, the app and every feature's results now appear instantly.** The startup splash's slow blurry fade-out is replaced by a quick crisp reveal, and a feature's Run now holds the bar at 100% until its results have actually finished computing, then reveals them immediately — so there's no lag or blank moment after 100%. Applies to every feature (current, in-progress and future) via the shared reveal.

## [v2.5.2] - 2026-09-07

### Changed
- **Every feature now plays the same branded "run" presentation** (the Loading → 100% reveal) when you start it. The multi-file features — **Baseline Revision, Consultant Review, Update vs Update, Critical Path, and Bad Weather** — previously ran without it; they now show the same reveal as every other feature. Built on one shared helper (`revealAndRun`) so it's the default for future features too.

## [v2.5.1] - 2026-09-07

### Changed
- **The WBS report's PDF picker is now fully per-section** — its Report Contents selector (File ▸ Print) offers **WBS overview** and **WBS summary table** as separate, individually-selectable sections (it previously exposed a single combined item).

## [v2.5.0] - 2026-09-07

### Added — Excel export for every feature
- **Every feature now exports its report to Excel (.xlsx)**, matching the on-screen / PDF layout (styled titled-section tables, not a flat data dump). New Excel exports: **Earned Value, Baseline Revision, AI Copilot · TIA, Professional Dashboard, Special Report, Baseline Narrative, Overview, WBS, and Schedule (Gantt)** — joining the ones that already had it (Schedule Health, Out of Sequence, Lag Report, Calendar Audit, Bad Weather, Consultant Review, Update vs Update, Update Analysis, Critical Path, Constructability). Each has an in-panel **Export to Excel** button and works from **File ▸ Export to Excel**; the workbook mirrors that report's sections.
- Built on one shared workbook writer (`write_sections_xlsx`), so Excel export is now the **standard for every future feature** too.

### Changed
- **Baseline Revision** now shows visible **PDF** and **Excel** buttons in its results panel — previously its report was only reachable from the File menu.

## [v2.4.1] - 2026-09-07

### Added
- **Ctrl+B shows / hides the Project Navigator** (the left sidebar) — the same toggle as View ▸ Show / hide navigator and the ☰ button. Listed automatically in Help ▸ Keyboard Shortcuts.

## [v2.4.0] - 2026-09-07

### Added — More keyboard shortcuts
- **Ctrl+E exports the current report to Excel** (alongside Ctrl+P / Ctrl+S for PDF).
- **Ctrl+D now cycles through all six appearance modes** (Light → Dark → Midnight → Sepia → High-contrast → Blueprint, then round again), instead of only toggling light/dark.
- **Ctrl+/ opens the Help Center** (the standard "show shortcuts/help" combo; F1 can't be used because the app window's WebView reserves it as the system Help key).
- The **Help ▸ Keyboard Shortcuts** list is now generated from a single shortcut registry, so it always matches the shortcuts that actually work — add or change a shortcut and it appears in the list automatically, with no separate edit.

### Fixed
- **Keyboard shortcuts now actually fire.** They were doing nothing because the app window could open — or come back from a file dialog — with keyboard focus outside the page, so key presses never reached it. The app now claims keyboard focus on startup, when the splash lifts, and whenever the window is re-focused, and listens for shortcuts at the window level so they work regardless of which part of the screen has focus.
- **The feature-open animation no longer reveals the results before the progress bar reaches 100%.** The loading overlay is now fully opaque, so results stay hidden until the bar completes and then appear instantly.

### Changed
- Help ▸ Contact & Support now states the team responds **within 2 days**.

## [v2.3.0] - 2026-09-07

### Added — Branded startup splash & feature-open reveal
- **A ~13-second Controlyx 2026 startup splash** plays when the app opens: a schedule builds, a glowing critical path rises, and it resolves into the Controlyx 2026 mark and the **"Project Control Intelligence Platform"** wordmark (with a small **"for Primavera P6 · XER & XML"** line) before lifting away to reveal the app. The splash plays in full and never blocks a slow start. This is now a single opening sequence — it replaces the earlier separate logo splash.
- **Opening a feature plays a short branded reveal** — pressing **Run** plays a brief animation (an accent scan sweeping the schedule and critical path, with the feature's name and a progress bar); the results appear the **instant the bar reaches 100%**, with no wait afterwards.
- Both respect the system "reduce motion" accessibility setting.

### Added — In-app Help Center
- The **Help** menu opens a Help Center with **Getting Started** (how the tool works), a **Feature Guide** that lists every feature and the inputs it needs (with live search), **Keyboard Shortcuts**, **What's New**, **Contact & Support**, and **About**. Contact & Support carries the developer's contact details and the technical-support contact; About credits the tool's developer. It follows the active appearance mode.

### Added — Change the imported file
- Imported the wrong file? A **"Change file"** button on the file bar lets you pick a different P6 XER/XML and swap it in place — no need to start over.

### Changed — Menus & navigation
- The **Analysis** menu is now a grouped, cascading **"Choose a module"** that mirrors the Project Navigator — each group (Project Overview, Schedule Quality, Progress & Performance, Compare & Claims, Calendars & Weather, Reports & Dashboards) fans out to its features, so you can open any module straight from the menu bar.
- The **Project Navigator now starts hidden** on launch for a cleaner first view; the ☰ button shows or hides it, and its scrollbar now matches the dark sidebar.
- The import prompt now reads **"Pick a P6 file (XER or XML)"**.

### Added — Schedule-health status light
- The three unlabelled colour dots at the top-right of the menu bar are now a **schedule-health status light**. Before you import anything it sits quietly as a grey **"No schedule"**; once a schedule is loaded it lights up as **On Track** (green), **At Risk** (amber), or **Behind** (red), read from the schedule's SPI — SPI ≥ 1.00 is On Track, 0.85–0.99 is At Risk, below 0.85 is Behind — and it never shows green while the forecast finish is late (a positive delay forces at least At Risk). Hovering shows the actual SPI and how many days ahead/behind. The colours follow the active appearance mode.

### Changed — App window & import copy
- **The app now opens maximised** instead of the small default window.
- The import screen's sub-line now spells out the order: *"Nothing is analysed until you import a Primavera P6 file, then pick a module and run it."*

### Fixed
- **Keyboard shortcuts now work** — Ctrl+O (import), Ctrl+Enter (Run), Ctrl+P / Ctrl+S (export PDF), Ctrl+F (feature guide), Esc (close menus).
- **Back to the import screen shows only the import screen** — the Recent Projects and Knowledge Base pages no longer trail beneath it.
- The startup splash now **plays in full** — the Skip option was removed so the opening presentation always shows.

## [v2.2.0] - 2026-09-06

### Changed — Explicit "choose a feature → Run" workflow
- **Importing a schedule no longer runs or shows any analysis.** After import you get a clear **"Choose a feature to analyze"** prompt with the workflow spelled out (Import → Choose feature → Run → Results). You pick a feature from the Project Navigator and the feature screen shows exactly the inputs it needs **inline** — there is no separate "inputs" step — and only when you press **Run** does that one feature compute. Nothing runs automatically after import, and there is no "Run All".
- **Every feature states its required inputs up front** — a single schedule, or a second file where the analysis needs one (Consultant Review → a baseline; Baseline Revision → Rev.00 + Rev.01; Update vs Update → a previous update; Critical Path → baseline / previous; Bad Weather → a location). **Consultant Review** and **Update vs Update** no longer start the instant you pick a file — you assign the file, then press **Run**.
- **Change inputs** — the feature screen shows a secondary **Change inputs** button beside Run, to reassign the schedule/file without restarting the workflow.
- Re-opening a feature you have already run this session jumps straight back to its results.

### Changed — Project Navigator reorganised by planning workflow
- The left **Project Navigator** is regrouped around how a planner works — **set up → validate → track → compare → report** — instead of the old generic Project / Analysis / Reports buckets:
  - **Project Overview** — Overview · WBS · Schedule (Gantt)
  - **Schedule Quality** — Schedule Health · Baseline Narrative · Lag Report
  - **Progress & Performance** — Earned Value · Out of Sequence · Update Analysis · Critical Path
  - **Compare & Claims** — Update vs Update · Consultant Review · Baseline Revision · AI Copilot · TIA
  - **Calendars & Weather** — P6 Calendar Audit · Bad Weather
  - **Reports & Dashboards** — Professional Dashboard · Special Report
  - **Library** — Knowledge Base · Constructability · Recent Projects
- **No duplicated access points** — every feature appears in exactly one place. Constructability sits under Knowledge Base (it reviews the schedule against that knowledge base). The **Weather → Forecast** entry was removed from the navigator.

### Added — Schedule (Gantt) view
- The **Schedule (Gantt)** view is now reachable from the Project Navigator — a time-scaled bar chart of the activities grouped by WBS, with % complete, critical-path highlighting, month gridlines and a data-date line. (The view existed but had no way in.)

### Fixed — Scrolling, and a functional cleanup of the on-screen controls
- **The main workspace scrolls again.** Reports, tables and results that run past the bottom of the window can now be scrolled — consistently across every feature.
- **Removed dead and misleading controls** after a full audit of every button, menu item and control: retired `Tools ▸ Settings` and the redundant `Project` menu (their actions live elsewhere), made `File ▸ Exit` actually close the app, renamed the mislabelled `File ▸ Load another file` to the honest **"Back to import screen"**, and dropped a decorative profile avatar and other non-working affordances. Removed a large block of unreachable dead code behind the scenes.
- **Two real bugs fixed** — clicking a bar on the P6 Calendar Audit comparison chart no longer produces a stray empty legend, and the AI Copilot note now points to the correct place to add your Anthropic API key.

## [v2.1.0] - 2026-09-04

### Added — Baseline Revision Comparison (Rev.00 vs Rev.01)
- **New "Baseline Revision Comparison" analysis** — compare two approved baseline revisions (e.g. Baseline Rev.00 vs Rev.01) from a planning/consultant perspective and see what changed and whether it materially affected the planned execution strategy, logic, sequence, critical path, milestones, scope or duration. It is an analytical review, **not** a raw file diff, and stays neutral and evidence-based: every finding reads **Change detected → Potential impact → Planning review**, never an automatic "wrong/bad" verdict.
- **Explicit workflow** — Select feature → **assign both revisions** (Rev.00 Original, Rev.01 Revised) → **Run Comparison** → review results. Nothing is analysed until Run is pressed; assigning a file never triggers the comparison on its own. Uses the global File ▸ Print / Export to PDF — no duplicate import/export/print buttons inside the feature.
- **Activity matching beyond the Activity ID** — activities are reconciled on the evidence (name, WBS, activity codes, dates, duration, surrounding logic), so an activity that kept its work but changed ID reads as an **identity change**, not a false "removed + added".
- **Results** — an Executive Summary (KPIs, change profile by planning category, ranked material findings), a **Critical Path & Sequence** view (Rev.00 vs Rev.01 driving chains with activities entering/leaving the critical path, logic-based **sequence-change detection**, and float/criticality movement), a **Scope & Structure** view (**WBS** branches added/removed/renamed and activities moved, **calendar** reassignments and workweek/holiday changes, and primary **constraint** changes), a **Milestone Comparison** (delayed/advanced/new/removed), and a filterable **Change Register** whose rows expand to a full Rev.00 ⇄ Rev.01 side-by-side plus a four-part planning analysis (Change detected · Why it matters · Potential impact · Planning review). Severity reflects **schedule impact** (material vs minor), never a judgement that a change is wrong.
- **WBS / calendar / constraint comparison** — WBS structure diff (added/removed/renamed branches, work packages, activities moved between WBS), calendar comparison (per-activity reassignments grouped e.g. "N activities moved 6-day → 7-day", plus calendar-level workweek/holiday/hours changes), and primary-constraint comparison (added/removed/type/date, hard constraints flagged) — all classified into the change profile and register.
- **Resource & cost comparison** (conditional on the export carrying it) — total budget change, per-activity budget-cost changes, and resource-assignment changes (resources added/removed, budgeted units and rate changes). Presented as **informational** — a cost or resource change is never counted as a material schedule impact. Backed by a small **additive** parser extension (new `ScheduleData.resources` / `assignments_by_activity`, populated from P6-XML `ResourceAssignment` and XER `TASKRSRC`/`RSRC`); the existing per-activity cost sums (`bac_by_activity` / `ac_by_activity`) and all EVM math are unchanged.
- **Consultant-grade report** — Executive Summary, Revision Overview, Milestone Comparison, Critical Path Comparison, Major Sequence Changes, Major Logic Changes, WBS/Calendar/Constraint Changes, Resource & Cost Comparison and the Change Register assemble into one professional PDF, rendered through the shared report framework so all six appearance modes and the on-screen preview match the printed output.
- Isolated `p6_revcompare/` package built on the existing diff (`p6_compare`) and critical-path (`p6_critpath`) primitives with a new neutral, progress-free interpretation layer; new `/api/revcompare` and `/api/revcompare/report` routes. The only `p6_evm` change is the additive resource/assignment capture above; EVM and metrics are untouched. _Two minor P6-XML data gaps remain (they only limit specific sub-cases, and primary constraints / total float are covered): free float is often absent from XML exports (present in XER), and secondary constraints are not parsed._

## [v2.0.0] - 2026-09-01
### Changed — Rebranded to **Controlyx** (edition **2026**)
- The product is now **Controlyx**, shown as **Controlyx 2026**. Rebranded across the window title, in-app header and HTML title, the CLI banner, the README/CLAUDE docs, the built executable (**`Controlyx.exe`**), the PyInstaller spec (**`controlyx.spec`**), and the GitHub Actions build artifact + release asset.
- **Existing installs keep their data.** The per-user data folder (`%APPDATA%\P6EVMTool` → `%APPDATA%\Controlyx`) and the database (`p6evm.db` → `controlyx.db`) are renamed and **migrated automatically on first run**; if the rename can't complete it safely falls back to the old location so nothing is lost.
- **Intentionally unchanged** (renaming these would break imports or discard user settings — technical identifiers, not branding): the `p6_evm` Python package and the UI `localStorage` keys (`p6_evm_theme`, `p6evm_w_*`, `p6evm_ac_*`). The user-facing name now lives in one place — `APP_NAME` / `APP_EDITION` / `APP_TITLE` in `utils.py`.

### Added — Brand identity (app icon, logo lockup, in-app splash)
- **App icon** — a project-control-intelligence mark (amber "C" ring + EVM S-curve + intelligence spark), embedded into `Controlyx.exe`.
- **Logo lockup** in PNG **and** SVG (light / dark / stacked) pairing the mark with the **"Project Control Intelligence Platform"** tagline — used in the README header and an in-app launch splash, and available for report/doc headers.
- **In-app launch splash** (fades out, reduced-motion aware) and a rebranded sidebar mark.

### Added — Special Report (compose your own cross-feature report)
- **New "Special Report" analysis** — build your own report by picking the exact **detailed results** you want from any feature: each figure on its own (Planned %, Actual %, SPI, the category table, audit scores & findings, "Planned vs Actual activities", …) **plus each feature's own full report sections with their real tables and charts**. Order and number them, name the report, and export to **Word or PDF that look identical** — in all **six appearance modes**. Prints as a proper document: cover page → table of contents → numbered sections.
- **It runs the features for you** — single-file results come straight from the imported schedule; results that need a second file (Critical Path / Consultant Review → a **baseline XER**; Update-vs-Update → a **previous update**) highlight what's missing with an **Attach** button, then compute on the spot — you never open the feature's own tab.
- **Saved report templates** per project (re-run the same report next week on the new update), and **new features appear in the list automatically** (auto-discovery registry, like the Professional Dashboard).
- Isolated `p6_special/` package + `/api/special/*` routes; **EVM untouched**. Word matches the PDF because both render one HTML with every colour resolved to concrete hex.

### Added — Schedule Health Review (score a baseline's logic health)
- **New "Schedule Health Review" analysis** — scores a **baseline's** logic health against the **DCMA 14-point** checks as weighted sub-features — **Milestones & Constraints · Critical Path / CPLI · Float · Dangling · Whole-day durations · Leads & Negative Float · Open Ends · Relationship Types · High Duration** (circular logic is a pass/fail gate) — rolled into one weighted **Schedule Health %**.
- **Summary dashboard** — an overall health gauge with a plain-language verdict, a **Pass / Review / Critical** split, each check's score × weight worst-first, where the problems concentrate, and a **"fix these first"** list; plus a **detail view per check** (including the CPLI driving-path timeline).
- PDF export with the Report Contents selector. Scoring layer on top of the existing audit; EVM untouched.

### Added — Report Appearance Modes (six looks, screen + every report)
- **Six appearance looks** — **Light** (default), **Dark**, **Midnight**, **Sepia**, **High-contrast** and **Blueprint** — chosen from one **Appearance** control in the toolbar. Your choice themes the **whole app screen and every report preview, PDF and Word export**, and is remembered. It changes only the look — never a number, date or word.
- Built as one shared colour layer, so **every current report and every future feature gets all six looks for free** (the Critical Path Analyzer PDF and the Constructability print-preview included).

### Added — Report Contents selector (Preview = PDF = Print, everywhere)
- **Every report's Print Preview now lets you choose exactly what goes in it** — tick/untick individual tables and charts, reorder them, Select / Clear All, and it remembers your choice per report. **What you see in the preview is exactly what prints and what the PDF contains** (Preview = PDF = Print), from one shared framework used across all modules.

### Changed — Recent Projects moved to its own page
- The **Recent Projects** list is now its **own left-sidebar page** (like the Knowledge Base and Construction Database) instead of trailing the bottom of the Home reports — so it never appears under a module's report again. Same list, just relocated; open a project to jump straight to its results.

## [v1.3.0] - 2026-08-23
### Added — Critical Path Analyzer (new module)
- **New "Critical Path Analyzer" sidebar section** — compares the critical path across **2–3 schedules** (two updates · update-vs-baseline · both + baseline; you can swap any of the three, including the current update). It answers *how the critical path moved and what it does to completion*.
- **Execution dashboard** — a Critical Path Health verdict with a **CPLI** gauge (and the formula spelled out), KPI tiles (CPLI · path length · % critical · near-critical, each Current vs Previous with the variance), and three charts (critical/near by schedule · CPLI trend · milestone slip vs baseline).
- **Driving path, schedule by schedule** — the governing (and every) finish milestone's driving path drawn as **WBS work-front boxes** (Planned % · Actual % · baseline finish · expected finish · slip / total float, titled by the work-front WBS with its full ancestry `@Phase C @Silos Civil Works`), with the **new critical path highlighted** — NEW ON PATH (the reroute) · LEFT PATH · stayed · complete.
- **Critical & near-critical census** (count + % per schedule, with the plain-difference variance to one decimal), **every-milestone finish comparison**, **float migration**, and an auto **recommendation**.
- **PDF + Excel** export with the Report Contents selector and a milestone-path picker. New `p6_critpath/`; **EVM untouched**. Critical = TF ≤ 0; near-critical = 0 < TF < 10 wd; critical path length = remaining working days (data date → expected finish); CPLI = (remaining length + total float) ÷ remaining length.

### Added — Update Analysis (one update vs its baseline)
- **New "Update Analysis" sidebar section** — a single-file read of one update against the baseline embedded in it: a **Time Status** donut, **Planned vs Actual by activity code**, the governing milestone's **driving path** as WBS work-front boxes, **activity counts** (planned vs actual) and **scope weight**. House-style landscape PDF + Excel with the Report Contents selector. New `p6_update/`; EVM untouched.

### Added — Lag Report
- **New standalone Lag Report** — a register of every relationship lag/lead in the schedule, with a justification column and PDF/Excel export.

### Changed — Consultant Review refinements
- The Consultant Review (baseline-vs-update forensic delay) gained table refinements, dashboard charts, a manager-oriented PDF, **date-based and instant (no-F9) but-for delay**, and an S-curve.

### Changed — Executive-read dates
- Report dates now render in the executive-friendly **`09-Feb.2027`** format.

### Added — Construction Database (downloadable schedules + contribute-to-learn)
- **New "Construction Database" sidebar section** — a local library of P6 schedules grouped by project type (EPS tree). For every type you can **download a ready-made baseline**: a **clean** reference (scores ~100) or one carrying **typical gaps** (a few illogical links + missing activities) so you can import it, open the Constructability review and watch it flag them. Generated as P6 XML — import & F9.
- **Add your own schedules** — a **➕ Add to Database** button on the Constructability review files your imported schedule under its detected type; it joins that type's library *and* feeds the "Learned from your projects" engine, so the tool's knowledge grows from your real projects. **Local & private** — nothing leaves the PC. A shared cross-company database remains a future edition.
- Isolated `p6_kb/database.py` + `p6_kb/examples.py`; `GET /api/database`, `POST /api/database/{add,example,download}`; EVM/audit untouched.

### Added — Construction Knowledge Base greatly expanded (now covers most project types)
- The Constructability Knowledge Base now ships **88 project sub-types** across Buildings, Infrastructure, Industrial, Energy and Landscape — every one **selectable in the sub-type picker** and reviewable **offline at no cost**. All are **starter drafts** for a planning engineer to curate.
- **New factory types:** MDF / wood panel, reinforcement (rebar), precast concrete, ready-mix batching plant, asphalt / hot-mix, ceramic & tile, brick & block, gypsum board, pipe (steel & HDPE), cable & wire, textile, plastics / injection-moulding, paint & coatings, sugar, tyre & rubber, battery / gigafactory, furniture — joining the existing glass, cement, steel, aluminium, automotive, food & beverage, pharmaceutical, pulp & paper, fertilizer and semiconductor plants.
- **New electrical substation types:** AIS (air-insulated), GIS (gas-insulated), HVDC converter station, traction / railway, MV distribution and mobile / packaged (e-house) — alongside the general power substation.
- **Other new types:** prison / correctional, laboratory / R&D, convention & exhibition centre (Buildings); road / highway tunnel, district cooling, telecommunications / fibre network (Infrastructure); concentrated solar power (CSP) and EV-charging infrastructure (Energy).
- Engine, UI and server unchanged — the Knowledge Base is glob-loaded data, so new types are picked up automatically and bundled into the `.exe`.

### Added — Knowledge Base library (browse the standards as a P6-style EPS)
- **New "Knowledge Base" sidebar section** — browse all project-type standards as an **EPS tree** (category folders → project types). Each type opens to its reference **baseline** standard: detection keywords, standard WBS, key/often-missing activities (with typical predecessor→successor, durations and the *why*), construction logic rules, milestones and common issues. Offline, no schedule needed.
- **Review a schedule against a type** — one click runs the Constructability review for that exact type on the currently-open schedule.
- **Export as a P6 starter baseline** — turn a standard into a **P6 XML schedule skeleton** (WBS + activities + durations + Finish-to-Start logic, sequenced to satisfy the standard's own rules) that you import into Primavera P6 as a new project and F9. Validated by round-tripping through the tool's own parser.

### Added — Constructability Review: Execution-Readiness Dashboard + PDF/Excel
- **Execution-Readiness dashboard** at the top of the review: a plain-language **readiness verdict**, the score as a **gauge with the four-band legend** (Ready 85+ · Minor 70–84 · Significant 50–69 · Major 0–49) and a marker at the score, **readiness-by-dimension** bars (logic / completeness / structure), **KPI tiles** (illogical %, missing %, missing WBS, critical-path, scope coverage), an **issues-by-WBS-phase** breakdown, a **severity split**, and **ranked priority fixes** ("tackle these first").
- **Smart touches:** a **detection-confidence** indicator (how strongly the schedule matched the type, honest about the draft KB), and a **"what-if" projected score** — how high the schedule would score once the flagged logic is corrected.
- **Export to PDF and Excel** — the whole review (dashboard + illogical / missing / WBS tables) as a print-ready PDF, and every finding flattened into one filterable Excel sheet.
- **Knowledge Base +2 industrial standards** — *Local Fabrication & Equipment Installation* (new: fab yard → material receipt → steel/spool fabrication → coating → equipment erection & alignment → piping/E&I hook-up → pre-commissioning), and *Steel Structures* strengthened with the erection works (base-plate grouting, primary/secondary erection, decking). KB now **89 types**.

### Added — Learns from your own projects (private, offline)
- **The tool now quietly learns from every schedule you import** — per project type it accumulates which activities and WBS branches recur across *your own* imports, and their typical durations. Fully **local and private**: nothing leaves your PC, deduped by file so re-imports never inflate it, and always marked **"learned"** and kept separate from the curated standards.
- **"Learned from your projects" panel** in the Constructability review — the activities that commonly recur in your schedules of that type, each with how often (e.g. 6 of 7 imports), average duration, and whether it's in the current schedule (missing ones flagged *"consider adding"*), plus the WBS branches your projects usually have.
- **Learned types in the Knowledge Base library** — a *"Learned from your projects"* group at the top of the EPS tree; open a learned type to read what the tool learned and **export** it as a P6 starter baseline or **download** it as a standard file.
- Three clearly-badged knowledge sources — **Curated** (built-in), **Learned** (your imports, this PC), and **Shared** (anonymised, pooled across users — a future version).
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
