/**
 * printView documents are picker-managed (F2): each section is a [data-sec] block in the
 * SELECTED order, so a drag in the Report Contents tree reaches Preview · PDF · Print.
 * Run: node tests/js/test_printview.js
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { composeDoc } from '../../ui/modules/printview.js';
import { scanReport, buildTree, restoreState, moveSection, toggleSection, pruneHtml, canReorder } from '../../ui/modules/report_parts.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (err) { console.error(`  ✗ ${name}\n    ${err.message}`); failed++; }
}
const SECS = [
  { key: 'kpi', label: 'KPI tiles', html: '<div class="k">KPI-BODY</div>' },
  { key: 'wbs', label: 'WBS table', html: '<table><tr><td>WBS-BODY</td></tr></table>' },
  { key: 'gantt', label: 'Gantt', html: '<div>GANTT-BODY</div>' },
  { key: 'none', label: 'Empty', html: '' },
];
const order = (html) => ['KPI-BODY', 'WBS-BODY', 'GANTT-BODY'].map(t => [t, html.indexOf(t)])
  .filter(([, i]) => i >= 0).sort((a, b) => a[1] - b[1]).map(([t]) => t);
// the real app stylesheet rides along in every printView document — the scanner must not trip on it
const APP_CSS = readFileSync(new URL('../../ui/style.css', import.meta.url), 'utf-8');

console.log('\nprintView composeDoc');
test('sections come out in the SELECTED order, not the caller order', () => {
  const html = composeDoc('', 'T', '', SECS, ['gantt', 'kpi']);
  assert.deepEqual(order(html), ['GANTT-BODY', 'KPI-BODY']);
});
test('every section is a [data-sec] block the picker can see (so drag is offered)', () => {
  const html = composeDoc(APP_CSS, 'T', '', SECS, ['kpi', 'wbs', 'gantt']);
  const scan = scanReport(html);
  assert.deepEqual(scan.sections.map(s => s.key), ['kpi', 'wbs', 'gantt']);
  assert.equal(canReorder(scan.sections.length > 0, false), true);
});
test('a drag in the tree reorders the final document (Preview = PDF = Print)', () => {
  const html = composeDoc(APP_CSS, 'T', '', SECS, ['kpi', 'wbs', 'gantt']);
  const tree = buildTree(SECS.map(s => ({ key: s.key, label: s.label, empty: !s.html })), scanReport(html));
  let st = restoreState(null, tree, ['kpi', 'wbs', 'gantt']);
  st = moveSection(st, 'gantt', 'kpi');                       // drag Gantt to the top
  const out = pruneHtml(html, st, { knownSections: tree.map(s => s.key) });
  assert.deepEqual(order(out), ['GANTT-BODY', 'KPI-BODY', 'WBS-BODY']);
  assert.ok(out.includes(APP_CSS.slice(0, 200)), 'the stylesheet is untouched');
});
test('an unticked section is absent from the final document', () => {
  const html = composeDoc('', 'T', '', SECS, ['kpi', 'wbs', 'gantt']);
  const tree = buildTree(SECS.map(s => ({ key: s.key, label: s.label, empty: !s.html })), scanReport(html));
  const st = toggleSection(restoreState(null, tree, ['kpi', 'wbs', 'gantt']), tree, 'wbs', false);
  const out = pruneHtml(html, st, { knownSections: tree.map(s => s.key) });
  assert.deepEqual(order(out), ['KPI-BODY', 'GANTT-BODY']);
  assert.ok(!out.includes('WBS table'));
});
test('section keys are attribute-escaped', () => {
  const html = composeDoc('', 'T', '', [{ key: 'a"b', label: 'X', html: 'x' }], ['a"b']);
  assert.ok(html.includes('data-sec="a&quot;b"'));
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
