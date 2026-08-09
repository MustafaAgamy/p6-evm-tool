/**
 * Unit tests for the pure helpers in ui/modules/compare.js
 * Run: node tests/js/test_compare.js
 */
import assert from 'node:assert/strict';
import { fmtLag, statusClass, summaryPills, signedDays } from '../../ui/modules/compare.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

console.log('\nfmtLag');
test('FS with zero lag drops the +0', () => assert.equal(fmtLag('FS', 0), 'FS'));
test('positive lag', () => assert.equal(fmtLag('FS', 10), 'FS+10'));
test('negative lag rounds and uses -', () => assert.equal(fmtLag('SS', -1.6), 'SS-2'));
test('missing type defaults to FS', () => assert.equal(fmtLag(undefined, 0), 'FS'));

console.log('\nstatusClass');
test('added', () => assert.equal(statusClass('added'), 'cmp-add'));
test('removed', () => assert.equal(statusClass('removed'), 'cmp-rem'));
test('changed', () => assert.equal(statusClass('changed'), 'cmp-chg'));
test('same → no class', () => assert.equal(statusClass('same'), ''));

console.log('\nsummaryPills');
test('empty shows a no-changes message', () => assert.ok(summaryPills([]).includes('No logic')));
test('renders count and label', () => {
  const h = summaryPills([{ kind: 'lag', label: 'driving lag changed', count: 2 }]);
  assert.ok(h.includes('2'));
  assert.ok(h.includes('driving lag changed'));
});

console.log('\nsignedDays');
test('positive', () => assert.equal(signedDays(3), '+3 d'));
test('negative uses the minus glyph', () => assert.equal(signedDays(-2), '−2 d'));
test('zero', () => assert.equal(signedDays(0), '0 d'));

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
