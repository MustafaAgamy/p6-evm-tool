// ── In-app Help manual — CONTENT ONLY (no DOM, no logic) ───────────────────
// One entry per feature. To update a feature's page when it changes, edit ONLY
// that topic object below — nothing else in the app moves. Rendering lives in
// help.js; this file is pure data so it stays safe to edit.
//
// Topic fields (all except id/title/whatFor optional):
//   id        unique slug (also the search key)
//   title     page heading
//   whatFor   one or two plain lines — "What it's for"
//   steps     [string]  numbered "How to use it" steps  (**bold**, `code` allowed)
//   howLabel  heading for the mechanics block (default "How it works")
//   how       [ {p:"..."} | {formula:"...", note:"..."} ]  the mechanics
//   reading   {good:"...", bad:"..."}   how to read a good vs worrying result
//   terms     [ {term, def} ]           definition list (Glossary)
//   where     string    "Where this lives in the app"
//
// The product name is rendered from `appName` only — never hard-code it in text.

export const MANUAL = {
  version: '1.0',
  appName: 'nPace',
  groups: [
    {
      group: 'Getting started',
      topics: [
        {
          id: 'what-this-is',
          title: 'What this app is',
          whatFor: 'It reads a Primavera P6 schedule export and turns it into the two things a planner needs each week: EVM results (how far ahead or behind the project is, in money and %) and a Schedule Audit (whether the schedule’s logic, float and sequence are healthy). It shows the numbers on screen and as a one-page PDF, and remembers past imports.',
          how: [
            { p: 'It never edits your P6 schedule. It only reads the file you export. Because P6’s XML does not store Planned Value or Earned Value directly, the app re-derives the planned/earned side from the schedule — everything is read-only.' },
          ],
          where: 'The Home screen — the first thing you see when the app opens.',
        },
        {
          id: 'weekly-workflow',
          title: 'The weekly workflow',
          whatFor: 'The normal cycle for each schedule update.',
          steps: [
            'Export your updated schedule from P6 as an XML (or XER) file.',
            'Open the app and import it — **Browse File** or drag-and-drop.',
            'Choose **EVM Results** or **Schedule Audit**.',
            'Read the numbers; adjust weights or attach a baseline if needed.',
            'Generate the PDF to submit.',
          ],
          how: [
            { p: 'Every import is saved, so next week you can re-open the project instantly from Recent Projects without re-importing. Excel import is planned but not yet available (its card reads “Coming soon”).' },
          ],
          where: 'The whole app — Home first, then the analysis you pick.',
        },
      ],
    },
    {
      group: 'Importing a schedule',
      topics: [
        {
          id: 'import-xml',
          title: 'Import XML',
          whatFor: 'Bring a P6 schedule in from a P6 XML export — the primary and most accurate format.',
          steps: [
            'On Home, click **Browse File** under Import XML.',
            'Pick your `.xml` file exported from P6.',
            'Wait for parsing — the results section appears with the file name, data date, and activity/calendar counts.',
          ],
          how: [
            { p: 'XML is the richest format: it carries the embedded baseline (dates and budget), the intraday working-time calendars, and activity codes. Because the baseline is embedded, Planned Value, SPI and Delay are exact from XML with no extra steps.' },
          ],
          where: 'Home → Import Schedule → the Import XML card.',
        },
        {
          id: 'import-xer',
          title: 'Import XER',
          whatFor: 'Bring a schedule in from a P6 XER export when XML is not available.',
          steps: [
            'On Home, click **Browse File** under Import XER.',
            'Pick your `.xer` file.',
            'The results appear the same way as XML.',
          ],
          how: [
            { p: 'A XER **update** does not embed its baseline, so Planned Value, SPI and Delay are approximate until you attach the baseline (see Attaching a baseline). The dashboard marks these figures “approx” and shows a yellow banner, so the gap is never hidden.' },
            { p: 'XER working-time is read from its calendar data so working days match XML; intraday hours are still being aligned, so a XER can read very slightly differently from the same XML.' },
          ],
          reading: {
            good: 'For a XER update, attach the baseline — then PV, SPI and Delay become exact.',
            bad: 'A XER with no baseline attached — treat PV, SPI and Delay as approximate.',
          },
          where: 'Home → Import Schedule → the Import XER card.',
        },
        {
          id: 'drag-drop',
          title: 'Drag and drop',
          whatFor: 'A faster way to import — drop the file straight onto the window.',
          steps: [
            'Drag a `.xml` or `.xer` file from your file explorer.',
            'Drop it anywhere on the app window.',
            'It imports exactly as if you had used Browse.',
          ],
          how: [
            { p: 'Only `.xml` and `.xer` files are accepted; anything else shows a short error and nothing is imported.' },
          ],
          where: 'Home — the dashed drag-and-drop strip (dropping works anywhere on the window).',
        },
      ],
    },
    {
      group: 'Choosing what to view',
      topics: [
        {
          id: 'choose-analysis',
          title: 'EVM Results, Schedule Audit and Calendar Audit',
          whatFor: 'After an import, the app asks which analysis you want — three separate views, kept independent on purpose.',
          steps: [
            'Import a schedule.',
            'On the “Choose what to view” cards, click **EVM Results**, **Schedule Audit**, or **Calendar Audit**.',
            'Switch anytime with the tabs, or **⟲ Change** to go back to the choice.',
          ],
          how: [
            { p: '**EVM Results** answers “how far ahead or behind, and how much earned?”. **Schedule Audit** answers “is the schedule’s logic and float well built?”. **Calendar Audit** answers “are the working calendars, holidays and shutdowns sound?”. They never mix — each is its own report.' },
          ],
          where: 'Shown right after import; also the tabs above the results. The shield icon in the sidebar jumps to the Schedule Audit view.',
        },
      ],
    },
    {
      group: 'EVM Results',
      topics: [
        {
          id: 'planned-value',
          title: 'Planned Value (PV)',
          whatFor: 'The budgeted cost of the work that *should* have been done by the data date — “how much were we supposed to have finished by today?”.',
          steps: [
            'Open EVM Results.',
            'Read the **Planned Value** tile in the Executive Dashboard.',
          ],
          howLabel: 'How the number is calculated',
          how: [
            { formula: 'PV = Σ (activity baseline budget × activity planned %)', note: 'Planned % is the working time from baseline start to the data date ÷ the activity’s full baseline duration — measured in the calendar’s intraday work HOURS (P6’s method), capped 0–100%.' },
            { p: 'The budget used is the **baseline** budget from the P6 file, not the current update’s cost loading — this is what makes PV match P6 to the unit. If a schedule carries no embedded baseline (a bare XER), it falls back to the current cost and PV becomes approximate.' },
          ],
          reading: {
            good: 'From XML (baseline embedded), PV matches P6 exactly.',
            bad: 'From a XER with no baseline attached, PV is approximate — attach the baseline.',
          },
          where: 'EVM Results → Executive Dashboard → the Planned Value tile; also on the EVM PDF.',
        },
        {
          id: 'earned-value',
          title: 'Earned Value (EV)',
          whatFor: 'The budgeted cost of the work that has *actually been completed* by the data date — “how much of the budget have we genuinely earned?”.',
          steps: [
            'Open EVM Results.',
            'Read the **Earned Value** tile.',
          ],
          howLabel: 'How the number is calculated',
          how: [
            { formula: 'EV = Σ (activity baseline budget × activity actual %)', note: 'Actual % is the physical % complete entered in P6. A category can be overridden — e.g. design measured by drawing count — see Engineering progress.' },
          ],
          where: 'EVM Results → Executive Dashboard → the Earned Value tile.',
        },
        {
          id: 'actual-cost',
          title: 'Actual Cost (AC)',
          whatFor: 'The real money spent to date. It feeds CPI.',
          steps: [
            'Open EVM Results and read the **Actual Cost** tile.',
            'If P6 auto-computes actuals (AC equals EV), enter the real finance actual in **✎ Project Setup** so CPI becomes meaningful.',
          ],
          how: [
            { p: 'AC defaults to P6’s value. When P6 is set to auto-compute actuals, its Actual Cost equals Earned Value — which would make CPI always 1.00 — so the app lets you type the real finance actual instead. The entered value is saved per project.' },
          ],
          where: 'EVM Results → the Actual Cost tile; edited in ✎ Project Setup.',
        },
        {
          id: 'spi',
          title: 'SPI — Schedule Performance Index',
          whatFor: 'In one number, whether the project is ahead of or behind plan by the data date. Usually the first figure people look at.',
          steps: [
            'Open EVM Results.',
            'Read the **SPI · Schedule** tile (top-left of the dashboard).',
          ],
          howLabel: 'How the number is calculated',
          how: [
            { formula: 'SPI = Earned Value (EV) ÷ Planned Value (PV)', note: '1.00 = exactly on plan; below 1.00 = behind (0.90 ≈ 10% behind); above 1.00 = ahead. If PV = 0 (nothing due yet), SPI shows “—”.' },
            { p: 'On the dashboard SPI is derived from the Overall Actual % ÷ Overall Planned % of the (editable) Category Weights table, so it updates live when you change weights or upload an engineering log. It is weight/cost-based and is never affected by the Schedule Audit.' },
          ],
          reading: {
            good: 'SPI ≥ 0.95 — keeping pace with, or ahead of, plan.',
            bad: 'SPI < 0.90 — meaningfully behind; check the PV–EV Gap to see which discipline is dragging.',
          },
          where: 'EVM Results → Executive Dashboard → the SPI tile; also on the EVM PDF header.',
        },
        {
          id: 'cpi',
          title: 'CPI — Cost Performance Index',
          whatFor: 'Whether the project is spending in line with what it has earned.',
          steps: [
            'Open EVM Results and read the **CPI · Cost** tile.',
            'Make sure Actual Cost is a real finance figure (Project Setup), or CPI is not meaningful.',
          ],
          howLabel: 'How the number is calculated',
          how: [
            { formula: 'CPI = Earned Value (EV) ÷ Actual Cost (AC)', note: '1.00 = on budget; below 1.00 = over budget; above 1.00 = under budget. If AC = 0, CPI shows “—”.' },
            { p: 'CPI recomputes live from whatever Actual Cost is in effect — P6’s value or the one you entered.' },
          ],
          reading: {
            good: 'CPI ≥ 1.00 — earning at least as much budget as spent.',
            bad: 'CPI < 1.00 — spending faster than earning; over budget.',
          },
          where: 'EVM Results → the CPI tile.',
        },
        {
          id: 'finish-delay',
          title: 'Finish Delay',
          whatFor: 'How many working days the project’s finish has slipped versus the baseline.',
          steps: [
            'Open EVM Results.',
            'Read the **Delay** tile (red = late, green = early), next to Baseline Finish and Expected Finish.',
          ],
          howLabel: 'How the number is calculated',
          how: [
            { formula: 'Delay = forecast finish − baseline finish, counted in working days', note: 'Working days use the project’s P6 calendar (weekends and holidays excluded). Positive = behind, negative = ahead, zero = on time.' },
            { p: 'The finish point is the schedule’s finish milestone (the activity with no successor, or the one marked as project finish). If there is no finish milestone or no baseline, Delay shows “—”.' },
          ],
          reading: {
            good: '0 or negative — on time or ahead.',
            bad: 'A positive number — behind; from a XER without a baseline this is approximate.',
          },
          where: 'EVM Results → the Delay tile.',
        },
        {
          id: 'category-weights',
          title: 'Category weights and progress',
          whatFor: 'Breaks the project into WBS categories (Construction, Engineering, Design, Procurement…) and rolls their progress into the overall %, weighted by each category’s share of the project.',
          steps: [
            'Open EVM Results and read the **Category Weights & Overall Progress** table — each category’s weight, planned %, actual %, and weighted contribution.',
            'To change a weight or the Actual Cost, click **✎ Project Setup**, edit, and **Apply** — the table, slicer and dashboard recompute live. Weights are saved per project.',
            'Use the chips above **Project Progress** to focus one discipline, or Overall to roll them all up.',
          ],
          how: [
            { p: 'Categories are detected automatically from the WBS by construction meaning, so any project works with no configuration. Each category’s progress is its activities weighted by baseline budget; the overall is the categories weighted by their weight.' },
            { formula: 'Overall Actual % = Σ (weight × category actual %) ÷ Σ weight', note: 'On import every phase gets a sensible default weight: cost-loaded phases share 95% by their cost; the non-cost disciplines share 5% evenly; Milestones / Key Dates / summary rows stay at 0% so they never dilute the project %.' },
          ],
          where: 'EVM Results → the Category Weights table and the ✎ Project Setup dialog.',
        },
        {
          id: 'baseline-attach',
          title: 'Attaching a baseline (for XER)',
          whatFor: 'A XER update does not include its baseline, so its Planned Value, SPI and Delay are approximate. Attaching the baseline makes them exact.',
          steps: [
            'Import a XER update and open EVM Results.',
            'In the yellow baseline banner at the top, click **📎 Attach baseline XER**.',
            'Pick the baseline schedule file.',
            'The banner turns green (with an X/Y matched count) and PV, SPI and Delay recompute against the baseline dates and budget.',
          ],
          how: [
            { p: 'The baseline is matched to the update by Activity ID; its dates and budget replace the update’s for the planned side only — actual progress is untouched. The attached baseline is remembered per project, so re-opening keeps it. XML imports need no baseline; it is already embedded.' },
          ],
          reading: {
            good: 'Green banner “Baseline attached” — PV/SPI/Delay now match P6.',
            bad: 'Yellow banner “No baseline attached” on a XER — the figures are approximate.',
          },
          where: 'EVM Results → the banner at the very top of the panel.',
        },
        {
          id: 'engineering-progress',
          title: 'Engineering progress (drawings)',
          whatFor: 'Tracks design and shop-drawing progress (submitted / approved) and can drive the Design and Engineering categories’ actual %, so engineering reflects real submittals rather than schedule dates.',
          steps: [
            'Open EVM Results and find the **Engineering Progress** section.',
            'To use your drawing log, click **⬆ Upload Log(s)** and pick one or more Excel logs (a Design log, a Shop log, or a combined E1 log).',
            'The table fills with Req / Submitted / Approved per trade and type, plus overall Design and Engineering rows and gap tables.',
          ],
          how: [
            { p: 'Two sources. **From the drawing log (preferred):** each drawing is counted once (by title); a drawing is Approved if any revision took action code A or B. Design drawings (non-Shop) drive the Design category’s actual %, Shop drawings drive Engineering — then the category table, slicer and dashboard recompute. **From P6 (fallback):** with no log uploaded, submittal/approval activities that have *started* are counted from the schedule.' },
            { formula: '% Approved = approved drawings ÷ required drawings', note: 'Counting each drawing once keeps every % ≤ 100% even after a variation forces a re-submittal.' },
          ],
          where: 'EVM Results → the Engineering Progress section; the ⬆ Upload Log(s) button.',
        },
        {
          id: 'pv-ev-gap',
          title: 'PV–EV Gap analysis',
          whatFor: 'Shows where the behind-plan work is concentrated — which activity-code group (Type of Works, Area, …) carries the biggest gap between Planned and Earned Value.',
          steps: [
            'Open EVM Results and scroll to **PV vs EV Gap Analysis**.',
            'Pick a grouping in the **Group by** dropdown (any activity code from the schedule).',
            'Read the bars — each group’s gap and its share of the total gap.',
          ],
          howLabel: 'How the number is calculated',
          how: [
            { formula: 'Gap = PV − EV per group;  % of Gap = |group gap| ÷ Σ|gaps|', note: 'PV and EV per activity use the baseline budget × planned/actual %. Activities with no value for the chosen code are excluded. A pure baseline shows almost no gap (PV ≈ EV).' },
            { p: '“Ahead X” means that group has earned more than planned (a negative gap). Activity codes are read from both XML and XER.' },
          ],
          where: 'EVM Results → PV vs EV Gap Analysis; the Group-by dropdown at the top of that section.',
        },
        {
          id: 'evm-pdf',
          title: 'The EVM PDF report',
          whatFor: 'Produces the one-page consultant EVM report to submit, using your current weights, Actual Cost and engineering log.',
          steps: [
            'Open EVM Results and set weights / Actual Cost / engineering as you want them.',
            'Click **Generate EVM PDF**.',
            'A preview opens fitted to the window — check it, then **Save as PDF** (or Close).',
          ],
          how: [
            { p: 'The preview is the exact report HTML scaled to fit; Save writes the PDF with the same content. Generating a PDF needs Google Chrome installed on the machine.' },
          ],
          where: 'EVM Results → the Generate EVM PDF button at the bottom of the panel.',
        },
      ],
    },
    {
      group: 'Schedule Audit',
      topics: [
        {
          id: 'audit-overview',
          title: 'What the Schedule Audit is',
          whatFor: 'Checks the quality of the schedule’s logic and float as separate, self-contained module reports, each with its own score and grade. It diagnoses and recommends; it never edits your logic.',
          steps: [
            'Import a schedule and choose **Schedule Audit** (or click the shield in the sidebar).',
            'Pick a module tab: **Dangling Activities** or **Float Analysis**.',
            'Read that module’s score, KPIs and findings; export it if needed.',
          ],
          how: [
            { p: 'Each module scores from its own headline percentage on a shared curve, then gets a 4-level grade.' },
            { formula: 'score curve: 0%→100, 2%→90, 5%→75, 8%→50, 20%+→0', note: 'Grades: Excellent (≤2%) · Acceptable (2–5%) · Needs Attention (5–8%) · Critical (>8%). A single overall Schedule Health Score is deliberately deferred until more modules exist, so today each module stands on its own.' },
          ],
          where: 'The Schedule Audit tab; module tabs run across the top.',
        },
        {
          id: 'dangling',
          title: 'Dangling activities',
          whatFor: 'Finds activities whose start or finish is not properly driven by logic — a core DCMA schedule-quality check.',
          steps: [
            'Open Schedule Audit → **Dangling Activities**.',
            'Read the KPIs (Total, Dangling Start, Dangling Finish, both, Dangling %).',
            'Scroll the findings; each row names the issue, the current predecessors/successors, and a suggested logic fix.',
            'Filter by severity or search an activity.',
          ],
          how: [
            { p: '**Dangling Start** = the start is not driven by a Finish-to-Start or Start-to-Start predecessor (includes having no predecessor at all). **Dangling Finish** = the finish does not drive a Finish-to-Start or Finish-to-Finish successor (includes having no successor). Both together is more serious; a dangling activity on the critical path is escalated. The suggested fixes are advisory relationship-type changes only.' },
            { formula: 'Dangling % = dangling activities ÷ total activities', note: 'This % drives the module score and grade.' },
          ],
          reading: {
            good: 'Dangling % ≤ 2% — Excellent logic completeness.',
            bad: 'Dangling % > 8% — Critical; many activities float free of the network.',
          },
          where: 'Schedule Audit → the Dangling Activities tab.',
        },
        {
          id: 'float-analysis',
          title: 'Float analysis',
          whatFor: 'Flags activities carrying excessive total float (above the threshold) or negative float — signs of missing logic, or a schedule behind its need dates.',
          steps: [
            'Open Schedule Audit → **Float Analysis**.',
            'Read the KPIs (Above Threshold, Float %, Max/Average Float, Threshold).',
            'Use the **WBS Summary** to see where high float concentrates, then the findings for each activity.',
          ],
          how: [
            { p: 'An activity is flagged when total float is above the threshold (default 44 working days) or negative. Negative float is Critical (the finish need date is threatened); more than 3× the threshold is High (likely a missing driving successor); otherwise Medium.' },
            { formula: 'Float % = activities above threshold ÷ total activities', note: 'This % drives the module score and grade. The threshold is configurable.' },
          ],
          reading: {
            good: 'Low Float % and no negative float — a well-constrained network.',
            bad: 'Any negative float, or a high Float %, points to missing logic or real delay.',
          },
          where: 'Schedule Audit → the Float Analysis tab.',
        },
        {
          id: 'audit-export',
          title: 'Export an audit module (Excel / PDF)',
          whatFor: 'Save one audit module as an Excel table or a standalone consultant PDF — one module at a time, never mixed.',
          steps: [
            'Open Schedule Audit and select the module you want.',
            'Click **Export Module to Excel** for the data table, or **Generate Module PDF** for the report.',
            'For the PDF, a fitted preview opens first — check it, then Save as PDF.',
          ],
          how: [
            { p: 'The export always reflects the module currently on screen. PDF generation needs Chrome installed.' },
          ],
          where: 'Schedule Audit → the two buttons at the bottom of the panel.',
        },
      ],
    },
    {
      group: 'Calendar Audit',
      topics: [
        {
          id: 'calendar-audit',
          title: 'Calendar Audit',
          whatFor: 'Reviews the project’s working calendars — the timeline of working days, weekends, holidays, shutdowns and working-hour changes — so you can trust the dates the schedule is built on.',
          steps: [
            'Import a schedule and choose **Calendar Audit** (or its tab).',
            'Read the Executive Dashboard — the key dates and the calendar statistics.',
            'Use the calendar picker to switch between the project’s calendars, then scroll the timeline, monthly views, exceptions, hours profile, comparison, usage and conflicts.',
            'Export to Excel, or click **Generate Calendar Audit PDF**.',
          ],
          how: [
            { p: 'It reads every calendar in the P6 file and lays out, per calendar: a colour-coded day timeline (working / weekend / holiday / shutdown / special hours), monthly working-day and working-hour totals, the lists of holidays, reduced-hour periods and shutdowns, the working-hours profile, a comparison across calendars, which calendars are actually used, and any conflicts (such as an unused or contradictory calendar). An automatic Executive Conclusion summarises the findings.' },
          ],
          where: 'The Calendar Audit tab — the third analysis, after EVM Results and Schedule Audit; Export to Excel / Generate Calendar Audit PDF at the bottom.',
        },
      ],
    },
    {
      group: 'Projects and display',
      topics: [
        {
          id: 'recent-projects',
          title: 'Recent projects',
          whatFor: 'The app remembers the last 10 projects so you can re-open them instantly without re-importing, and compare delay / SPI / progress at a glance.',
          steps: [
            'On Home, look at the **Recent Projects** table.',
            'Click **Open** on a row to reload it (from saved results — no re-parsing).',
            'Click the trash icon to delete a project’s whole history (it asks first).',
          ],
          how: [
            { p: 'Every import is parsed once and stored; re-opening reads the saved numbers, so it is instant. A copy of each imported file is cached, so the PDF can still be generated even if you moved the original. All data lives on your machine only.' },
          ],
          where: 'Home → the Recent Projects table.',
        },
        {
          id: 'preview-before-pdf',
          title: 'Preview before PDF',
          whatFor: 'Every PDF (EVM or audit module) is shown on screen first, fitted to the window, so you never print blind.',
          steps: [
            'Click any **Generate PDF** button.',
            'The report opens scaled to fit — review it.',
            'Click **Save as PDF** to write the file, or **Close** to go back.',
          ],
          how: [
            { p: 'The preview is the exact report that will be saved. Saving needs Chrome installed on the machine.' },
          ],
          where: 'Any Generate PDF action, in EVM Results or Schedule Audit.',
        },
        {
          id: 'theme',
          title: 'Light and dark mode',
          whatFor: 'Switch the display between light and dark.',
          steps: [
            'Click the sun / moon icon in the top-right.',
            'Your choice is remembered next time you open the app.',
          ],
          how: [
            { p: 'The sidebar stays dark in both modes by design. The default is light.' },
          ],
          where: 'The top bar → the theme toggle (top-right).',
        },
        {
          id: 'glossary',
          title: 'Glossary of terms',
          whatFor: 'Plain definitions of the core terms used across the app.',
          terms: [
            { term: 'Data date', def: 'The “as of” date of the update — everything planned and earned is measured up to this date.' },
            { term: 'Baseline', def: 'The approved plan (dates and budget) the project is measured against.' },
            { term: 'BAC — Budget at Completion', def: 'An activity’s (or the project’s) total budgeted cost. The app uses the baseline BAC to match P6.' },
            { term: 'Planned Value (PV)', def: 'Budgeted cost of the work that should have been done by the data date.' },
            { term: 'Earned Value (EV)', def: 'Budgeted cost of the work actually completed by the data date.' },
            { term: 'Actual Cost (AC)', def: 'Real money spent to date.' },
            { term: 'SPI', def: 'Schedule Performance Index = EV ÷ PV. 1.0 = on schedule.' },
            { term: 'CPI', def: 'Cost Performance Index = EV ÷ AC. 1.0 = on budget.' },
            { term: 'Total float', def: 'Working days an activity can slip before it delays the project finish. Zero or below = critical.' },
            { term: 'Critical path', def: 'The chain of activities with no spare float that sets the finish date.' },
            { term: 'Dangling activity', def: 'An activity whose start or finish is not properly driven by logic.' },
            { term: 'Out of sequence', def: 'An activity that progressed in a way its predecessor logic did not allow.' },
            { term: 'WBS', def: 'Work Breakdown Structure — the hierarchical grouping of the schedule the app uses to form categories.' },
          ],
          where: 'Help → Glossary (this page).',
        },
      ],
    },
  ],
};
