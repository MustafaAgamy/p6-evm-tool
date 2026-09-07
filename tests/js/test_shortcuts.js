/**
 * Unit tests for ui/modules/shortcuts.js
 * (plus a static guard that ui/modules/help.js derives its Keyboard Shortcuts
 *  list from the registry instead of a hand-maintained array.)
 * Run: node tests/js/test_shortcuts.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SHORTCUTS, shortcutRows } from '../../ui/modules/shortcuts.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (err) {
    console.error(`  ✗ ${name}`);
    console.error(`    ${err.message}`);
    failed++;
  }
}

// ── #1 SHORTCUTS shape ──────────────────────────────────────────────────────
console.log('\nSHORTCUTS shape');

test('SHORTCUTS is an array',        () => assert.ok(Array.isArray(SHORTCUTS)));
test('SHORTCUTS is non-empty',       () => assert.ok(SHORTCUTS.length > 0));
test('every entry has string id',    () => SHORTCUTS.forEach(s => assert.equal(typeof s.id, 'string', `id on ${JSON.stringify(s)}`)));
test('every entry has string key',   () => SHORTCUTS.forEach(s => assert.equal(typeof s.key, 'string', `key on ${JSON.stringify(s)}`)));
test('every entry has boolean ctrl', () => SHORTCUTS.forEach(s => assert.equal(typeof s.ctrl, 'boolean', `ctrl on ${JSON.stringify(s)}`)));
test('every entry has non-empty string label', () => SHORTCUTS.forEach(s => {
  assert.equal(typeof s.label, 'string', `label on ${JSON.stringify(s)}`);
  assert.ok(s.label.length > 0, `empty label on ${JSON.stringify(s)}`);
}));
test('every entry has non-empty keys array of strings', () => SHORTCUTS.forEach(s => {
  assert.ok(Array.isArray(s.keys), `keys not array on ${JSON.stringify(s)}`);
  assert.ok(s.keys.length > 0, `empty keys on ${JSON.stringify(s)}`);
  s.keys.forEach(k => assert.equal(typeof k, 'string', `non-string key token on ${JSON.stringify(s)}`));
}));

// ── #2 Ctrl+E Excel export ──────────────────────────────────────────────────
console.log('\nCtrl+E excel export');

const excel = SHORTCUTS.find(s => s.key === 'e' && s.ctrl === true);
test('an entry with key "e" + ctrl exists', () => assert.ok(excel, 'no ctrl+e entry found'));
test('excel entry id is "excel"',           () => assert.equal(excel && excel.id, 'excel'));
test('excel entry keys deep-equal [Ctrl, E]', () => assert.deepEqual(excel && excel.keys, ['Ctrl', 'E']));
test('excel entry label mentions Excel',    () => assert.match(excel ? excel.label : '', /excel/i));

// ── #3 Ctrl+D cycle appearance ──────────────────────────────────────────────
console.log('\nCtrl+D cycle appearance');

const cycle = SHORTCUTS.find(s => s.key === 'd' && s.ctrl === true);
test('an entry with key "d" + ctrl exists', () => assert.ok(cycle, 'no ctrl+d entry found'));
test('cycle entry id is "cycleAppearance"', () => assert.equal(cycle && cycle.id, 'cycleAppearance'));
test('cycle entry keys deep-equal [Ctrl, D]', () => assert.deepEqual(cycle && cycle.keys, ['Ctrl', 'D']));
test('cycle entry label mentions appearance', () => assert.match(cycle ? cycle.label : '', /appearance/i));

// ── #4 shortcutRows() mirrors SHORTCUTS ─────────────────────────────────────
console.log('\nshortcutRows()');

const rows = shortcutRows();
test('shortcutRows() returns an array',       () => assert.ok(Array.isArray(rows)));
test('shortcutRows() length matches SHORTCUTS', () => assert.equal(rows.length, SHORTCUTS.length));
test('each row is [label, keys] matching its SHORTCUTS entry', () => {
  rows.forEach((row, i) => {
    const s = SHORTCUTS[i];
    assert.ok(Array.isArray(row), `row ${i} is not an array`);
    assert.equal(row.length, 2, `row ${i} is not a [label, keys] pair`);
    assert.equal(row[0], s.label, `row ${i} label mismatch`);
    assert.deepEqual(row[1], s.keys, `row ${i} keys mismatch`);
  });
});

// ── #5 No duplicate ctrl+key combos ─────────────────────────────────────────
console.log('\nunique combos');

test('every ctrl+key combo is unique', () => {
  const seen = new Map();
  SHORTCUTS.forEach(s => {
    const combo = `${s.ctrl}:${s.key}`;
    if (seen.has(combo)) {
      throw new Error(`duplicate combo "${combo}" (ids "${seen.get(combo)}" and "${s.id}")`);
    }
    seen.set(combo, s.id);
  });
});
test('Ctrl+P and Ctrl+S are distinct combos (not a collision)', () => {
  const p = SHORTCUTS.find(s => s.ctrl && s.key === 'p');
  const sSave = SHORTCUTS.find(s => s.ctrl && s.key === 's');
  assert.ok(p, 'no ctrl+p entry');
  assert.ok(sSave, 'no ctrl+s entry');
  assert.notEqual(`${p.ctrl}:${p.key}`, `${sSave.ctrl}:${sSave.key}`);
});

// ── #6 Auto-reflect guard (static source check on help.js) ──────────────────
console.log('\nhelp.js derives from registry (static guard)');

const helpSrc = fs.readFileSync(path.join(__dirname, '..', '..', 'ui', 'modules', 'help.js'), 'utf8');
test('help.js imports from ./shortcuts.js', () => {
  assert.match(helpSrc, /import[^;]*['"][^'"]*shortcuts\.js['"]/,
    'help.js does not import from ./shortcuts.js');
});
test('help.js has no hardcoded shortcut row literal', () => {
  assert.ok(!helpSrc.includes("['Ctrl', 'O']") && !helpSrc.includes("['Ctrl','O']"),
    "help.js still contains a hardcoded [Ctrl, O] shortcut row");
});

// ── Summary ─────────────────────────────────────────────────────────────────
console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
