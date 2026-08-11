/**
 * Unit tests for the pure helpers in ui/modules/period.js
 * Run: node tests/js/test_period.js
 */
import assert from 'node:assert/strict';
import { signPct, shortDate, periodScurveSvg, milestoneTrendSvg, dashboardHtml } from '../../ui/modules/period.js';

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

console.log('\ndashboardHtml — SPI/Delay/%Complete strips + sign convention');
{
  const report = {
    data_date_prev: '30-Jun-2026', data_date_now: '31-Jul-2026',
    summary: {
      actual_prev: 34, actual_now: 41, period_earned: 7, forecast_at_now: 43,
      shortfall_pct: 2, forecast_achievement: 0.78,
      forecast_finish_prev: '12-Mar-2027', forecast_finish_now: '26-Mar-2027', finish_slip_days: 14,
      prev_spi: 0.85, curr_spi: 0.81, spi_variance: -0.04,
      delay_prev: 22, delay_now: 30, delay_change: 8,
    },
    schedule_adherence: { planned: 18, hit: 13, pct: 72.2 },
    recovery: { work_remaining: 59, current_rate: 7, projected_finish: '10-Apr-2027',
                baseline_finish: '09-Feb-2027', required_rate: 9.8, required_achievement: 1.4, feasible: false },
    critical_movement: { new_critical: 1 }, buckets: { counts: { started: 5 } },
  };
  const h = dashboardHtml(report);
  test('shows both cutoff dates', () => { assert.ok(h.includes('30-Jun-2026') && h.includes('31-Jul-2026')); });
  test('% Complete variance is good (green) when progress increased', () => {
    assert.ok(h.includes('Previous % Complete') && h.match(/per-tvar good[^]*Progressed this period/));
  });
  test('SPI down → variance cell is bad (red)', () => {
    assert.ok(h.includes('Previous SPI') && /SPI[^]*per-tvar bad[^]*SPI worsened/.test(h));
  });
  test('Delay up → variance cell is bad (red)', () => {
    assert.ok(h.includes('Previous delay') && /Delay vs baseline[^]*per-tvar bad[^]*Delay grew/.test(h));
  });
  test('Forecast finish strip shows both forecasts', () => {
    assert.ok(/Forecast finish[^]*12-Mar-2027[^]*26-Mar-2027/.test(h) && h.includes('Finish slipped'));
  });
  test('Recovery outlook renders with baseline + infeasible verdict', () => {
    assert.ok(h.includes('Recovery outlook') && h.includes('09-Feb-2027') &&
              h.includes('Projected finish ≈ 10-Apr-2027') && /per-rr-v bad/.test(h));
  });
  test('Facts row shows schedule adherence', () => {
    assert.ok(h.includes('Schedule adherence') && h.includes('72%') && h.includes('13 of 18 due finishes'));
  });
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
