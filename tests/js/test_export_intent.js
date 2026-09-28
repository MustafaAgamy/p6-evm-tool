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
function harness(view, { result = true, missing = [] } = {}) {
  const log = { clicked: [], errors: [], printed: [] };
  const state = { currentView: view, currentResult: result ? { project_name: 'P', data_date: '2025-12-11' } : null };
  const document = { getElementById: (id) => (missing.includes(id) ? null : { click: () => log.clicked.push(id) }) };
  const CRUMB = { evm: 'Earned Value', lag: 'Lag Report', schedule: 'Schedule (Gantt)', overview: 'Overview', prodintel: 'Productivity & Resources' };
  const sec = () => [{ key: 's', label: 'S', html: '<p>x</p>' }];
  const fn = new Function('state', 'document', 'CRUMB', 'showError', 'printView', 'prodintelPrint', 'overviewPrint',
    'wbsPrint', 'narrativePrint', 'DOC_KINDS', 'docExportRoute', 'requestDocExport', 'clearDocExport', 'noDocExportMessage',
    appSrc.slice(a, b) + '\nreturn { runReport, REPORT_BTN };');
  const api = fn(state, document, CRUMB, (m) => log.errors.push(m), (o) => log.printed.push(o.module), sec, sec, sec,
    () => null, EI.DOC_KINDS, EI.docExportRoute, EI.requestDocExport, EI.clearDocExport, EI.noDocExportMessage);
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
test('screen views (Overview) and library views print through printView with the note', () => {
  EI.clearDocExport();
  const o = harness('overview'); o.runReport('docx');
  assert.deepEqual(o.log.printed, ['overview']);
  assert.equal(EI.takeDocExport().kind, 'docx');
  const l = harness('prodintel', { result: false }); l.runReport('html');
  assert.deepEqual(l.log.printed, ['prodintel']);
  assert.equal(EI.takeDocExport().kind, 'html');
});
test('Excel-only view and no-schedule say so in the page, no pending note', () => {
  EI.clearDocExport();
  const g = harness('schedule'); g.runReport('docx');
  assert.deepEqual(g.log.errors, ['Schedule (Gantt) has no Word export yet — use File ▸ Export to Excel.']);
  const z = harness('evm', { result: false }); z.runReport('html');
  assert.deepEqual(z.log.errors, ['Import a P6 schedule and open a module first.']);
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
test('feature_needs lists Word / HTML exactly where they exist', () => {
  // Adopted previews (api.js passes exports: ADOPTED_EXPORTS) — update when a feature adopts.
  const adoptedViews = ['evm', 'calendar'];
  assert.equal((read('ui', 'modules', 'api.js').match(/exports: ADOPTED_EXPORTS/g) || []).length, adoptedViews.length);
  const own = { narrative: ['Word', 'HTML'], special: ['Word'] };      // REPORT_BTN docx / html
  for (const f of FEATURE_NEEDS) {
    const want = adoptedViews.includes(f.id) ? ['Word', 'HTML'] : (own[f.id] || []);
    for (const k of ['Word', 'HTML']) {
      assert.equal(f.exports.includes(k), want.includes(k), `${f.id}: exports ${k}?`);
    }
  }
  assert.ok(featureNeeds('evm').exports.includes('PDF') && featureNeeds('calendar').exports.includes('Excel'));
});

console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
