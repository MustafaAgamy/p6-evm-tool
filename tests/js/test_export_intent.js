/**
 * File ▸ Export to Word / HTML (Ctrl+Shift+W / Ctrl+Shift+H) routing —
 * ui/modules/export_intent.js + runReport('docx'|'html') in ui/app.js + the preview's take-up.
 *   • Narrative / Reporting Studio → their own richer Word / HTML button.
 *   • Every other report → the SAME preview as File ▸ Print, with a pending export that the
 *     preview's export bar presses (adopted feature) or explains (not adopted yet).
 * Run: node tests/js/test_export_intent.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { dateText } from '../../ui/modules/format.js';
import * as EI from '../../ui/modules/export_intent.js';
import { FEATURE_NEEDS, featureNeeds } from '../../ui/modules/feature_needs.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..', '..');
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), 'utf8');

let passed = 0;
let failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (err) { console.error(`  ✗ ${name}`); console.error(`    ${err.message}`); failed++; }
}

const ADOPTED = ['pdf', 'docx', 'html', 'xlsx'];

console.log('\ndocExportRoute (pure)');
test('no schedule imported → friendly message (library views excepted)', () => {
  assert.equal(EI.docExportRoute({ kind: 'docx', map: { pdf: 'x' }, hasResult: false }).action, 'error');
  assert.equal(EI.docExportRoute({ kind: 'docx', printView: true, standalone: true }).action, 'preview');
});
test('own Word / HTML button wins (Narrative, Reporting Studio)', () => {
  assert.deepEqual(EI.docExportRoute({ kind: 'docx', map: { pdf: 'p', docx: 'w' }, hasResult: true }),
    { action: 'click', id: 'w' });
});
test('a report with a PDF preview → open it with a pending export', () => {
  assert.deepEqual(EI.docExportRoute({ kind: 'html', map: { pdf: 'p', xls: 'x' }, hasResult: true }),
    { action: 'preview', kind: 'html', hasExcel: true });
  assert.equal(EI.docExportRoute({ kind: 'docx', printView: true, hasResult: true }).action, 'preview');
});
test('Excel-only view → message that never offers a PDF it does not have', () => {
  const r = EI.docExportRoute({ kind: 'docx', map: { xls: 'x' }, hasResult: true, what: 'Schedule (Gantt)' });
  assert.equal(r.action, 'error');
  assert.equal(r.msg, 'Schedule (Gantt) has no Word export yet — use File ▸ Export to Excel.');
});
test('own-preview reports (Critical Path, Update vs Update, Update Analysis) say "not yet" up front', () => {
  EI.clearDocExport();
  const r = EI.docExportRoute({ kind: 'docx', map: { pdf: 'p', xls: 'x' }, hasResult: true, ownPreview: true,
    what: 'Critical Path Analyzer' });
  assert.deepEqual(r, { action: 'error',
    msg: 'Critical Path Analyzer has no Word export yet — use File ▸ Print / Export to PDF or File ▸ Export to Excel.' });
  assert.equal(EI.takeDocExport(), null);
});
test('pdf / xls are not doc kinds', () => assert.equal(EI.docExportRoute({ kind: 'pdf', hasResult: true }).action, 'none'));

console.log('\npending export');
test('take clears it; expired notes are dropped', () => {
  EI.requestDocExport('docx', { what: 'Earned Value' }, 1000);
  assert.equal(EI.takeDocExport(1001).kind, 'docx');
  assert.equal(EI.takeDocExport(1002), null);
  EI.requestDocExport('html', {}, 1000);
  assert.equal(EI.takeDocExport(1000 + EI.PENDING_TTL_MS + 1), null);
});
test('adopted preview presses its own button; others explain in the page', () => {
  const p = { kind: 'docx', what: 'Lag Report', hasExcel: true, until: Infinity };
  assert.deepEqual(EI.pendingExportPlan(p, ADOPTED), { click: 'docx' });
  assert.equal(EI.pendingExportPlan(p, ['pdf']).message,
    'Lag Report has no Word export yet — use ⬇ PDF in this preview or File ▸ Export to Excel.');
  assert.equal(EI.pendingExportPlan(null, ADOPTED), null);
});

// ── runReport('docx'|'html') in ui/app.js, run for real against stubs ──────────
console.log('\nrunReport routing (app.js)');
const appSrc = read('ui', 'app.js');
const a = appSrc.indexOf('  const REPORT_BTN = {');
const b = appSrc.indexOf('  function runMenuCmd(cmd)');
assert.ok(a > 0 && b > a, 'REPORT_BTN … runReport block not found in app.js');
function harness(view, { result = true, missing = [], gantt = () => [{ key: 's', label: 'S', html: '<p>x</p>' }] } = {}) {
  const log = { clicked: [], errors: [], printed: [] };
  const state = { currentView: view, currentResult: result ? { project_name: 'P', data_date: '2025-12-11' } : null };
  const document = { getElementById: (id) => (missing.includes(id) ? null : { click: () => log.clicked.push(id) }) };
  const CRUMB = { evm: 'Earned Value', lag: 'Lag Report', schedule: 'Schedule (Gantt)', overview: 'Overview', prodintel: 'Productivity & Resources',
    critpath: 'Critical Path Analyzer', period: 'Update vs Update', update: 'Update Analysis' };
  const sec = () => [{ key: 's', label: 'S', html: '<p>x</p>' }];
  const fn = new Function('state', 'document', 'CRUMB', 'showError', 'printView', 'prodintelPrint', 'overviewPrint',
    'wbsPrint', 'schedulePrint', 'narrativePrint', 'DOC_KINDS', 'docExportRoute', 'requestDocExport', 'clearDocExport', 'noDocExportMessage', 'exportOverviewExcel', 'exportWbsExcel', 'exportScheduleExcel', 'playbooksOpen', 'playbookReport', 'dateText',
    appSrc.slice(a, b) + '\nreturn { runReport, REPORT_BTN };');
  const api = fn(state, document, CRUMB, (m) => log.errors.push(m), (o) => log.printed.push(o.module), sec, sec, sec,
    gantt, () => null, EI.DOC_KINDS, EI.docExportRoute, EI.requestDocExport, EI.clearDocExport, EI.noDocExportMessage, () => {}, () => {}, () => {}, () => false, () => {}, dateText);
  return { ...api, log };
}
test('Earned Value: Ctrl+Shift+W opens the PDF preview and leaves a Word export for its bar', () => {
  EI.clearDocExport();
  const h = harness('evm');
  h.runReport('docx');
  assert.deepEqual(h.log.clicked, ['pdf-btn']);
  assert.deepEqual(h.log.errors, []);
  const p = EI.takeDocExport();
  assert.equal(p.kind, 'docx');
  assert.deepEqual(EI.pendingExportPlan(p, ADOPTED), { click: 'docx' });
});
test('Lag Report (not adopted yet): Ctrl+Shift+H opens the preview, which explains', () => {
  EI.clearDocExport();
  const h = harness('lag');
  h.runReport('html');
  assert.deepEqual(h.log.clicked, ['lag-pdf-btn']);
  const plan = EI.pendingExportPlan(EI.takeDocExport(), ['pdf']);
  assert.match(plan.message, /^Lag Report has no HTML export yet/);
});
test('Baseline Narrative / Reporting Studio keep their own Word', () => {
  EI.clearDocExport();
  const n = harness('narrative'); n.runReport('docx'); n.runReport('html');
  assert.deepEqual(n.log.clicked, ['narrative-word-btn', 'narrative-html-btn']);
  const s = harness('special'); s.runReport('docx');
  assert.deepEqual(s.log.clicked, ['sr-word']);
  assert.equal(EI.takeDocExport(), null);                      // no pending note left behind
});
test('Reporting Studio: File ▸ Print and Ctrl+Shift+H open the Studio preview, never the direct PDF save', () => {
  EI.clearDocExport();
  const s = harness('special');
  s.runReport('pdf');
  assert.deepEqual(s.log.clicked, ['sr-preview']);             // not 'sr-pdf' (straight to a save dialog)
  s.runReport('html');
  assert.deepEqual(s.log.clicked, ['sr-preview', 'sr-preview']);
  assert.deepEqual(s.log.errors, []);
  // The Studio preview offers PDF only → the pending HTML becomes an in-page "not yet" line.
  const plan = EI.pendingExportPlan(EI.takeDocExport(), ['pdf'], 'Reporting Studio');
  assert.match(plan.message, /has no HTML export yet — use ⬇ PDF in this preview/);
  // Wiring: sr-preview is the preview (showReportPreview reads the note); sr-pdf is the direct save.
  const src = read('ui', 'modules', 'special.js');
  assert.match(src, /getElementById\('sr-preview'\)\.addEventListener\('click', doPreview\)/);
  assert.match(src, /getElementById\('sr-pdf'\)\.addEventListener\('click', \(\) => doExport\('pdf'\)\)/);
  const pv = src.slice(src.indexOf('async function doPreview'), src.indexOf('async function doExport'));
  assert.match(pv, /showReportPreview\(/);
  assert.match(pv, /exports: \['pdf'\]/);
});
test('every File menu button id in REPORT_BTN exists in the UI (F3: Studio Excel was sr-xls, button is sr-excel)', () => {
  const { REPORT_BTN } = harness('special');
  const ui = [read('ui', 'index.html'), appSrc]
    .concat(fs.readdirSync(path.join(ROOT, 'ui', 'modules')).filter((f) => f.endsWith('.js')).map((f) => read('ui', 'modules', f)))
    .join('\n')
    .replace(appSrc.slice(a, b), '');                          // the REPORT_BTN map itself does not count
  const missing = [];
  for (const [view, btns] of Object.entries(REPORT_BTN)) {
    for (const [kind, id] of Object.entries(btns)) {
      if (!ui.includes(`"${id}"`) && !ui.includes(`'${id}'`)) missing.push(`${view}.${kind}=${id}`);
    }
  }
  assert.deepEqual(missing, []);
  assert.equal(REPORT_BTN.special.xls, 'sr-excel');
  const s = harness('special'); s.runReport('xls');
  assert.deepEqual(s.log.clicked, ['sr-excel']);
  assert.deepEqual(s.log.errors, []);
});
test('screen views (Overview) and library views print through printView with the note', () => {
  EI.clearDocExport();
  const o = harness('overview'); o.runReport('docx');
  assert.deepEqual(o.log.printed, ['overview']);
  assert.equal(EI.takeDocExport().kind, 'docx');
  const l = harness('prodintel', { result: false }); l.runReport('html');
  assert.deepEqual(l.log.printed, ['prodintel']);
  assert.equal(EI.takeDocExport().kind, 'html');
});
test('Schedule (Gantt) prints through printView (comment 26); no-schedule says so in the page', () => {
  EI.clearDocExport();
  const g = harness('schedule'); g.runReport('docx');
  assert.deepEqual(g.log.errors, []);
  assert.deepEqual(g.log.printed, ['schedule']);                 // the same preview as File ▸ Print
  assert.equal(EI.takeDocExport().kind, 'docx');                 // … which then presses its own Word button
  const z = harness('evm', { result: false }); z.runReport('html');
  assert.deepEqual(z.log.errors, ['Import a P6 schedule and open a module first.']);
  assert.equal(EI.takeDocExport(), null);
});
test('F6: File ▸ Print on Schedule (Gantt) opens its preview — never "run the analysis first"', () => {
  const g = harness('schedule');
  g.runReport('pdf');
  assert.deepEqual(g.log.clicked, []);
  assert.deepEqual(g.log.errors, []);
  assert.deepEqual(g.log.printed, ['schedule']);
  g.runReport('xls');                                           // its Excel still works
  assert.deepEqual(g.log.clicked, ['sched-excel-btn']);
  // a re-opened project whose schedule file is gone has no rows: a true message, no preview
  const n = harness('schedule', { gantt: () => null }); n.runReport('pdf');
  assert.deepEqual(n.log.printed, []);
  assert.deepEqual(n.log.errors, ['This project has no activity timeline to print — import the schedule again to rebuild the Gantt.']);
  // "Run first" stays for a report whose button is registered but not on screen yet.
  const e = harness('evm', { missing: ['pdf-btn', 'evm-excel-btn'] });
  e.runReport('pdf'); e.runReport('xls');
  assert.deepEqual(e.log.errors, ['Run this module’s analysis first, then File ▸ Print / Export to PDF.',
    'Run this module’s analysis first, then File ▸ Export to Excel.']);
});
test('Critical Path / Update vs Update / Update Analysis: Word / HTML open the shared preview, which explains', () => {
  // They use the shared preview now (comment 1), so they behave like every other report: the
  // preview opens with the note and says in the page that Word / HTML is not offered yet.
  for (const [view, name, btn] of [['critpath', 'Critical Path Analyzer', 'cpa-export-pdf'],
    ['period', 'Update vs Update', 'per-export-pdf'], ['update', 'Update Analysis', 'ua-export-pdf']]) {
    for (const [kind, label] of [['docx', 'Word'], ['html', 'HTML']]) {
      EI.clearDocExport();
      const h = harness(view);
      h.runReport(kind);
      assert.deepEqual(h.log.clicked, [btn], `${view} ${kind}: opens its PDF preview`);
      assert.deepEqual(h.log.errors, []);
      const plan = EI.pendingExportPlan(EI.takeDocExport(), ['pdf']);
      assert.match(plan.message, new RegExp(`^${name} has no ${label} export yet`));
    }
  }
});
test('Word / HTML asked on a report that cannot open its preview leaves no note behind', () => {
  EI.clearDocExport();
  const h = harness('evm', { missing: ['pdf-btn'] });        // analysis not run → no PDF button
  h.runReport('docx');
  assert.deepEqual(h.log.clicked, []);
  assert.equal(h.log.errors.length, 1);
  assert.equal(EI.takeDocExport(), null);
});
test('a later File ▸ Print drops a stale pending Word export', () => {
  const h = harness('evm');
  h.runReport('docx');
  h.runReport('pdf');
  assert.equal(EI.takeDocExport(), null);
});

console.log('\nwiring guards');
const previewSrc = read('ui', 'modules', 'preview.js');
test('showReportPreview takes the pending export and presses its own bar button', () => {
  assert.match(previewSrc, /pendingExportPlan\(takeDocExport\(\), offered\.map\(e => e\.kind\), featureName\)/);
  assert.match(previewSrc, /querySelector\(`#rpv-save-\$\{plan\.click\}`\)/);
});
test('moving to another feature drops a pending Word / HTML note (openView + setCrumb)', () => {
  const ov = appSrc.slice(appSrc.indexOf('  function openView(view) {'));
  assert.match(ov.slice(0, ov.indexOf('\n  }\n')), /clearDocExport\(\)/);
  assert.match(appSrc, /const setCrumb = \(id\) => \{ clearDocExport\(\);/);
});
test('no report keeps a private preview: every one opens the shared picker (comment 1)', () => {
  // Critical Path, Update vs Update and Update Analysis had their own overlay; they now use
  // showReportPreview, so the Word / HTML note is read like in every other report.
  assert.match(appSrc, /const OWN_PREVIEW = new Set\(\);/);
  for (const m of ['critpath', 'period', 'update']) {
    const src = read('ui', 'modules', `${m}.js`);
    assert.match(src, /showReportPreview\(\{/, `${m}.js opens the shared preview`);
    assert.ok(!/per-preview-overlay/.test(src), `${m}.js still builds its own overlay`);
  }
});
test('feature_needs lists Word / HTML for every feature that has a report (comment 2)', () => {
  // Every report preview offers the full bar now: four callers in api.js (EVM, Calendar, the
  // Schedule Health checks, Bad Weather) plus compare / revcompare / update / period / critpath,
  // and every printView screen view (Word + HTML beside PDF).
  assert.equal((read('ui', 'modules', 'api.js').match(/exports: ADOPTED_EXPORTS/g) || []).length, 3);
  assert.match(read('ui', 'modules', 'api.js'), /exports: module === '__summary__' \? \['pdf', 'docx', 'html'\] : ADOPTED_EXPORTS/);
  for (const m of ['compare', 'revcompare', 'update', 'period', 'critpath']) {
    assert.match(read('ui', 'modules', `${m}.js`), /exports: \['pdf', 'docx', 'html', 'xlsx'\]/, m);
    assert.match(read('ui', 'modules', `${m}.js`), /onExcel: \(\) =>/, m + ' gives its own workbook');
  }
  assert.match(read('ui', 'modules', 'printview.js'), /exports: exports \|\| \(onExcel \? \['pdf', 'docx', 'html', 'xlsx'\] : \['pdf', 'docx', 'html'\]\), onExcel,/);
  for (const fn of ['exportOverviewExcel', 'exportWbsExcel', 'exportScheduleExcel']) assert.ok(read('ui', 'app.js').includes('excel: ' + fn), fn);
  const none = ['home', 'recent', 'chat'];                           // no report
  const wordOnly = ['special'];                                      // the Studio: its own Word, no HTML
  for (const f of FEATURE_NEEDS) {
    const want = none.includes(f.id) ? [] : (wordOnly.includes(f.id) ? ['Word'] : ['Word', 'HTML']);
    for (const k of ['Word', 'HTML']) {
      assert.equal(f.exports.includes(k), want.includes(k), `${f.id}: exports ${k}?`);
    }
  }
  assert.ok(featureNeeds('evm').exports.includes('PDF') && featureNeeds('calendar').exports.includes('Excel'));
});

test('Knowledge Base page: File ▸ Print / Excel run the page\'s own exports', () => {
  const app = read('ui', 'app.js'); const kb = read('ui', 'modules', 'knowledge.js');
  assert.ok(app.includes("if (DOC_KINDS[kind]) requestDocExport(kind, { what: 'Knowledge Base', hasExcel: true });"));   // Word / HTML: its preview presses them (comment 43)
  assert.ok(app.includes("playbookReport(kind === 'xls' ? 'xls' : 'pdf');"));
  assert.match(kb, /export function playbookReport\(kind\) \{ if \(kind === 'xls'\) exportExcel\(\); else exportPdf\(\); \}/);
  assert.match(kb, /onExcel: \(\) => exportExcel\(\)/);              // the preview carries the Excel button too
});

test('Excel can wait for the preview too: Ctrl+E on a view whose Excel lives in its preview (comment 43)', () => {
  assert.deepEqual(Object.keys(EI.PENDING_KINDS).sort(), ['docx', 'html', 'xlsx']);
  assert.ok(!('xlsx' in EI.DOC_KINDS), 'Ctrl+E is not routed as a Word / HTML command');
  EI.requestDocExport('xlsx', { what: 'Earned Value', hasExcel: true }, 1000);
  assert.deepEqual(EI.pendingExportPlan(EI.takeDocExport(1001), ['pdf', 'docx', 'html', 'xlsx'], 'EVM'), { click: 'xlsx' });
  EI.requestDocExport('xlsx', { what: 'X' }, 1000);
  assert.match(EI.pendingExportPlan(EI.takeDocExport(1001), ['pdf'], 'X').message, /has no Excel export yet/);
  const app = read('ui', 'app.js');
  assert.ok(app.includes("if (pv && pv.excel) { pv.excel(); return true; }"));
  assert.ok(app.includes("requestDocExport('xlsx', { what: CRUMB[state.currentView] || 'This view', hasExcel: true });"));
  assert.ok(app.includes("if (kind === 'xls' && pvSolo.excel) { pvSolo.excel(); return true; }"));
});

console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
