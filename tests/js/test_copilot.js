/**
 * Unit tests for the pure helpers in ui/modules/copilot_helpers.js
 * Run: node tests/js/test_copilot.js
 */
import assert from 'node:assert/strict';
import { resolveActivity } from '../../ui/modules/copilot_helpers.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

const ACTS = [
  { id: 'ACT001', name: 'Excavation' },
  { id: 'MEP-L2-001', name: 'MEP first-fix, Level 2' },
  { id: 'ACT002', name: 'Excavation' },   // same name, different id
];

test('bare Activity ID resolves (case-insensitive, trimmed)', () => {
  assert.equal(resolveActivity(ACTS, 'MEP-L2-001').name, 'MEP first-fix, Level 2');
  assert.equal(resolveActivity(ACTS, 'act001').id, 'ACT001');
  assert.equal(resolveActivity(ACTS, '  ACT002  ').id, 'ACT002');
});

test('an "ID — Name" pick from the list resolves to that exact activity', () => {
  assert.equal(resolveActivity(ACTS, 'MEP-L2-001 — MEP first-fix, Level 2').id, 'MEP-L2-001');
  // duplicate name is disambiguated by the ID in the combo
  assert.equal(resolveActivity(ACTS, 'ACT002 — Excavation').id, 'ACT002');
});

test('typing part of a name alone does NOT resolve (must pick from the list)', () => {
  assert.equal(resolveActivity(ACTS, 'Excavation'), null);
  assert.equal(resolveActivity(ACTS, 'MEP'), null);
});

test('partial / unknown / empty / null inputs return null', () => {
  assert.equal(resolveActivity(ACTS, 'ACT'), null);
  assert.equal(resolveActivity(ACTS, 'NOPE'), null);
  assert.equal(resolveActivity(ACTS, ''), null);
  assert.equal(resolveActivity(ACTS, '   '), null);
  assert.equal(resolveActivity(null, 'ACT001'), null);
});

test('tolerates activities missing a name (combo still keyed on the ID)', () => {
  const acts = [{ id: 'X1' }];
  assert.equal(resolveActivity(acts, 'X1').id, 'X1');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
