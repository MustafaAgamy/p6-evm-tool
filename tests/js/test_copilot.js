/**
 * Unit tests for the pure helpers in ui/modules/copilot_helpers.js
 * Run: node tests/js/test_copilot.js
 */
import assert from 'node:assert/strict';
import { matchActivity } from '../../ui/modules/copilot_helpers.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

const ACTS = [
  { id: 'ACT001', name: 'Excavation' },
  { id: 'MEP-L2-001', name: 'MEP first-fix, Level 2' },
  { id: 'ACT002', name: 'Blinding' },
];

test('exact ID match returns the activity', () => {
  assert.equal(matchActivity(ACTS, 'MEP-L2-001').name, 'MEP first-fix, Level 2');
});

test('match is case-insensitive', () => {
  assert.equal(matchActivity(ACTS, 'act001').id, 'ACT001');
  assert.equal(matchActivity(ACTS, 'Mep-L2-001').id, 'MEP-L2-001');
});

test('surrounding whitespace is trimmed', () => {
  assert.equal(matchActivity(ACTS, '  ACT002  ').id, 'ACT002');
});

test('partial ID does NOT match (exact only)', () => {
  assert.equal(matchActivity(ACTS, 'ACT'), null);
  assert.equal(matchActivity(ACTS, 'MEP-L2'), null);
});

test('empty / unknown / null inputs return null', () => {
  assert.equal(matchActivity(ACTS, ''), null);
  assert.equal(matchActivity(ACTS, '   '), null);
  assert.equal(matchActivity(ACTS, 'NOPE'), null);
  assert.equal(matchActivity(null, 'ACT001'), null);
  assert.equal(matchActivity(undefined, 'ACT001'), null);
});

test('tolerates activities with a missing id', () => {
  assert.equal(matchActivity([{ name: 'no id' }, { id: 'X', name: 'x' }], 'x').id, 'X');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
