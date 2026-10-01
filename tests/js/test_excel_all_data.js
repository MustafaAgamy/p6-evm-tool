// Owner comment 29 — "Excel must include ALL the data of a feature".
// The UI side of it: the Baseline Narrative has its own Export Excel button that sends the report
// on screen (so the workbook follows the Report-Contents selection like Word / PDF / HTML), and the
// Milestone Check export sends the schedule's milestones the screen holds.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert';
import { fileURLToPath } from 'node:url';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const narrative = read('ui/modules/narrative.js');
const api = read('ui/modules/api.js');
const app = read('ui/app.js');

let passed = 0;
function test(name, fn) { fn(); passed += 1; console.log('  ok  ' + name); }

test('the Narrative screen builds an Export Excel button beside its other exports', () => {
  assert.ok(/x\.id = 'narr-excel-btn'/.test(narrative));
  assert.ok(/x\.textContent = 'Export Excel'/.test(narrative));
  assert.ok(/x\.addEventListener\('click', \(\) => exportNarrative\('xlsx'\)\)/.test(narrative));
});

test('the xlsx kind goes to the /api/narrative/excel route with the report on screen', () => {
  assert.ok(/NARRATIVE_ROUTES = \{ xlsx: 'excel' \}/.test(narrative));
  assert.ok(narrative.includes('/api/narrative/${NARRATIVE_ROUTES[kind] || kind}'));
  assert.ok(/NARRATIVE_BTN_IDS = \{[^}]*xlsx: 'narr-excel-btn'/.test(narrative));
  assert.ok(/NARRATIVE_OK_LABELS = \{[^}]*xlsx: '✓ Excel saved'/.test(narrative));
  // one export function for all four kinds → the same document (exportDoc) reaches the workbook
  assert.ok(/body: JSON\.stringify\(\{ doc: exportDoc\(\), edits: \{\}, output_path: outputPath \}\)/.test(narrative));
});

test('the button is wired once, by narrative.js — not a second time by app.js', () => {
  assert.ok(!/getElementById\('narr-excel-btn'\)\?\.addEventListener/.test(app));
});

test('the toolbar Excel export sends the generated report, not the bare result', () => {
  const fn = api.slice(api.indexOf('export async function exportNarrativeExcel'));
  const body = fn.slice(0, fn.indexOf('export async function', 10));   // this function only
  assert.ok(/doc: state\.narrativeDoc \|\| null/.test(body));
  assert.ok(!/result: state\.currentResult/.test(body));
});

test('the Milestone Check export sends the schedule milestones held on screen', () => {
  assert.ok(/state\.currentModule === 'hard_constraints'/.test(api));
  assert.ok(/excelBody\.baseline_milestones = mc\.baseline_milestones/.test(api));
});

console.log(`\n${passed} passed`);
