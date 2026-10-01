/**
 * Productivity & Resources — the settings change the rate (owner comment 37).
 * The planner types HIS factor beside Project type / Location / Methodology; it is validated,
 * remembered per choice, and sent with the query. Controlyx supplies no factor of its own.
 * Run: node tests/js/test_prodintel_factors.js
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const store = {};
globalThis.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
globalThis.document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], addEventListener: () => {} };
globalThis.window = globalThis.window || {};

const P = await import('../../ui/modules/prodintel.js');
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'ui', 'modules', 'prodintel.js'), 'utf8');

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (err) { console.error(`  ✗ ${name}`); console.error(`    ${err.message}`); failed++; }
}

console.log('\nProductivity — your factor per setting');
test('a factor is a number between 0.2 and 5; blank means the library norm', () => {
  assert.deepEqual(P.parseFactor(''), { value: null, error: '' });
  assert.deepEqual(P.parseFactor(' 1.2 '), { value: 1.2, error: '' });
  assert.deepEqual(P.parseFactor('0,85'), { value: 0.85, error: '' });           // decimal comma
  assert.equal(P.parseFactor('abc').value, null);
  assert.match(P.parseFactor('abc').error, /Type a number/);
  assert.equal(P.parseFactor('9').value, null);
  assert.match(P.parseFactor('9').error, /between 0\.2 and 5/);
  assert.equal(P.parseFactor('0.1').value, null);
});
test('the factor belongs to the CHOICE: changing country changes the factor sent', () => {
  const factors = { Location: { KSA: 1.15 }, Methodology: { 'Jump-form': 0.8 } };
  const ksa = P.contextWithFactors({ 'Project type': 'Industrial', Location: 'KSA', Methodology: 'Jump-form' }, factors);
  assert.deepEqual(ksa.factors, { Location: 1.15, Methodology: 0.8 });
  const egy = P.contextWithFactors({ 'Project type': 'Industrial', Location: 'Egypt', Methodology: 'Conventional' }, factors);
  assert.deepEqual(egy.factors, {});                                             // nothing typed → nothing sent
  assert.equal(egy.Location, 'Egypt');
  assert.equal(P.factorFor(factors, 'Location', 'KSA'), 1.15);
  assert.equal(P.factorFor(factors, 'Location', 'GCC'), null);
  assert.equal(P.factorFor({ Location: { KSA: 'x' } }, 'Location', 'KSA'), null); // a damaged saved value is ignored
});
test('all three settings carry a factor box and every query / Excel sends the factors', () => {
  assert.deepEqual(P.FACTOR_DIMS, ['Project type', 'Location', 'Methodology']);
  for (const d of ['Project type', 'Location', 'Methodology']) assert.ok(src.includes(`fbox('${d}')`), d);
  assert.ok(src.includes("api('/api/prodintel/query', { item_id: id, context: queryCtx(),"));
  assert.ok(src.includes("api('/api/prodintel/excel', { item_id: _itemId, context: queryCtx(),"));
  assert.ok(src.includes("localStorage.setItem(FACTOR_KEY"));
});
test('the screen says what each setting did, and never claims a factor of its own', () => {
  assert.ok(src.includes('no factor, library norm'));
  assert.ok(src.includes('Rates = library norm ×'));
  assert.ok(src.includes('Library norm ${base} · your factors ×${r.factor} applied'));
  assert.ok(src.includes('is not normally part of'));
  assert.ok(src.includes('Controlyx never guesses a multiplier'));
  assert.ok(!/\balert\(/.test(src) && !/\bconfirm\(/.test(src));                 // no-ops in the desktop window
});

console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
