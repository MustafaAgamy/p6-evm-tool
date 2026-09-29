// What each feature needs — ONE data structure for the whole app.
//
// Help ▸ Feature guide (help.js), the "Needs: …" line under every item of the Analysis
// menu and the tooltip of every Project Navigator item (app.js) and the Ctrl+K command
// palette (palette.js) are ALL generated from FEATURE_NEEDS below — so the three can never
// disagree. tests/js/test_feature_needs.js fails if a navigator item has no entry here.
//
// Every requirement is DERIVED FROM THE CODE, not guessed:
//   • schedule files — every schedule picker is the same native dialog (app.py choose_file:
//     *.xml;*.xer) and every engine reads the file through p6_evm/parser.parse_file, which
//     accepts BOTH formats (p6_evm/xer.py for .xer). So "XER or XML" everywhere, except
//     where a handler checks the extension (called out in `files[].note`).
//   • baseline — ONE resolution for every feature (p6_evm/baseline.py, server._schedule_for):
//     the baseline inside the file (an XML exported from P6 WITH its baseline project,
//     <BaselineProject>, parser.py), else the baseline the planner attached for this update
//     (XER or XML — "Attach baseline" on Earned Value / Update Analysis, remembered per snapshot:
//     db.get_attached_baseline), else the file's own Planned dates stand in, flagged
//     baseline_source 'self' (an XER never carries its baseline; nor does an XML exported
//     without it — xer.py / parser.py baseline_by_id).
//   • second / third files — from each feature's server handler + panel (compare.js,
//     revcompare.js, period.js, critpath.js, special providers).
//
// Fields:
//   id, name, group — the navigator id / label / group (app.js NAV); 'chat' lives on the
//                     menu bar; 'home' is the navigator root.
//   what            — one line: what the feature is for.
//   hint            — the compact "Needs: …" line (menu + navigator tooltip + palette).
//   files           — [{ n, role, formats, k, note? }]; k: 'p6' (the imported schedule),
//                     'extra' (another file you pick), 'optional'. [] = no schedule file.
//   other           — other inputs (logs, milestones, location, settings…).
//   recommend       — optional: the recommended format and why.
//   produces        — what you get on screen.
//   exports         — the files you can save.
//   start           — how to start (menu path).

const XER_OR_XML = 'XER or XML';

// What to do when an update carries no baseline for Update Analysis. Shown on the Update Analysis
// screen (update.js, code 'no_baseline') AND in the Help note below, so the two can never disagree.
// /api/update/analyze reads the update through the one baseline resolver (server._schedule_for:
// the baseline inside the file, else the one attached for this update) and refuses to measure it
// against its own Planned dates — so attaching the baseline (XER or XML) is the fix.
export const UPDATE_NO_BASELINE_ADVICE =
  'Attach the baseline (XER or XML) with the button on this screen or on Earned Value — it is remembered ' +
  'for this update and used by every feature — or re-export the update from P6 as XML with its baseline ' +
  'project included.';

export const FEATURE_NEEDS = [
  {
    id: 'home', name: 'Import a schedule', group: '',
    what: 'Bring a Primavera P6 export into the tool — nothing is analysed until you pick a feature and press Run.',
    hint: '1 P6 schedule file — XER or XML',
    files: [{ n: 1, role: 'P6 schedule — a baseline or an update', formats: XER_OR_XML, k: 'p6' }],
    other: [],
    produces: 'The project is read, stored on this PC (Recent Projects) and every feature unlocks.',
    exports: [],
    start: 'File ▸ Import XML / XER… (Ctrl+O)',
  },

  // ── Project Overview ────────────────────────────────────────────────────────
  {
    id: 'overview', name: 'Overview', group: 'Project Overview',
    what: 'A one-page snapshot of progress and category performance.',
    hint: '1 P6 schedule (XER or XML)',
    files: [{ n: 1, role: 'P6 schedule — baseline or update (the imported file)', formats: XER_OR_XML, k: 'p6' }],
    other: [],
    produces: 'Progress snapshot with category planned vs actual %.',
    exports: ['PDF', 'Excel'],
    start: 'Navigator ▸ Project Overview ▸ Overview',
  },
  {
    id: 'wbs', name: 'WBS', group: 'Project Overview',
    what: 'Work-breakdown roll-up with weighted progress, dates and a timeline.',
    hint: '1 P6 schedule (XER or XML)',
    files: [{ n: 1, role: 'P6 schedule — baseline or update (the imported file)', formats: XER_OR_XML, k: 'p6' }],
    other: [],
    produces: 'WBS tree rolled up to the activity level — planned / actual %, start / finish, timeline.',
    exports: ['PDF', 'Excel'],
    start: 'Navigator ▸ Project Overview ▸ WBS',
  },
  {
    id: 'schedule', name: 'Schedule (Gantt)', group: 'Project Overview',
    what: 'A time-scaled Gantt of the activities, grouped by WBS.',
    hint: '1 P6 schedule (XER or XML)',
    files: [{ n: 1, role: 'P6 schedule — baseline or update (the imported file)', formats: XER_OR_XML, k: 'p6' }],
    other: [],
    produces: 'Gantt chart of every activity grouped by WBS.',
    exports: ['Excel'],
    start: 'Navigator ▸ Project Overview ▸ Schedule (Gantt)',
  },

  // ── Schedule Quality ────────────────────────────────────────────────────────
  {
    id: 'audit', name: 'Schedule Health', group: 'Schedule Quality',
    what: 'DCMA-style checks on logic, constraints, float, lags and durations.',
    hint: '1 P6 schedule (XER or XML) + your contract milestones',
    files: [{ n: 1, role: 'P6 schedule — normally the baseline programme (it scores baseline health)', formats: XER_OR_XML, k: 'p6' }],
    other: [
      'Contract milestones — required before any result shows: type the project completion milestone (and any other contractual milestones), pick the matching milestone activity from the file and enter the contract date. Saved per project.',
    ],
    produces: 'Health score and every check with its findings; Resolve & Correct for dangling activities.',
    exports: ['PDF', 'Excel', 'Corrected schedule (same format as the import: XER or XML)'],
    start: 'Navigator ▸ Schedule Quality ▸ Schedule Health',
  },
  {
    id: 'narrative', name: 'Baseline Narrative', group: 'Schedule Quality',
    what: 'A written basis-of-schedule narrative generated from the programme.',
    hint: '1 baseline schedule (XER or XML) + short setup questions',
    files: [{ n: 1, role: 'The baseline programme (the imported file)', formats: XER_OR_XML, k: 'p6',
      note: 'The currency is read only from an XER (an XML has no currency table), so money figures in an XML narrative carry no currency symbol.' }],
    other: ['Guided setup — answer a few short questions before Generate.'],
    produces: 'A full narrative document with tables and charts, section by section.',
    exports: ['Word', 'PDF', 'HTML', 'Excel'],
    start: 'Navigator ▸ Schedule Quality ▸ Baseline Narrative',
  },
  {
    id: 'lag', name: 'Lag Report', group: 'Schedule Quality',
    what: 'Every relationship lag and lead, with a justification register.',
    hint: '1 P6 schedule (XER or XML)',
    files: [{ n: 1, role: 'P6 schedule — baseline or update (the imported file)', formats: XER_OR_XML, k: 'p6' }],
    other: ['Optional: a written justification against each lag (typed in the register, saved per project).'],
    produces: 'Lag / lead register with the justification column.',
    exports: ['PDF', 'Excel'],
    start: 'Navigator ▸ Schedule Quality ▸ Lag Report',
  },

  // ── Progress & Performance ──────────────────────────────────────────────────
  {
    id: 'evm', name: 'Earned Value', group: 'Progress & Performance',
    what: 'Planned vs earned value, SPI / CPI and finish delay from this update.',
    hint: '1 update + its baseline (inside the XML, or attached: XER or XML) · optional E1 log',
    files: [
      { n: 1, role: 'Current update (progressed, with a data date) — the imported file', formats: XER_OR_XML, k: 'p6' },
      { n: 1, role: 'Baseline — for an update that doesn’t carry it (an XER, or an XML exported without its baseline project); the tool asks for it after you run', formats: XER_OR_XML, k: 'optional',
        note: 'An XER never carries its baseline, and an XML carries it only when exported from P6 with the baseline project included. Without it, Planned Value, SPI and Delay are measured against the update’s own Planned dates (approximate). With the baseline attached the results equal the XML exported with its baseline — and the attachment is remembered for this update and used by every feature (Update Analysis, reports, AI Chat).' },
    ],
    other: [
      'Project Setup (✎ on the Earned Value screen) — category weights and Actual Cost.',
      'Optional: one or more E1 / design / shop-drawing logs (Excel .xlsx or .xlsm) for the Engineering section.',
    ],
    recommend: 'XML exported from P6 with its baseline project included — one file, exact Planned Value. An update + its attached baseline gives the same numbers.',
    produces: 'PV, EV, AC, SPI, CPI, delay in days and category progress.',
    exports: ['PDF', 'Word', 'HTML', 'Excel'],   // the preview's export bar (report adopted: docs/report-picker-adoption.md)
    start: 'Navigator ▸ Progress & Performance ▸ Earned Value (Alt+1)',
  },
  {
    id: 'oos', name: 'Out of Sequence', group: 'Progress & Performance',
    what: 'Activities whose actual progress breaks their predecessor logic.',
    hint: '1 progressed update (XER or XML)',
    files: [{ n: 1, role: 'A progressed update — needs actual start / finish dates (a baseline with no progress has nothing to flag)', formats: XER_OR_XML, k: 'p6' }],
    other: [],
    produces: 'Out-of-sequence register by WBS, root causes and the effect on the critical path; Resolve & Correct per finding.',
    exports: ['PDF', 'Excel', 'Corrected schedule (same format as the import: XER or XML)'],
    start: 'Navigator ▸ Progress & Performance ▸ Out of Sequence',
  },
  {
    id: 'update', name: 'Update Analysis', group: 'Progress & Performance',
    what: 'This update measured against its baseline — the one inside the file, or the one attached for it.',
    hint: '1 update + its baseline (inside the XML, or attached: XER or XML)',
    files: [
      { n: 1, role: 'Current update — the imported file', formats: XER_OR_XML, k: 'p6',
        note: 'Needs a real baseline. An XML exported from P6 with its baseline project included carries it; an XER never does, nor does an XML exported without it — then the screen stops with "no baseline" (it never measures the update against its own Planned dates) and offers to attach it. If the screen says there is no baseline: ' + UPDATE_NO_BASELINE_ADVICE },
      { n: 1, role: 'Baseline — only when the update doesn’t carry it; attach it on this screen or on Earned Value', formats: XER_OR_XML, k: 'optional',
        note: 'The same attachment Earned Value uses — remembered for this update and used by every feature. Update + attached baseline gives the same result as the XML exported with its baseline.' },
    ],
    other: [],
    recommend: 'XML exported from P6 with its baseline — one file. An XER (or an XML without it) + its attached baseline gives the same result.',
    produces: 'Time status, planned vs actual by activity code, activity counts, scope weights and the critical path.',
    exports: ['PDF', 'Excel'],
    start: 'Navigator ▸ Progress & Performance ▸ Update Analysis (Alt+3)',
  },
  {
    id: 'critpath', name: 'Critical Path', group: 'Progress & Performance',
    what: 'Driving path and float health across two or three schedules.',
    hint: 'current update + a baseline and/or previous update (XER or XML)',
    files: [
      { n: 1, role: 'Current update — the imported file', formats: XER_OR_XML, k: 'p6' },
      { n: 1, role: 'Baseline — for "Update vs Baseline" (default) and "Two updates + Baseline"', formats: XER_OR_XML, k: 'extra' },
      { n: 1, role: 'Previous update — for "Two updates" and "Two updates + Baseline"', formats: XER_OR_XML, k: 'extra' },
    ],
    tag: '2–3 files',
    other: ['Choose the comparison mode: Two updates · Update vs Baseline · Two updates + Baseline.'],
    produces: 'Critical-path census, path lanes, milestones and float migration between the schedules.',
    exports: ['PDF', 'Excel'],
    start: 'Navigator ▸ Progress & Performance ▸ Critical Path (Alt+4)',
  },

  // ── Compare & Claims ────────────────────────────────────────────────────────
  {
    id: 'period', name: 'Update vs Update', group: 'Compare & Claims',
    what: 'This period against last period.',
    hint: 'current update + previous update (XER or XML)',
    files: [
      { n: 1, role: 'Current update — the imported file', formats: XER_OR_XML, k: 'p6' },
      { n: 1, role: 'Previous update — suggested automatically when you imported an earlier update of the same project; otherwise pick it', formats: XER_OR_XML, k: 'extra' },
    ],
    other: ['The milestone slip trend uses every update of this project you have imported.'],
    produces: 'Progress vs last period’s forecast, % variance, critical-path movement and the period S-curve.',
    exports: ['PDF', 'Excel'],
    start: 'Navigator ▸ Compare & Claims ▸ Update vs Update',
  },
  {
    id: 'compare', name: 'Consultant Review', group: 'Compare & Claims',
    what: 'Forensic baseline vs update review with a but-for delay.',
    hint: 'current update + baseline (XER or XML); but-for step needs an XML update',
    files: [
      { n: 1, role: 'Current update — the imported file', formats: XER_OR_XML, k: 'p6',
        note: 'The corrected but-for file can only be written from an XML update.' },
      { n: 1, role: 'Baseline programme', formats: XER_OR_XML, k: 'extra' },
      { n: 1, role: 'Optional but-for step: the corrected file rescheduled in P6 (F9) and re-exported', formats: XER_OR_XML, k: 'optional',
        note: 'Only WRITING the corrected file needs the update as XML; the rescheduled re-export you load back can be XER or XML.' },
    ],
    other: [],
    recommend: 'XML for the update — required to write the corrected but-for file.',
    produces: 'Driving-logic, lag and duration changes vs the baseline; reported vs but-for delay and a recommendation.',
    exports: ['PDF', 'Excel', 'Corrected but-for XML'],
    start: 'Navigator ▸ Compare & Claims ▸ Consultant Review',
  },
  {
    id: 'revcompare', name: 'Baseline Revision', group: 'Compare & Claims',
    what: 'Two approved baseline revisions compared (Rev.00 vs Rev.01).',
    hint: '2 baselines: Rev.00 + Rev.01 (each XER or XML)',
    files: [
      { n: 1, role: 'Rev.00 — the original baseline', formats: XER_OR_XML, k: 'extra' },
      { n: 1, role: 'Rev.01 — the revised baseline (pre-filled with the imported schedule; change it if needed)', formats: XER_OR_XML, k: 'p6' },
    ],
    other: ['Import any schedule first — the feature opens from the navigator once a schedule is loaded.'],
    recommend: 'Either format — each revision is read the same way, and the two may differ.',
    produces: 'Executive summary, change register, critical path & sequence, milestones, calendars and manpower changes.',
    exports: ['PDF', 'Excel'],
    start: 'Navigator ▸ Compare & Claims ▸ Baseline Revision (Alt+5)',
  },

  // ── Calendars & Weather ─────────────────────────────────────────────────────
  {
    id: 'calendar', name: 'P6 Calendar Audit', group: 'Calendars & Weather',
    what: 'Working-time calendars, net working days and a two-calendar comparison.',
    hint: '1 P6 schedule (XER or XML)',
    files: [{ n: 1, role: 'P6 schedule — baseline or update (the imported file)', formats: XER_OR_XML, k: 'p6' }],
    other: ['Optional: a note against each reduced-hours working period (saved with the project, printed in the PDF).'],
    produces: 'Calendar register, net-working-days histogram and a side-by-side calendar comparison.',
    exports: ['PDF', 'Word', 'HTML', 'Excel'],   // the preview's export bar (report adopted: docs/report-picker-adoption.md)
    start: 'Navigator ▸ Calendars & Weather ▸ P6 Calendar Audit (Alt+6)',
  },
  {
    id: 'weather', name: 'Bad Weather', group: 'Calendars & Weather',
    what: 'Bad-weather stop-work days and their effect on the forecast finish.',
    hint: '1 P6 schedule + project location + site type · internet',
    files: [{ n: 1, role: 'P6 schedule — the imported file', formats: XER_OR_XML, k: 'p6' }],
    other: [
      'Project location — search a place or drop a pin on the map.',
      'Site type (marine / desert / coastal / building / custom) — sets the stop-work limits; every limit is editable.',
      'Internet connection — the map, the place search (OpenStreetMap) and the weather history (Open-Meteo) are online.',
    ],
    produces: 'Weather effect on the forecast finish — waterfall and a three-colour day histogram.',
    exports: ['PDF', 'Excel'],
    start: 'Navigator ▸ Calendars & Weather ▸ Bad Weather',
  },

  // ── Reports ─────────────────────────────────────────────────────────────────
  {
    id: 'special', name: 'Reporting Studio', group: 'Reports',
    what: 'Pick results from any feature and build one report — as a document or a dashboard.',
    hint: 'an imported schedule; comparison items ask for their extra file',
    files: [
      { n: 1, role: 'An imported schedule (to open the Studio)', formats: XER_OR_XML, k: 'p6' },
      { n: 1, role: 'Only for comparison items: baseline, previous update or Rev.00 — the Studio asks for it', formats: XER_OR_XML, k: 'optional',
        note: 'Every slot accepts XER or XML, whatever its label says (the "Rescheduled corrected (but-for) XML" slot too). The open schedule is read with its own baseline, else the one attached on Earned Value / Update Analysis. The but-for item needs the rescheduled corrected file — writing that corrected file (in Consultant Review) needs the update as XML; the rescheduled re-export itself can be XER or XML.' },
    ],
    other: [],
    produces: 'One composed report from the results you pick, in the order you choose.',
    exports: ['Word', 'PDF', 'Excel'],
    start: 'Navigator ▸ Reports ▸ Reporting Studio (Alt+7)',
  },

  // ── Library ─────────────────────────────────────────────────────────────────
  {
    id: 'prodintel', name: 'Productivity & Resources', group: 'Library',
    what: 'Productivity norms → man-hours, crew and duration for a work item.',
    hint: 'no schedule — pick a work item + quantity',
    files: [],
    other: ['Pick a work item, enter the quantity and the project context (project type, location, method, shift hours).'],
    produces: 'Man-hours, crew and duration with the basis of estimate and P6 resource guidance.',
    exports: ['PDF', 'Excel'],
    start: 'Navigator ▸ Library ▸ Productivity & Resources (or Tools ▸ Productivity & Resources)',
  },
  {
    id: 'kb', name: 'Knowledge Base', group: 'Library',
    what: 'The local construction knowledge library, by project type.',
    hint: 'no schedule needed · optional: learn from a project XER or XML',
    files: [{ n: 1, role: 'Optional: a real project to learn from', formats: XER_OR_XML, k: 'optional' }],
    other: ['Optional: import a knowledge file (.json).'],
    produces: 'Reference standards per project type, example baselines and the learned knowledge projects.',
    exports: [
      'Starter baseline (XML)',
      'Example baseline with typical gaps (XML)',
      'Clean reference baseline (XML)',
      'Contributed schedules (in their own format: XER or XML)',
      'Raw learned project file (as it was learned: XER or XML)',
      'Knowledge file (.json)',
    ],
    start: 'Navigator ▸ Library ▸ Knowledge Base (or Tools ▸ Knowledge Base)',
  },
  {
    id: 'construct', name: 'Constructability', group: 'Library',
    what: 'Reviews sequencing and logic against the built-in construction knowledge base.',
    hint: '1 P6 schedule (XER or XML)',
    files: [{ n: 1, role: 'P6 schedule — the imported file', formats: XER_OR_XML, k: 'p6' }],
    other: ['Optional: override the detected project sub-type.'],
    produces: 'Rule-based review of the programme against the knowledge base.',
    exports: ['PDF', 'Excel'],
    start: 'Navigator ▸ Library ▸ Constructability',
  },
  {
    id: 'recent', name: 'Recent Projects', group: 'Library',
    what: 'Every project imported on this PC — re-open without re-importing.',
    hint: 'no file — uses projects already imported',
    files: [],
    other: [],
    produces: 'List of imported projects with their latest import; re-open the stored results; remove a project’s history.',
    exports: [],
    start: 'Navigator ▸ Library ▸ Recent Projects (File ▸ Recent projects, Alt+9)',
  },

  // ── Menu bar ────────────────────────────────────────────────────────────────
  {
    id: 'chat', name: 'AI Chat', group: 'Menu bar',
    what: 'Offline assistant: 15 grounded answers, time-impact, what-if and a manager’s briefing.',
    hint: '1 P6 schedule (XER or XML) — imported, or sent inside the chat',
    files: [{ n: 1, role: 'P6 schedule — the imported one, or send one inside the chat (📎)', formats: XER_OR_XML, k: 'p6' }],
    other: ['Works offline — no internet and no cloud AI.'],
    produces: 'Answers with tables and charts, a time-impact analysis, what-if scenarios and a manager’s briefing.',
    exports: ['What-if scenario (P6 XML)'],
    start: 'Menu bar ▸ AI Chat (Alt+8)',
  },
];

const BY_ID = new Map(FEATURE_NEEDS.map(f => [f.id, f]));

// The entry for a navigator / menu id, or null.
export function featureNeeds(id) {
  return BY_ID.get(id) || null;
}

// "Needs: 1 P6 schedule (XER or XML)" — the compact line under Analysis-menu items and in
// navigator tooltips. '' for an unknown id.
export function needsHint(id) {
  const f = BY_ID.get(id);
  return f ? 'Needs: ' + f.hint : '';
}

// Navigator tooltip: "<what>\nNeeds: <hint>".
export function needsTooltip(id) {
  const f = BY_ID.get(id);
  return f ? `${f.what}\nNeeds: ${f.hint}` : '';
}

// Everything a search box should match on for one entry (lower-case).
export function needsSearchText(f) {
  if (!f) return '';
  return [
    f.name, f.group, f.what, f.hint, f.produces, f.start, f.recommend || '',
    ...(f.files || []).flatMap(x => [x.role, x.formats, x.note || '']),
    ...(f.other || []),
    ...(f.exports || []),
  ].join(' ').toLowerCase();
}

// Entries whose text contains every word of `query` (blank → all), in registry order.
export function filterNeeds(query, list = FEATURE_NEEDS) {
  const words = String(query || '').toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return list.slice();
  return list.filter(f => { const hay = needsSearchText(f); return words.every(w => hay.includes(w)); });
}

// Entries grouped for display — [{group, items}] in first-appearance order ('' → the root).
export function needsGroups(list = FEATURE_NEEDS) {
  const out = [];
  const idx = new Map();
  for (const f of list) {
    if (!idx.has(f.group)) { idx.set(f.group, out.length); out.push({ group: f.group, items: [] }); }
    out[idx.get(f.group)].items.push(f);
  }
  return out;
}

// How many schedule files a feature asks for (required ones only).
export function requiredFileCount(f) {
  return (f && f.files ? f.files : []).filter(x => x.k === 'p6' || x.k === 'extra').length;
}

// The small corner tag on a Help card: "2 files" / "2–3 files" (blank for one-file features).
export function fileTag(f) {
  if (!f) return '';
  if (f.tag) return f.tag;
  const n = requiredFileCount(f);
  return n >= 2 ? `${n} files` : '';
}
