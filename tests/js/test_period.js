/**
 * Unit tests for the pure helpers in ui/modules/period.js
 * Run: node tests/js/test_period.js
 */
import assert from 'node:assert/strict';
import { signPct, shortDate, progressBarHtml, milestoneSection, dashboardHtml,
         criticalTimelineData, criticalCompareBody } from '../../ui/modules/period.js';

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
test('3 points: start, actual fill, planned marker', () => {
  const h = progressBarHtml({ data_date_prev: '07-Aug', data_date_now: '22-Aug',
    summary: { actual_prev: 22.9, actual_now: 34.9, forecast_at_now: 44, period_earned: 12, period_forecast: 21, forecast_achievement: 0.57 } });
  assert.ok(h.includes('per-pfill') && h.includes('width:34.9%'));         // fill to exact actual
  assert.ok(h.includes('34.9%') && h.includes('planned 44.0%') && h.includes('start 22.9%'));  // 3 points, one decimal
  assert.ok(h.includes('of the whole project'));                          // explanation
});

console.log('\nmilestoneSection (table + drift chart)');
test('empty message when no overall milestone', () => {
  assert.ok(milestoneSection({ milestones: { rows: [] } }).includes('No project-completion milestone'));
});
test('renders the table dates and a drift svg', () => {
  const ov = { name: 'Handover', baseline_finish: '09-Feb-2027', prev_forecast: '20-Feb-2027', curr_forecast: '01-Mar-2027',
      slip_period_days: 9, slip_baseline_days: 20, baseline_iso: '2027-02-09', prev_iso: '2027-02-20', curr_iso: '2027-03-01' };
  const rep = { milestones: { overall: ov, rows: [ov,
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

console.log('\ncriticalTimelineData / CompareBody (connected chain — 1 row unchanged, 2 aligned rows on a reroute)');
{
  const A = (id, name, wbs, s, f) => ({ id, name, wbs_path: wbs, codes: { Discipline: 'Civil' }, start: s, finish: f });
  const prev = [A('A', 'Excavate', 'Plant > Foundations > Excavation', '2026-08-01', '2026-09-30'),
                A('B', 'Steel', 'Plant > Steel > Erection', '2026-10-01', '2026-12-15'),
                A('C', 'Cladding', 'Plant > Cladding > Panels', '2026-12-16', '2027-02-01'),
                A('D', 'Roof', 'Plant > Roof > Sheeting', '2027-02-02', '2027-03-12')];
  const curr = [A('A', 'Excavate', 'Plant > Foundations > Excavation', '2026-08-01', '2026-09-30'),
                A('B', 'Steel', 'Plant > Steel > Erection', '2026-10-01', '2026-12-15'),
                A('E', 'Furnace', 'Plant > Furnace > Melter', '2026-12-16', '2027-02-20'),
                A('F', 'Commissioning', 'Plant > Commissioning > Cold end', '2027-02-21', '2027-03-26')];
  const summary = { forecast_finish_prev: '12-Mar-2027', forecast_finish_now: '26-Mar-2027', finish_slip_days: 14 };
  const d = criticalTimelineData(prev, curr, summary, 'leaf-parent');
  test('groups to WBS leaf-parent segments', () => {
    assert.deepEqual(d.prev.map(s => s.key), ['Foundations', 'Steel', 'Cladding', 'Roof']);
    assert.deepEqual(d.curr.map(s => s.key), ['Foundations', 'Steel', 'Furnace', 'Commissioning']);
  });
  test('divergence after the shared prefix + changed flag', () => { assert.equal(d.divergence, 2); assert.equal(d.changed, true); });
  test('conclusion names the reroute, the new route and the P6 finish', () => {
    assert.ok(d.conclusion.includes('rerouted at Steel') && d.conclusion.includes('Furnace') && d.conclusion.includes('26-Mar-2027'));
  });
  const report = { critical_path: { previous: prev, current: curr }, summary,
                   data_date_prev: '07-Aug-2026', data_date_now: '22-Aug-2026' };
  const html = criticalCompareBody(report, 'leaf-parent');
  test('changed → two connected rows, new route red, both flags + slip note', () => {
    assert.ok(html.includes('cpchain'));                                   // connected chain, not an SVG
    assert.ok(html.includes('Was — last update') && html.includes('Now — this update'));
    assert.ok(html.includes('cpblk gone') && html.includes('cpblk new'));  // old greyed, new red
    assert.ok(html.includes('12-Mar-2027') && html.includes('26-Mar-2027'));
    assert.ok(html.includes('moved +14 working days'));
  });
  test('unchanged → one blue chain, no second row', () => {
    const d2 = criticalTimelineData(prev, prev, summary, 'leaf-parent');
    assert.equal(d2.divergence, d2.curr.length); assert.equal(d2.changed, false);
    assert.ok(d2.conclusion.includes('Same critical path as last period'));
    const h2 = criticalCompareBody({ critical_path: { previous: prev, current: prev }, summary }, 'leaf-parent');
    assert.ok(h2.includes("This period's critical path") && !h2.includes('Was — last update'));
    assert.ok(!h2.includes('cpblk gone') && !h2.includes('cpblk new'));
  });
  test('timeline style → SVG Gantt: WAS/NOW rows, red new route, slip bracket', () => {
    const h = criticalCompareBody(report, 'leaf-parent', 'timeline');
    assert.ok(h.includes('<svg') && h.includes('Critical path timeline') && !h.includes('cpchain'));
    assert.ok(h.includes('WAS · 07-Aug-2026') && h.includes('NOW · 22-Aug-2026'));   // data dates label rows
    assert.ok(h.includes('rerouted here') && h.includes('#f87171'));                 // divergence + new route red
    assert.ok(h.includes('finish 12-Mar-2027') && h.includes('finish 26-Mar-2027'));
    assert.ok(h.includes('+14 wd') && h.includes('rerouted at Steel'));              // slip bracket + shared conclusion
  });
  test('table style → compact Was/Now table, new tail red', () => {
    const h = criticalCompareBody(report, 'leaf-parent', 'table');
    assert.ok(h.includes('cptable') && !h.includes('<svg') && !h.includes('cpchain'));
    assert.ok(h.includes('Driving route') && h.includes('Forecast finish') && h.includes('Rerouted at'));
    assert.ok(h.includes('Foundations → Steel → Cladding → Roof'));                  // was route, plain
    assert.ok(h.includes('cpt-red') && h.includes('(+14 wd)') && h.includes('26-Mar-2027'));
    assert.ok(h.includes('rerouted at Steel'));                                      // shared conclusion
  });
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
