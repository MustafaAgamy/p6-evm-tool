"""Tests for the Special Report parse-free context."""
import db
from p6_special.context import SpecialContext


def _seed(fixture_xml):
    pid = db.upsert_project('P1', 'Grain Terminal')
    sid = db.insert_snapshot(pid, '2026-01-01', str(fixture_xml), str(fixture_xml),
                             'h1', 10, 2)
    db.insert_metrics(sid, {
        'pv': 100, 'ev': 60, 'ac': 70, 'spi': 0.6, 'cpi': 0.857, 'delay_days': 5,
        'overall_planned_pct': 61.4, 'overall_actual_pct': 40.4, 'variance': -40,
    })
    db.insert_category_metrics(sid, {
        'Construction': {'weight': 85.5, 'planned_pct': 58, 'actual_pct': 38,
                         'bac': 1000, 'ac': 700, 'activity_count': 50, 'overridden': False},
    })
    return pid, sid


def test_evm_read_from_db(temp_db, xml_path):
    pid, sid = _seed(xml_path)
    ctx = SpecialContext(pid)
    assert ctx.evm['overall_planned_pct'] == 61.4
    assert ctx.evm['overall_actual_pct'] == 40.4
    assert ctx.snapshot_id == sid
    assert ctx.project_name == 'Grain Terminal'
    assert 'Construction' in ctx.evm['categories']


def test_memoized(temp_db, xml_path):
    pid, _ = _seed(xml_path)
    ctx = SpecialContext(pid)
    assert ctx.evm is ctx.evm  # same object → memoized


def test_meta(temp_db, xml_path):
    pid, _ = _seed(xml_path)
    ctx = SpecialContext(pid)
    meta = ctx.meta
    assert meta['project_name'] == 'Grain Terminal'
    assert meta['data_date'] == '2026-01-01'


def test_xml_path_and_parse(temp_db, xml_path):
    pid, _ = _seed(xml_path)
    ctx = SpecialContext(pid)
    assert ctx.has_xml()
    data = ctx.parsed()
    assert data is not None
    assert ctx.parsed() is data  # memoized


def test_computed_ties_out(temp_db, xml_path):
    pid, _ = _seed(xml_path)
    ctx = SpecialContext(pid)
    result = ctx.computed()
    assert result is not None
    # Full compute result carries records + the standard EVM keys
    for key in ('pv', 'ev', 'overall_planned_pct', 'overall_actual_pct', 'records'):
        assert key in result


def test_missing_project_returns_none(temp_db):
    ctx = SpecialContext(9999)
    assert ctx.evm is None
    assert ctx.project_name == 'Project'
