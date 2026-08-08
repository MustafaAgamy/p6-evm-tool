/**
 * Unit tests for the pure helpers in ui/modules/calendar.js
 * Run: node tests/js/test_calendar.js
 */
import assert from 'node:assert/strict';
import { fmtCalDate, statusClass, monthGridCells, conflictSeverityClass }
  from '../../ui/modules/calendar.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

console.log('\nfmtCalDate');
test('formats an ISO date',        () => assert.equal(fmtCalDate('2025-01-05'), '05 Jan 2025'));
test('null -> dash',               () => assert.equal(fmtCalDate(null), '—'));
test('garbage -> dash',            () => assert.equal(fmtCalDate('not-a-date'), '—'));

console.log('\nstatusClass');
test('work',      () => assert.equal(statusClass('work'), 'cs-work'));
test('shutdown',  () => assert.equal(statusClass('shutdown'), 'cs-shutdown'));
test('unknown -> work', () => assert.equal(statusClass('???'), 'cs-work'));

console.log('\nmonthGridCells');
test('pads leading blanks by weekday', () => {
  const m = { first_weekday: 2, days: [{ d: 1, status: 'work' }, { d: 2, status: 'weekend' }] };
  const cells = monthGridCells(m);
  assert.equal(cells.length, 4);            // 2 blanks + 2 days
  assert.equal(cells[0].blank, true);
  assert.equal(cells[1].blank, true);
  assert.equal(cells[2].d, 1);
  assert.equal(cells[2].status, 'work');
});
test('no pad when weekday 0', () => {
  const cells = monthGridCells({ first_weekday: 0, days: [{ d: 1, status: 'work' }] });
  assert.equal(cells.length, 1);
  assert.equal(cells[0].d, 1);
});
test('empty days -> only blanks', () => {
  const cells = monthGridCells({ first_weekday: 3, days: [] });
  assert.equal(cells.length, 3);
  assert.ok(cells.every(c => c.blank));
});

console.log('\nconflictSeverityClass');
test('High',  () => assert.equal(conflictSeverityClass('High'), 'cf-high'));
test('Low default', () => assert.equal(conflictSeverityClass('???'), 'cf-low'));

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
