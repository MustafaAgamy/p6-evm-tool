"""Tests for the EVM Special Report provider (reference provider)."""
import db
from p6_special.providers import evm
from p6_special.context import SpecialContext


def _seed(fixture):
    pid = db.upsert_project('P1', 'Grain')
    sid = db.insert_snapshot(pid, '2026-01-01', str(fixture), str(fixture), 'h', 10, 2)
    db.insert_metrics(sid, {
        'pv': 1e6, 'ev': 6e5, 'ac': 7e5, 'spi': 0.6, 'cpi': 0.857, 'delay_days': 5,
        'overall_planned_pct': 0.614, 'overall_actual_pct': 0.404, 'variance': -0.21,
    })
    db.insert_category_metrics(sid, {
        'Construction': {'weight': 0.855, 'planned_pct': 0.58, 'actual_pct': 0.38,
                         'bac': 1e6, 'ac': 7e5, 'activity_count': 50, 'overridden': False},
    })
    return pid


def _items(ctx):
    return {i.id: i for i in evm.provide(ctx)}


def test_planned_kpi_scaled_to_percent(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    pl = _items(ctx)['evm:planned_pct'].produce(ctx)
    assert pl['kind'] == 'kpi_group'
    # 2 decimals, matching the EVM screen's slicer/dashboard read-out.
    assert pl['items'][0]['value'] == '61.40%'


def test_actual_kpi(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    assert _items(ctx)['evm:actual_pct'].produce(ctx)['items'][0]['value'] == '40.40%'


def test_variance_signed_and_bad_tone(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    v = _items(ctx)['evm:variance'].produce(ctx)['items'][0]
    # 2 decimals + true minus glyph (U+2212), matching the screen.
    assert v['value'] == '−21.00%'
    assert v['tone'] == 'bad'


def test_spi_as_percent_and_tone(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    s = _items(ctx)['evm:spi'].produce(ctx)['items'][0]
    # The EVM screen shows SPI as a whole-number percentage, not a ratio.
    assert s['value'] == '60%'
    assert s['tone'] == 'bad'


def test_money_ev(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    assert _items(ctx)['evm:ev'].produce(ctx)['items'][0]['value'] == '600,000'


def test_paired_is_a_bars_payload(temp_db, xml_path):
    # Composite EVM results ship DATA (bars / table): the narrative Document renders
    # it in the house style, and the Dashboard turns the same data into a chart.
    ctx = SpecialContext(_seed(xml_path))
    b = _items(ctx)['evm:planned_vs_actual'].produce(ctx)
    assert b['kind'] == 'bars'
    assert b.get('rows')


def test_category_is_a_table_payload(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    t = _items(ctx)['evm:category_table'].produce(ctx)
    assert t['kind'] == 'table'
    assert t.get('rows') and t.get('columns')


def test_availability_ready(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    assert _items(ctx)['evm:planned_pct'].availability(ctx) == 'ready'


def test_availability_needs_run_without_data(temp_db):
    ctx = SpecialContext(9999)
    assert evm.provide(ctx)[0].availability(ctx) == 'needs_run'


def test_gap_gated_no_data_when_absent(temp_db, xml_path):
    """PV-EV gap is optional: with no stored gap it must report 'no_data', not a
    'ready' item that then renders an empty section (silent-empty regression)."""
    ctx = SpecialContext(_seed(xml_path))
    item = _items(ctx)['evm:gap']
    assert item.availability(ctx) == 'no_data'
    assert item.produce(ctx)['kind'] == 'no_data'


def test_gap_ready_and_reuses_report_section_when_present(temp_db, xml_path):
    pid = _seed(xml_path)
    sid = db.get_latest_snapshot_id(pid)
    # The REAL stored gap is a dict {dimension, total_*, groups:[{code,pv,ev,gap,pct_of_gap}]}
    # (p6_evm.gap.gap_by_code) — not a list. Seed the real shape.
    db.save_evm_extras(sid, {'gap': {
        'dimension': 'Discipline', 'total_pv': 1000.0, 'total_ev': 600.0, 'total_gap': 400.0,
        'groups': [{'code': 'CIV', 'pv': 700.0, 'ev': 400.0, 'gap': 300.0, 'pct_of_gap': 75.0},
                   {'code': 'MECH', 'pv': 300.0, 'ev': 200.0, 'gap': 100.0, 'pct_of_gap': 25.0}],
    }})
    ctx = SpecialContext(pid, snapshot_id=sid)
    item = _items(ctx)['evm:gap']
    assert item.availability(ctx) == 'ready'
    pl = item.produce(ctx)
    # Reuses the EVM Report's OWN PV-EV Gap section (exact style), not a generic table.
    assert pl['kind'] == 'html'
    assert 'Gap' in pl['html'] and 'CIV' in pl['html']


def test_gap_no_data_when_stored_shape_is_wrong(temp_db, xml_path):
    # A stray list (the old buggy shape) must NOT advertise 'ready'.
    pid = _seed(xml_path)
    sid = db.get_latest_snapshot_id(pid)
    db.save_evm_extras(sid, {'gap': [{'code': 'CIV'}]})
    ctx = SpecialContext(pid, snapshot_id=sid)
    assert _items(ctx)['evm:gap'].availability(ctx) == 'no_data'


# ── Engineering Progress (atomic add-on section) ──────────────────────────────
_E1_EXTRAS = {
    'engineering_e1': [
        {'trade': 'Civil', 'submittal_type': 'IFC', 'req': 10, 'planned': 8,
         'submitted_rows': 7, 'approved_rows': 6, 'not_approved_rows': 1,
         'under_review_rows': 0, 'planned_pct': 80, 'submitted_pct': 60, 'approved_pct': 60},
        {'trade': 'Mechanical', 'submittal_type': 'Shop', 'req': 5, 'planned': 4,
         'submitted_rows': 3, 'approved_rows': 2, 'not_approved_rows': 0,
         'under_review_rows': 1, 'planned_pct': 80, 'submitted_pct': 60, 'approved_pct': 40},
    ],
    'engineering_overall': {
        'design': {'req': 10, 'planned': 8, 'submitted_rows': 7, 'approved_rows': 6,
                   'not_approved_rows': 1, 'under_review_rows': 0,
                   'planned_pct': 80, 'submitted_pct': 60, 'approved_pct': 60},
        'engineering': {'req': 5, 'planned': 4, 'submitted_rows': 3, 'approved_rows': 2,
                        'not_approved_rows': 0, 'under_review_rows': 1,
                        'planned_pct': 80, 'submitted_pct': 60, 'approved_pct': 40},
    },
    'engineering_by_trade': [
        {'trade': 'Civil', 'req': 10, 'submitted_rows': 7, 'approved_rows': 6,
         'not_approved_rows': 1, 'submitted_pct': 60, 'approved_pct': 60},
        {'trade': 'Mechanical', 'req': 5, 'submitted_rows': 3, 'approved_rows': 2,
         'not_approved_rows': 0, 'submitted_pct': 60, 'approved_pct': 40},
    ],
    'engineering_gaps': {
        'design': [{'trade': 'Civil', 'planned': 8, 'approved': 6, 'gap': 2, 'pct_of_gap': 100.0}],
        'engineering': [{'trade': 'Mechanical', 'planned': 4, 'approved': 2, 'gap': 2, 'pct_of_gap': 100.0}],
    },
}

_P6_EXTRAS = {
    'engineering_p6': [
        {'trade': 'Civil', 'submittal_type': 'Concrete', 'req': 12, 'planned_sub': 10,
         'actual_sub': 9, 'planned_appr': 8, 'actual_appr': 6,
         'actual_sub_pct': 75, 'actual_appr_pct': 50},
    ],
}


def test_engineering_no_data_when_absent(temp_db, xml_path):
    """No E1/P6 rows stored → 'no_data' and a no_data payload (never a ready item
    that renders an empty engineering section)."""
    ctx = SpecialContext(_seed(xml_path))
    item = _items(ctx)['evm:engineering']
    assert item.availability(ctx) == 'no_data'
    assert item.produce(ctx)['kind'] == 'no_data'


def test_engineering_ready_e1_and_reuses_report_section(temp_db, xml_path):
    pid = _seed(xml_path)
    sid = db.get_latest_snapshot_id(pid)
    db.save_evm_extras(sid, dict(_E1_EXTRAS))
    ctx = SpecialContext(pid, snapshot_id=sid)
    item = _items(ctx)['evm:engineering']
    assert item.availability(ctx) == 'ready'
    pl = item.produce(ctx)
    # Reuses the EVM Report's OWN Engineering Progress section (exact style).
    assert pl['kind'] == 'html'
    h = pl['html']
    assert 'Engineering Progress' in h            # Section E heading
    assert 'Totals by Trade' in h                 # Totals-by-trade sub-table
    assert 'Engineering Gap' in h                 # Design + Shop gap tables
    assert 'Overall — Design Drawings' in h       # E1 overall rows
    assert 'Civil' in h and 'Mechanical' in h
    assert 'Source: E1 Log' in h                  # E1 (not P6) note


def test_engineering_only_the_addon_renders(temp_db, xml_path):
    """sections=['engineering'] is a sentinel that suppresses every core section, so
    the picked result is ONLY the engineering add-on — not the whole EVM report."""
    pid = _seed(xml_path)
    sid = db.get_latest_snapshot_id(pid)
    db.save_evm_extras(sid, dict(_E1_EXTRAS))
    ctx = SpecialContext(pid, snapshot_id=sid)
    h = _items(ctx)['evm:engineering'].produce(ctx)['html']
    # None of the four core-section headings leak in.
    assert 'Executive Dashboard' not in h
    assert 'Category Weights' not in h
    assert 'Planned Value vs Earned Value' not in h
    assert 'Project Progress' not in h
    # And the report banner / footer boilerplate is stripped.
    assert 'Earned Value Management · Report' not in h
    assert 'isolated from the Schedule Audit modules' not in h


def test_engineering_ready_p6_mode(temp_db, xml_path):
    pid = _seed(xml_path)
    sid = db.get_latest_snapshot_id(pid)
    db.save_evm_extras(sid, dict(_P6_EXTRAS))
    ctx = SpecialContext(pid, snapshot_id=sid)
    item = _items(ctx)['evm:engineering']
    assert item.availability(ctx) == 'ready'
    pl = item.produce(ctx)
    assert pl['kind'] == 'html'
    assert 'Engineering Progress' in pl['html']
    assert 'Source: P6' in pl['html']             # P6 (Mode B) note


def test_engineering_no_data_when_rows_empty(temp_db, xml_path):
    """An empty engineering_p6 list (the parse-time default) must NOT advertise
    'ready' — availability complements produce, which renders nothing."""
    pid = _seed(xml_path)
    sid = db.get_latest_snapshot_id(pid)
    db.save_evm_extras(sid, {'engineering_p6': [], 'engineering_e1': []})
    ctx = SpecialContext(pid, snapshot_id=sid)
    item = _items(ctx)['evm:engineering']
    assert item.availability(ctx) == 'no_data'
    assert item.produce(ctx)['kind'] == 'no_data'


# ── Finish-date KPIs (the EVM dashboard's two finish tiles, atomic) ───────────
def test_finish_dates_no_data_when_absent(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    items = _items(ctx)
    for iid in ('evm:baseline_finish', 'evm:expected_finish'):
        assert items[iid].availability(ctx) == 'no_data'
        assert items[iid].produce(ctx)['kind'] == 'no_data'


def test_finish_dates_ready_and_formatted(temp_db, xml_path):
    pid = _seed(xml_path)
    sid = db.get_latest_snapshot_id(pid)
    # Stored finish dates carry an ISO time tail; the tile drops it and formats as the
    # EVM screen does — 'DD Mon YYYY'.
    db.save_evm_extras(sid, {'baseline_finish': '2027-12-31T00:00:00',
                             'expected_finish': '2028-03-15 00:00:00'})
    ctx = SpecialContext(pid, snapshot_id=sid)
    items = _items(ctx)

    bf = items['evm:baseline_finish']
    assert bf.availability(ctx) == 'ready'
    bkpi = bf.produce(ctx)
    assert bkpi['kind'] == 'kpi_group'
    assert bkpi['items'][0]['value'] == '31 Dec 2027'
    assert bkpi['items'][0]['label'] == 'Baseline Finish'

    ef = items['evm:expected_finish']
    assert ef.availability(ctx) == 'ready'
    assert ef.produce(ctx)['items'][0]['value'] == '15 Mar 2028'


def test_finish_dates_no_data_when_only_the_other_present(temp_db, xml_path):
    pid = _seed(xml_path)
    sid = db.get_latest_snapshot_id(pid)
    db.save_evm_extras(sid, {'baseline_finish': '2027-12-31T00:00:00'})
    ctx = SpecialContext(pid, snapshot_id=sid)
    items = _items(ctx)
    assert items['evm:baseline_finish'].availability(ctx) == 'ready'
    # Expected finish absent → its own item stays honest.
    assert items['evm:expected_finish'].availability(ctx) == 'no_data'
    assert items['evm:expected_finish'].produce(ctx)['kind'] == 'no_data'
