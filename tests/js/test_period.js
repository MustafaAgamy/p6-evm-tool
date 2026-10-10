/**
 * Unit tests for the pure helpers in ui/modules/period.js
 * Run: node tests/js/test_period.js
 */
import assert from 'node:assert/strict';
import { signPct, shortDate, progressBarHtml, milestoneSection, dashboardHtml,
         criticalTimelineData, criticalCompareBody, earnedValueHtml, criticalSummaryHtml, critGroupChoice,
         watchTable, criticalTable, wrapText } from '../../ui/modules/period.js';

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
test('shows a DB timestamp as its date, 30-Jun.2026 (comment 46)', () => assert.equal(shortDate('2026-06-30 00:00:00'), '30-Jun.2026'));
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
  const ov = { name: 'Handover', baseline_finish: '09-Feb.2027', prev_forecast: '20-Feb.2027', curr_forecast: '01-Mar.2027',
      slip_period_days: 9, slip_baseline_days: 20, baseline_iso: '2027-02-09', prev_iso: '2027-02-20', curr_iso: '2027-03-01' };
  const rep = { milestones: { overall: ov, rows: [ov,
    { name: 'Mech', baseline_finish: '20-Dec.2026', prev_forecast: '20-Dec.2026', curr_forecast: '20-Dec.2026',
      slip_period_days: 0, slip_baseline_days: 0, baseline_iso: '2026-12-20', prev_iso: '2026-12-20', curr_iso: '2026-12-20' },
  ] } };
  const h = milestoneSection(rep);
  assert.ok(h.includes('Handover') && h.includes('09-Feb.2027') && h.includes('20-Feb.2027'));  // table dates
  assert.ok(h.includes('<svg') && h.includes('Previous forecast') && h.includes('Current forecast'));  // drift chart
  assert.ok(/per-slip-bad[^]*9 wd later/.test(h) && h.includes('20 wd late'));   // moved this period / against baseline
  assert.ok(h.includes('Mech') && h.includes('S/N') && h.includes('project completion'));   // every milestone listed
});
test('milestone names are wrapped in full, never cut', () => {
  const name = 'Completion of Silo Mechanical Works and Handover to Commissioning Team';
  const lines = wrapText(name, 38);
  assert.ok(lines.length >= 2 && lines.every(l => l.length <= 38));
  assert.equal(lines.join(' '), name);
});

console.log('\ndashboardHtml — SPI/Delay/%Complete strips + sign convention');
{
  const report = {
    data_date_prev: '30-Jun.2026', data_date_now: '31-Jul.2026',
    summary: {
      actual_prev: 34, actual_now: 41, period_earned: 7, forecast_at_now: 43,
      shortfall_pct: 2, forecast_achievement: 0.78,
      forecast_finish_prev: '12-Mar.2027', forecast_finish_now: '26-Mar.2027', finish_slip_days: 14,
      prev_spi: 0.85, curr_spi: 0.81, spi_variance: -0.04,
      delay_prev: 22, delay_now: 30, delay_change: 8,
    },
    schedule_adherence: { planned: 18, hit: 13, pct: 72.2 },
    recovery: { work_remaining: 59, current_rate: 7, projected_finish: '10-Apr.2027',
                baseline_finish: '09-Feb.2027', required_rate: 9.8, required_achievement: 1.4, feasible: false },
    critical_movement: { new_critical: 1 }, buckets: { counts: { started: 5 } },
  };
  const h = dashboardHtml(report);
  test('shows both cutoff dates', () => { assert.ok(h.includes('30-Jun.2026') && h.includes('31-Jul.2026')); });
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
    assert.ok(/Forecast finish[^]*12-Mar.2027[^]*26-Mar.2027/.test(h) && h.includes('Finish slipped'));
  });
  test('Recovery outlook renders with baseline + infeasible verdict', () => {
    assert.ok(h.includes('Recovery outlook') && h.includes('09-Feb.2027') &&
              h.includes('Projected finish ≈ 10-Apr.2027') && /per-rr-v bad/.test(h));
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
  const summary = { forecast_finish_prev: '12-Mar.2027', forecast_finish_now: '26-Mar.2027', finish_slip_days: 14 };
  const d = criticalTimelineData(prev, curr, summary, 'leaf-parent');
  test('groups to WBS leaf-parent segments', () => {
    assert.deepEqual(d.prev.map(s => s.key), ['Foundations', 'Steel', 'Cladding', 'Roof']);
    assert.deepEqual(d.curr.map(s => s.key), ['Foundations', 'Steel', 'Furnace', 'Commissioning']);
  });
  test('divergence after the shared prefix + changed flag', () => { assert.equal(d.divergence, 2); assert.equal(d.changed, true); });
  test('conclusion names the reroute, the new route and the P6 finish', () => {
    assert.ok(d.conclusion.includes('rerouted at Steel') && d.conclusion.includes('Furnace') && d.conclusion.includes('26-Mar.2027'));
  });
  const report = { critical_path: { previous: prev, current: curr }, summary,
                   data_date_prev: '07-Aug.2026', data_date_now: '22-Aug.2026' };
  const html = criticalCompareBody(report, 'leaf-parent');
  test('changed → two connected rows, new route red, both flags + slip note', () => {
    assert.ok(html.includes('cpchain'));                                   // connected chain, not an SVG
    assert.ok(html.includes('Was — last update') && html.includes('Now — this update'));
    assert.ok(html.includes('cpblk gone') && html.includes('cpblk new'));  // old greyed, new red
    assert.ok(html.includes('12-Mar.2027') && html.includes('26-Mar.2027'));
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
    assert.ok(h.includes('WAS · 07-Aug.2026') && h.includes('NOW · 22-Aug.2026'));   // data dates label rows
    assert.ok(h.includes('rerouted here') && h.includes('var(--danger)'));           // divergence + new route red (themed)
    assert.ok(h.includes('finish 12-Mar.2027') && h.includes('finish 26-Mar.2027'));
    assert.ok(h.includes('+14 wd') && h.includes('rerouted at Steel'));              // slip bracket + shared conclusion
  });
  test('table style → compact Was/Now table, new tail red', () => {
    const h = criticalCompareBody(report, 'leaf-parent', 'table');
    assert.ok(h.includes('cptable') && !h.includes('<svg') && !h.includes('cpchain'));
    assert.ok(h.includes('Driving route') && h.includes('Forecast finish') && h.includes('Rerouted at'));
    assert.ok(h.includes('Foundations → Steel → Cladding → Roof'));                  // was route, plain
    assert.ok(h.includes('cpt-red') && h.includes('(+14 wd)') && h.includes('26-Mar.2027'));
    assert.ok(h.includes('rerouted at Steel'));                                      // shared conclusion
  });
}

console.log('\nround 2 — Earned Value, critical summary, watch list, serials');
{
  const cost = { data_date_prev: '19-Jul.2026', data_date_now: '09-Aug.2026', summary: {
    pct_basis: 'cost', actual_prev: 40.4, actual_now: 45.7, period_earned: 5.3, period_days: 21, bac: 1000000, bac_prev: 1000000,
    cost_activities: 8, all_activities: 12, ev_prev: 404000, ev_now: 457000, ev_variance: 53000,
    pv_prev: 614000, pv_now: 712000, pv_variance: 98000, planned_prev: 61.4, planned_now: 71.2, planned_variance: 9.8,
    ev_of_pv_period: 0.54, prev_spi: 0.66, curr_spi: 0.64, spi_variance: -0.02, forecast_at_now: 46,
    forecast_finish_prev: '02-May.2027', forecast_finish_now: '22-May.2027', finish_slip_days: 20 } };
  test('Earned Value: before, after and variance, with where to find each in P6', () => {
    const h = earnedValueHtml(cost);
    assert.ok(h.includes('404,000') && h.includes('457,000') && h.includes('+53,000'));
    assert.ok(h.includes('614,000') && h.includes('712,000') && h.includes('40.4%') && h.includes('45.7%'));
    assert.ok(h.includes('8 of 12') && h.includes('Where each figure is in P6') && h.includes('worked out by the tool'));
  });
  test('no Earned Value section when the updates carry no cost', () => {
    assert.equal(earnedValueHtml({ summary: { actual_prev: 10, actual_now: 20 } }), '');
  });
  test('cost basis → the labels say Performance %; the baseline plan is marked', () => {
    assert.ok(dashboardHtml(cost).includes('Previous Performance %'));
    const h = progressBarHtml(cost);
    assert.ok(h.includes('Performance %') && h.includes('baseline plan 71.2%') && !h.includes('of the whole project'));
  });
  const cs = { total: 12, stayed: 10, new: 2, prev_total: 14, left: 4, left_finished: 3, max_slip: 9,
    bands: [{ label: 'Did not move', lo: 0, hi: 0, count: 4 }, { label: '1 – 7 days', lo: 1, hi: 7, count: 6 }, { label: '8 – 9 days', lo: 8, hi: 9, count: 2 }],
    drivers: [{ key: 'progress shortfall', label: 'Progress shortfall', count: 9 }],
    groups: { 'Main WBS': { rows: [], groups: 3, covered: 12 }, Area: { rows: [{ value: 'Berth 1', count: 7, max_slip: 9 }], groups: 2, covered: 12 },
              WBS: { rows: [{ value: 'Marine', count: 12, max_slip: 9 }], groups: 1, covered: 12 } },
    new_rows: [{ activity_id: 'N1', activity_name: 'Fender', slip_days: 5, prev_float_days: 6, float_days: 0 }] };
  test('critical movement is summarised in tiles and charts first', () => {
    const h = criticalSummaryHtml({ critical_summary: cs, summary: cost.summary });
    assert.ok(h.includes('Critical now') && h.includes('previous update: 14') && h.includes('3 finished · 1 gained float'));
    assert.ok(h.includes('per-hist') && h.includes('How to read this chart') && h.includes('Berth 1') && h.includes('Fender'));
    assert.ok(h.includes("P6's own Critical flag"));
    assert.equal(criticalSummaryHtml({ critical_summary: {} }), '');
  });
  test('group charts: a code that repeats the WBS is not the default; a pick is honoured', () => {
    assert.deepEqual(critGroupChoice(cs), ['Area', 'WBS']);
    assert.deepEqual(critGroupChoice(cs, ['Main WBS', null]), ['Main WBS', 'WBS']);
  });
  test('tables start with a serial number', () => {
    const c = criticalTable({ rows: [{ activity_id: 'CV1', activity_name: 'Quay', prev_finish: 'a', curr_finish: 'b', slip_days: 3, float_days: 0, driver: 'held', critical_status: 'stayed' }] }, []);
    assert.ok(/<th class="num">S\/N<\/th><th>Activity ID/.test(c) && c.includes('Total Float (wd)') && c.includes('+3 wd'));
    const w = watchTable({ watch_list: { rows: [{ activity_id: 'ME2', activity_name: 'Belt', due_to_start: 'z', float_days: 0, reason: 'On the critical path' }] } });
    assert.ok(w.includes('S/N') && w.includes('Why it is listed') && w.includes('most likely to delay the finish date'));
  });
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
