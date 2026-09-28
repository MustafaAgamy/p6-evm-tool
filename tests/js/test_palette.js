/**
 * Unit tests for ui/modules/palette.js (Ctrl+K command palette) — the pure list builder,
 * ranking and arrow-key movement. The DOM part is exercised by the live Playwright check.
 * Run: node tests/js/test_palette.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildPaletteItems, filterPaletteItems, movePaletteIndex } from '../../ui/modules/palette.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appSrc = fs.readFileSync(path.join(__dirname, '..', '..', 'ui', 'app.js'), 'utf8');

let passed = 0;
let failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (err) { console.error(`  ✗ ${name}`); console.error(`    ${err.message}`); failed++; }
}

const NAV = [
  { node: { id: 'home', label: 'Import a schedule', icon: 'home' } },
  { group: 'Progress & Performance', items: [['evm', 'Earned Value'], ['update', 'Update Analysis']] },
  { group: 'Compare & Claims', items: [['revcompare', 'Baseline Revision', 'revcompare']] },
  { group: 'Library', items: [['recent', 'Recent Projects']] },
];
const MENUS = {
  file: [['Import XML / XER…', 'import'], ['sep'], ['Export to Excel…', 'export-excel'], ['Export to Word…', 'export-word'], ['Recent projects', 'recent']],
  help: [['Keyboard shortcuts', 'help-keys']],
};
const items = buildPaletteItems({ nav: NAV, menus: MENUS, extraFeatures: [{ id: 'chat', label: 'AI Chat', group: 'Menu bar' }] });

console.log('\nbuildPaletteItems');
test('features first (navigator order + extras), then commands', () => {
  assert.deepEqual(items.filter(i => i.kind === 'feature').map(i => i.id), ['home', 'evm', 'update', 'revcompare', 'recent', 'chat']);
  // File ▸ "Recent projects" (cmd 'recent') opens the Recent Projects FEATURE — listed once, as the feature.
  assert.deepEqual(items.filter(i => i.kind === 'command').map(i => i.cmd), ['import', 'export-excel', 'export-word', 'help-keys']);
  const firstCmd = items.findIndex(i => i.kind === 'command');
  assert.ok(items.slice(firstCmd).every(i => i.kind === 'command'));
});
test('separators are skipped and the trailing "…" is trimmed', () => {
  assert.ok(!items.some(i => i.label === 'sep'));
  assert.equal(items.find(i => i.cmd === 'import').label, 'Import XML / XER');
});
test('feature rows carry the group and the "Needs:" line from FEATURE_NEEDS', () => {
  const rc = items.find(i => i.id === 'revcompare');
  assert.match(rc.sub, /^Compare & Claims · Needs: 2 baselines/);
});
test('key hints come from the SHORTCUTS registry', () => {
  assert.equal(items.find(i => i.id === 'evm').keys, 'Alt+1');
  assert.equal(items.find(i => i.cmd === 'export-excel').keys, 'Ctrl+E');
  assert.equal(items.find(i => i.cmd === 'export-word').keys, 'Ctrl+Shift+W');
  assert.equal(items.find(i => i.cmd === 'import').keys, 'Ctrl+O');
  assert.equal(items.find(i => i.id === 'update').keys, 'Alt+3');
});
test('command rows name their menu', () => assert.equal(items.find(i => i.cmd === 'help-keys').sub, 'Help'));
test('duplicate ids / commands appear once', () => {
  const again = buildPaletteItems({ nav: [...NAV, ...NAV], menus: { ...MENUS, view: [['Import XML / XER…', 'import']] } });
  assert.equal(again.filter(i => i.id === 'evm').length, 1);
  assert.equal(again.filter(i => i.cmd === 'import').length, 1);
});

console.log('\nfilterPaletteItems');
test('blank query keeps the whole list', () => assert.equal(filterPaletteItems(items, '  ').length, items.length));
test('prefix of the label ranks first', () => assert.equal(filterPaletteItems(items, 'earn')[0].id, 'evm'));
test('word-start match ("rev" → Baseline Revision)', () => assert.equal(filterPaletteItems(items, 'rev')[0].id, 'revcompare'));
test('matches the Needs line too ("rev.00")', () => assert.ok(filterPaletteItems(items, 'rev.00').some(i => i.id === 'revcompare')));
test('every word must match', () => {
  assert.deepEqual(filterPaletteItems(items, 'export word').map(i => i.cmd), ['export-word']);
  assert.deepEqual(filterPaletteItems(items, 'zz top'), []);
});
test('a menu command that opens a navigator feature is listed once, as the feature ("recent")', () => {
  const r = filterPaletteItems(items, 'recent');
  assert.equal(r.length, 1);
  assert.equal(r[0].kind, 'feature');
  assert.equal(r[0].id, 'recent');
});
test('a feature beats a command on the same words', () => {
  const r = filterPaletteItems(buildPaletteItems({ nav: NAV, menus: { file: [['Earned Value summary', 'evm-sum']] } }), 'earned');
  assert.deepEqual(r.map(i => i.kind), ['feature', 'command']);
});

// ── The REAL navigator + menus (parsed out of ui/app.js) — SHELL-6 ──────────
console.log('\nreal app.js lists');
const lit = (re) => { const m = appSrc.match(re); assert.ok(m, `not found: ${re}`); return m[1]; };
const REAL_NAV = new Function(`return ${lit(/const NAV = (\[[\s\S]*?\n  \]);/)};`)();
const REAL_MENUS = new Function('window', `return ${lit(/const MENUS = (\{[\s\S]*?\n  \});/)};`)({ __APP_NAME__: 'Controlyx' });
const real = buildPaletteItems({ nav: REAL_NAV, menus: REAL_MENUS, extraFeatures: [{ id: 'chat', label: 'AI Chat', group: 'Menu bar' }] });
test('parsed the real lists', () => {
  assert.ok(real.filter(i => i.kind === 'feature').length >= 22);
  assert.ok(real.filter(i => i.kind === 'command').length >= 15);
});
test('no label appears twice in the real palette (case-insensitive)', () => {
  const seen = new Map();
  const dups = [];
  for (const i of real) {
    const k = i.label.toLowerCase();
    if (seen.has(k)) dups.push(`${i.label} (${seen.get(k)} + ${i.kind})`); else seen.set(k, i.kind);
  }
  assert.deepEqual(dups, []);
});
test('no command merely re-opens a navigator feature (kb / prodintel / recent)', () => {
  const featureIds = new Set(real.filter(i => i.kind === 'feature').map(i => i.id));
  const dup = real.filter(i => i.kind === 'command' && featureIds.has(i.cmd)).map(i => i.cmd);
  assert.deepEqual(dup, []);
  for (const id of ['kb', 'prodintel', 'recent']) assert.equal(real.filter(i => i.id === id || i.cmd === id).length, 1, id);
});
test('case-insensitive', () => assert.equal(filterPaletteItems(items, 'EARNED')[0].id, 'evm'));

console.log('\nmovePaletteIndex');
test('down / up wrap round', () => {
  assert.equal(movePaletteIndex(0, 1, 3), 1);
  assert.equal(movePaletteIndex(2, 1, 3), 0);
  assert.equal(movePaletteIndex(0, -1, 3), 2);
});
test('from "nothing selected": down → first, up → last', () => {
  assert.equal(movePaletteIndex(-1, 1, 4), 0);
  assert.equal(movePaletteIndex(-1, -1, 4), 3);
});
test('empty list → -1', () => assert.equal(movePaletteIndex(0, 1, 0), -1));

console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
