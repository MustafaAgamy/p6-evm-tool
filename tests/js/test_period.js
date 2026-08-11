/**
 * Unit tests for the pure helpers in ui/modules/period.js
 * Run: node tests/js/test_period.js
 */
import assert from 'node:assert/strict';
import { signPct, shortDate, progressBarHtml, milestoneSection, dashboardHtml } from '../../ui/modules/period.js';

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

console.log('\nprogressBarHtml (replaces the S-curve)');
test('empty message when no actuals', () => {
  assert.ok(progressBarHtml({ summary: {} }).includes('No progress'));
});
test('fill to actual, forecast marker, and the two period bars', () => {
  const h = progressBarHtml({ summary: { actual_now: 41, forecast_at_now: 43, period_earned: 7, period_forecast: 9 } });
  assert.ok(h.includes('per-pfill') && h.includes('width:41%'));           // fill to actual
  assert.ok(h.includes('per-pmark') && h.includes('forecast 43% (last update)'));  // marker
  assert.ok(h.includes('Forecast — last update') && h.includes('Actual — this update'));  // legend + bars
});

console.log('\nmilestoneSection (table + drift chart)');
test('empty message when no milestones', () => {
  assert.ok(milestoneSection({ milestones: { rows: [] } }).includes('No key milestones'));
});
test('renders the table dates and a drift svg', () => {
  const rep = { milestones: { rows: [
    { name: 'Handover', baseline_finish: '09-Feb-2027', prev_forecast: '20-Feb-2027', curr_forecast: '01-Mar-2027',
      slip_period_days: 9, slip_baseline_days: 20, baseline_iso: '2027-02-09', prev_iso: '2027-02-20', curr_iso: '2027-03-01' },
    { name: 'Mech', baseline_finish: '20-Dec-2026', prev_forecast: '20-Dec-2026', curr_forecast: '20-Dec-2026',
      slip_period_days: 0, slip_baseline_days: 0, baseline_iso: '2026-12-20', prev_iso: '2026-12-20', curr_iso: '2026-12-20' },
  ] } };
  const h = milestoneSection(rep);
  assert.ok(h.includes('Handover') && h.includes('09-Feb-2027') && h.includes('20-Feb-2027'));  // table dates
  assert.ok(h.includes('<svg') && h.includes('Previous forecast') && h.includes('Current forecast'));  // drift chart
  assert.ok(/per-slip-bad[^]*\+9 d/.test(h));                              // slippage cell
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
  test('SPI shown as whole percent (85% / 81%, no decimals)', () => {
    assert.ok(h.includes('85%') && h.includes('81%') && !h.includes('0.85'));
  });
  test('definitions block explains the metrics in plain English', () => {
    assert.ok(h.includes('What these numbers mean') && h.includes('Forecast achievement'));
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
