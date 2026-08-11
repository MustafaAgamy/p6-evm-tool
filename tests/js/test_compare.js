/**
 * Unit tests for the pure helpers in ui/modules/compare.js
 * Run: node tests/js/test_compare.js
 */
import assert from 'node:assert/strict';
import { fmtLag, statusClass, summaryPills, signedDays, suggestedCorrectedName, durImpactLabel, changedBreakdown, changeTypeBars, slipInfo, donutSegments } from '../../ui/modules/compare.js';

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

console.log('\nsuggestedCorrectedName');
test('swaps the extension for _but-for.xml', () =>
  assert.equal(suggestedCorrectedName('Metro_Update_Feb.xml'), 'Metro_Update_Feb_but-for.xml'));
test('works from an .xer name', () =>
  assert.equal(suggestedCorrectedName('sched.XER'), 'sched_but-for.xml'));
test('falls back when empty', () =>
  assert.equal(suggestedCorrectedName(''), 'update_but-for.xml'));

console.log('\ndurImpactLabel');
test('Direct', () => assert.equal(durImpactLabel('Direct'), 'Direct'));
test('None → Float absorbs', () => assert.equal(durImpactLabel('None'), 'Float absorbs'));
test('Unknown → dash', () => assert.equal(durImpactLabel('Unknown'), '—'));

console.log('\nchangedBreakdown');
test('reads total, logic and duration-only from the dashboard', () => {
  const b = changedBreakdown({ changed_activities: 2403, logic_changed: 1981, duration_only: 422 });
  assert.deepEqual(b, { total: 2403, logic: 1981, duration: 422 });
});
test('logic + duration reconcile to the total', () => {
  const b = changedBreakdown({ changed_activities: 2403, logic_changed: 1981, duration_only: 422 });
  assert.equal(b.logic + b.duration, b.total);
});
test('defaults every field to 0 when missing', () =>
  assert.deepEqual(changedBreakdown({}), { total: 0, logic: 0, duration: 0 }));
test('tolerates a null dashboard', () =>
  assert.deepEqual(changedBreakdown(null), { total: 0, logic: 0, duration: 0 }));

console.log('\nchangeTypeBars');
test('keeps only logic items, sorted desc, pct vs the largest', () => {
  const bars = changeTypeBars([
    { kind: 'lag', label: 'driving lag changed', count: 15, group: 'logic' },
    { kind: 'added_driver', label: 'driving predecessor added', count: 762, group: 'logic' },
    { kind: 'extended', label: 'duration extended', count: 400, group: 'duration' },
  ]);
  assert.equal(bars.length, 2);                 // duration item dropped
  assert.equal(bars[0].count, 762);             // biggest first
  assert.equal(bars[0].pct, 100);
  assert.equal(bars[1].pct, 2);                 // 15/762 → 2%
});
test('drops zero-count logic items', () =>
  assert.deepEqual(changeTypeBars([{ kind: 'lag', label: 'x', count: 0, group: 'logic' }]), []));
test('empty when no logic items', () =>
  assert.deepEqual(changeTypeBars([{ kind: 'extended', count: 5, group: 'duration' }]), []));
test('tolerates null', () => assert.deepEqual(changeTypeBars(null), []));

console.log('\nslipInfo');
test('positive = later', () => assert.deepEqual(slipInfo(66), { value: 66, word: 'days later', dir: 'late' }));
test('one day later is singular', () => assert.equal(slipInfo(1).word, 'day later'));
test('negative = earlier', () => assert.deepEqual(slipInfo(-5), { value: 5, word: 'days earlier', dir: 'early' }));
test('zero = on time', () => assert.equal(slipInfo(0).dir, 'ontime'));
test('null tolerated', () => assert.equal(slipInfo(null).value, null));

console.log('\ndonutSegments');
test('fractions reconcile to 1', () => {
  const d = donutSegments(1981, 422);
  assert.ok(Math.abs(d.logicFrac + d.durationFrac - 1) < 1e-9);
  assert.ok(d.logicFrac > d.durationFrac);
});
test('zero total → zero fractions', () => assert.deepEqual(donutSegments(0, 0), { logicFrac: 0, durationFrac: 0 }));
test('tolerates negatives', () => assert.deepEqual(donutSegments(-5, 0), { logicFrac: 0, durationFrac: 0 }));

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
