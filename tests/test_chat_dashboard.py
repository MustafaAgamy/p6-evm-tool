"""Contract + invariant tests for the in-chat professional dashboard (p6_chat.dashboard).

Reuses the same schedule-building + parse/compute helpers the Update-Analysis tests use
(``tests.test_update_analysis._xml`` / ``_parse_and_compute``) — a real parsed ScheduleData
plus a genuine ``metrics.compute()`` result carrying a baseline, cost loading and activity
codes — so the dashboard is exercised end-to-end on grounded numbers. Assertions check the
payload's SHAPE and its INVARIANTS (types, key set, 6 KPIs, monotone S-curve, gap rows that
sum to their total, 0-weight disciplines dropped), never the fixture's specific values.
"""
import copy

import pytest

from tests.test_update_analysis import _xml, _parse_and_compute
from p6_chat import dashboard


@pytest.fixture(scope='module')
def data_metrics():
    """A cost-loaded, baselined, activity-coded update parsed the way the app parses it."""
    xml = _xml('2025-07-02', [
        (10, 'A1', 'Piling done', 1.00, '2025-01-01', '2025-06-30', 120, 100, {'Discipline': 'Civil'}),
        (11, 'A2', 'Civil mid',   0.40, '2025-03-01', '2025-09-30', 160, 100, {'Discipline': 'Civil'}),
        (12, 'A3', 'Mech late',   0.00, '2025-08-01', '2025-12-31', 200, 100, {'Discipline': 'Mechanical'}),
        (13, 'A4', 'Elec run',    0.20, '2025-05-01', '2025-11-30', 140, 100, {'Discipline': 'Electrical'}),
    ])
    return _parse_and_compute(xml)


@pytest.fixture(scope='module')
def dash(data_metrics):
    data, metrics = data_metrics
    return dashboard.build(data, metrics)


def _non_decreasing(seq):
    vals = [v for v in seq if v is not None]
    return all(b >= a - 1e-6 for a, b in zip(vals, vals[1:]))


# ── top-level contract ───────────────────────────────────────────────────────

def test_contract_keys_and_types(dash):
    assert dash['ok'] is True
    for key in ('meta', 'health', 'kpis', 'gauges', 'time_status',
                'disciplines', 'gap_by_code', 'scurve'):
        assert key in dash, key
    assert isinstance(dash['meta'], dict)
    assert isinstance(dash['health'], dict)
    assert isinstance(dash['kpis'], list)
    assert isinstance(dash['gauges'], list)
    assert isinstance(dash['time_status'], dict)
    assert isinstance(dash['disciplines'], list)
    assert isinstance(dash['gap_by_code'], dict)
    assert isinstance(dash['scurve'], dict)


def test_meta_shape(dash):
    m = dash['meta']
    for k in ('project', 'data_date', 'baseline_finish', 'forecast_finish', 'cost_loaded', 'bac_m'):
        assert k in m, k
    assert isinstance(m['project'], str)
    assert isinstance(m['cost_loaded'], bool)
    assert isinstance(m['bac_m'], float)
    assert m['cost_loaded'] is True                      # fixture is cost-loaded
    assert m['baseline_finish'] is None or isinstance(m['baseline_finish'], str)
    assert m['forecast_finish'] is None or isinstance(m['forecast_finish'], str)


def test_health_shape(dash):
    h = dash['health']
    assert h['verdict'] in ('BEHIND', 'ON TRACK', 'AHEAD')
    assert h['tone'] in ('bad', 'warn', 'good')
    assert h['spi'] is None or isinstance(h['spi'], float)
    assert isinstance(h['message'], str) and h['message']
    assert isinstance(h['schedule_variance_m'], float)


def test_kpis_exactly_six_in_order(dash):
    kpis = dash['kpis']
    assert len(kpis) == 6
    assert [k['k'] for k in kpis] == [
        'SPI', 'CPI', '% complete', 'Delay', 'Earned value', 'Planned value']
    for k in kpis:
        assert set(k) == {'k', 'v', 'h', 't'}
        assert isinstance(k['v'], str) and k['v']
        assert isinstance(k['h'], str)
        assert k['t'] in ('', 'good', 'warn', 'bad')
    # the % complete value reads as a percentage
    assert dash['kpis'][2]['v'].endswith('%')
    # money KPIs read in £M
    assert dash['kpis'][4]['v'].startswith('£') and dash['kpis'][4]['v'].endswith('M')
    assert dash['kpis'][5]['v'].startswith('£') and dash['kpis'][5]['v'].endswith('M')


def test_gauges_spi_and_cpi(dash):
    g = dash['gauges']
    assert [x['label'] for x in g] == ['SPI', 'CPI']
    for x in g:
        assert x['value'] is None or isinstance(x['value'], float)
        assert x['tone'] in ('', 'good', 'warn', 'bad')


def test_time_status_shape(dash):
    ts = dash['time_status']
    for k in ('elapsed_pct', 'earned_pct', 'start', 'finish', 'exceeded_days'):
        assert k in ts, k
    assert ts['elapsed_pct'] is None or isinstance(ts['elapsed_pct'], float)
    assert ts['earned_pct'] is None or isinstance(ts['earned_pct'], float)


# ── disciplines ──────────────────────────────────────────────────────────────

def test_disciplines_shape_and_percent_scale(dash):
    ds = dash['disciplines']
    assert isinstance(ds, list) and len(ds) <= 8
    for d in ds:
        assert set(d) == {'name', 'planned', 'actual'}
        assert isinstance(d['name'], str)
        assert isinstance(d['planned'], float) and isinstance(d['actual'], float)
        # percentages, not fractions
        assert 0.0 <= d['planned'] <= 100.0
        assert 0.0 <= d['actual'] <= 100.0


def test_disciplines_drop_zero_weight_rows(data_metrics):
    """A 0-weight structural category (Milestones / Key Dates / Summary) must not appear."""
    data, metrics = data_metrics
    m2 = copy.deepcopy(metrics)
    m2['categories']['Milestones'] = {
        'weight': 0.0, 'planned_pct': 0.0, 'actual_pct': 0.0,
        'bac': 0.0, 'ac': 0.0, 'activity_count': 3, 'overridden': False,
    }
    out = dashboard.build(data, m2)
    names = [d['name'] for d in out['disciplines']]
    assert 'Milestones' not in names
    # the real, non-zero-weight categories survive
    real = [n for n, c in metrics['categories'].items() if (c.get('weight') or 0) > 0]
    for n in real:
        assert n in names


# ── gap by code ──────────────────────────────────────────────────────────────

def test_gap_rows_sum_to_total(dash):
    gap = dash['gap_by_code']
    assert set(gap) == {'total_m', 'label', 'rows'}
    assert isinstance(gap['label'], str)
    assert isinstance(gap['total_m'], float)
    assert isinstance(gap['rows'], list)
    assert len(gap['rows']) <= 9                          # 8 + a possible folded 'Other'
    for r in gap['rows']:
        assert set(r) == {'code', 'gap_m'}
        assert isinstance(r['gap_m'], float)
    # rows reconcile to the reported total (± rounding)
    assert gap['rows'], 'fixture carries cost + activity codes → expect gap rows'
    assert abs(sum(r['gap_m'] for r in gap['rows']) - gap['total_m']) < 1e-3
    # sorted by |gap| descending
    mags = [abs(r['gap_m']) for r in gap['rows'] if r['code'] != 'Other']
    assert mags == sorted(mags, reverse=True)


# ── S-curve ──────────────────────────────────────────────────────────────────

def test_scurve_grounded_and_monotone(dash, data_metrics):
    sc = dash['scurve']
    for k in ('months', 'plan', 'earn', 'fore', 'dd_index', 'bac_m'):
        assert k in sc, k
    n = len(sc['months'])
    assert n >= 2
    assert len(sc['plan']) == n and len(sc['earn']) == n and len(sc['fore']) == n
    assert isinstance(sc['dd_index'], int) and 0 <= sc['dd_index'] < n
    assert isinstance(sc['bac_m'], float)

    # planned curve: non-decreasing (ignoring nulls) and reaches ~100 at the finish
    assert _non_decreasing(sc['plan'])
    plan_vals = [v for v in sc['plan'] if v is not None]
    assert plan_vals and abs(plan_vals[-1] - 100.0) <= 1.5

    # earned curve: non-decreasing, stops at the data-date month, ends near the real EV/BAC
    assert _non_decreasing(sc['earn'])
    assert sc['earn'][sc['dd_index']] is not None
    assert all(v is None for v in sc['earn'][sc['dd_index'] + 1:])
    earned_at_dd = sc['earn'][sc['dd_index']]
    # ties to the EV-based earned % that Time Status reports (both are EV/BAC-grounded)
    assert abs(earned_at_dd - dash['time_status']['earned_pct']) <= 1.0

    # forecast curve: begins at the data date where 'earn' stops, climbs to 100
    assert all(v is None for v in sc['fore'][:sc['dd_index']])
    assert sc['fore'][sc['dd_index']] is not None
    fore_vals = [v for v in sc['fore'] if v is not None]
    assert _non_decreasing(fore_vals)
    assert abs(fore_vals[-1] - 100.0) <= 1.0


# ── build_from_snapshot guards ───────────────────────────────────────────────

def test_build_from_snapshot_no_args_is_guarded():
    out = dashboard.build_from_snapshot()
    assert out['ok'] is False and isinstance(out['error'], str)


def test_build_from_snapshot_bad_path_is_guarded():
    out = dashboard.build_from_snapshot(xml_path='/no/such/file/really.xml')
    assert out['ok'] is False and isinstance(out['error'], str)
