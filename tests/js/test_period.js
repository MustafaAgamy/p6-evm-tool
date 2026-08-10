/**
 * Unit tests for the pure helpers in ui/modules/period.js
 * Run: node tests/js/test_period.js
 */
import assert from 'node:assert/strict';
import { signPct, shortDate, periodScurveSvg, milestoneTrendSvg } from '../../ui/modules/period.js';

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}\n    ${e.message}`); failed++; }
}

console.log('\nsignPct');
test('positive gets a + sign', () => assert.equal(signPct(13), '+13.0%'));
test('negative keeps its - sign', () => assert.equal(signPct(-5), '-5.0%'));
test('null → em dash', () => assert.equal(signPct(null), '—'));

console.log('\nshortDate');
test('trims a DB timestamp to the date', () => assert.equal(shortDate('2026-06-30 00:00:00'), '2026-06-30'));
test('empty → em dash', () => assert.equal(shortDate(''), '—'));

console.log('\nperiodScurveSvg');
test('too few periods → friendly empty message', () => {
  assert.ok(periodScurveSvg({ periods: ['Jan 26'] }).includes('Not enough'));
});
test('draws both an actual and a forecast polyline', () => {
  const sc = {
    periods: ['Jun 26', 'Jul 26', 'Aug 26', 'Sep 26'],
    forecast: [34, 43, 60, 100],
    actual: [34, 41, null, null],
    dd_prev_idx: 0, dd_now_idx: 1, forecast_now: 43, actual_now: 41,
  };
  const svg = periodScurveSvg(sc);
  assert.ok(svg.includes('<svg'));
  assert.ok((svg.match(/<polyline/g) || []).length === 2);   // actual + forecast
  assert.ok(svg.includes('#f59e0b') && svg.includes('#3b82f6'));
});

console.log('\nmilestoneTrendSvg');
test('too few updates → fills-in message', () => {
  assert.ok(milestoneTrendSvg({ periods: ['2026-06-30'], series: [] }).includes('fills in'));
});
test('two rising milestones draw two polylines', () => {
  const trend = {
    periods: ['2026-06-30', '2026-07-31'],
    series: [
      { code: 'M900', name: 'Handover', task_type: 'FinishMilestone', finishes: ['2027-02-09', '2027-03-26'] },
      { code: 'M100', name: 'Mech', task_type: 'FinishMilestone', finishes: ['2026-12-20', '2026-12-20'] },
    ],
  };
  const svg = milestoneTrendSvg(trend);
  assert.ok(svg.includes('<svg'));
  assert.ok((svg.match(/<polyline/g) || []).length === 2);
  assert.ok(svg.includes('Handover') && svg.includes('Mech'));
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
