"""Tests for the PBIP generator + structural validator."""
import json
import os

import openpyxl
import pytest

import db
import p6_powerbi
import p6_powerbi.paths as paths
from p6_powerbi.pbip import NAME, generate_pbip
from p6_powerbi.validate import validate_pbip
from p6_powerbi.schema import TABLES, columns


def _gen(tmp_path, wb_name='p6evm.xlsx'):
    wb = str(tmp_path / 'ds' / wb_name)
    out = str(tmp_path / 'dash')
    return generate_pbip(workbook_path=wb, out_dir=out), out, wb


# ── schema stays in lockstep with the written workbook ──────────────────────

def test_dataset_headers_match_schema(temp_db, tmp_path):
    from p6_powerbi.dataset import write_dataset
    pid = db.upsert_project('P1', 'Proj')
    sid = db.insert_snapshot(pid, '2026-07-31', '/p.xml', '/c.xml', 'h', 10, 1)
    db.insert_metrics(sid, {'spi': 0.9})
    db.insert_category_metrics(sid, {'Civil': {'weight': 1.0, 'planned_pct': 0.5,
        'actual_pct': 0.4, 'bac': 1, 'ac': 1, 'activity_count': 1, 'overridden': False}})
    out = tmp_path / 'p6evm.xlsx'
    write_dataset(workbook_path=str(out))
    wb = openpyxl.load_workbook(out)
    for table in TABLES:
        headers = [c.value for c in wb[table][1]]
        assert headers == columns(table), f'{table} headers drifted from schema'


# ── PBIP structure ──────────────────────────────────────────────────────────

def test_generate_pbip_creates_required_files(tmp_path):
    pbip, out, _ = _gen(tmp_path)
    assert pbip.endswith(f'{NAME}.pbip') and os.path.exists(pbip)
    required = [
        f'{NAME}.SemanticModel/definition.pbism',
        f'{NAME}.SemanticModel/model.bim',
        f'{NAME}.Report/definition.pbir',
        f'{NAME}.Report/definition/report.json',
        f'{NAME}.Report/definition/version.json',
        f'{NAME}.Report/definition/pages/pages.json',
        f'{NAME}.Report/definition/pages/page_evm/page.json',
        f'{NAME}.Report/definition/pages/page_trends/page.json',
        f'{NAME}.Report/definition/pages/page_evm/visuals/evm_card_spi/visual.json',
    ]
    for rel in required:
        assert os.path.exists(os.path.join(out, *rel.split('/'))), f'missing {rel}'


def test_pbip_bakes_absolute_workbook_path(tmp_path):
    _, out, wb = _gen(tmp_path)
    model = json.load(open(os.path.join(out, f'{NAME}.SemanticModel', 'model.bim'), encoding='utf-8'))
    exprs = [t['partitions'][0]['source']['expression'] for t in model['model']['tables']]
    assert all('Excel.Workbook' in e for e in exprs)
    assert any(os.path.abspath(wb) in e for e in exprs)


def test_model_has_measures_and_relationships(tmp_path):
    _, out, _ = _gen(tmp_path)
    model = json.load(open(os.path.join(out, f'{NAME}.SemanticModel', 'model.bim'), encoding='utf-8'))
    tables = {t['name']: t for t in model['model']['tables']}
    assert len(tables['fact_metrics'].get('measures', [])) >= 5
    assert len(model['model']['relationships']) == 2
    # time-intelligence auto date tables disabled (keeps the model simple/robust)
    anns = {a['name']: a['value'] for a in model['model'].get('annotations', [])}
    assert anns.get('__PBI_TimeIntelligenceEnabled') == '0'


# ── validation ──────────────────────────────────────────────────────────────

def test_validate_clean_on_generated(tmp_path):
    pbip, _, _ = _gen(tmp_path)
    assert validate_pbip(pbip) == []


def test_validate_catches_bad_field_reference(tmp_path):
    pbip, out, _ = _gen(tmp_path)
    vpath = os.path.join(out, f'{NAME}.Report', 'definition', 'pages',
                         'page_evm', 'visuals', 'evm_card_spi', 'visual.json')
    v = json.load(open(vpath, encoding='utf-8'))
    v['visual']['query']['queryState']['Values']['projections'][0]['field']['Measure']['Property'] = 'no_such_field'
    json.dump(v, open(vpath, 'w', encoding='utf-8'))
    errors = validate_pbip(pbip)
    assert any('no_such_field' in e or 'no field' in e for e in errors)


def test_validate_catches_missing_file(tmp_path):
    pbip, out, _ = _gen(tmp_path)
    os.remove(os.path.join(out, f'{NAME}.SemanticModel', 'model.bim'))
    errors = validate_pbip(pbip)
    assert any('model.bim' in e for e in errors)


# ── build_all end-to-end ────────────────────────────────────────────────────

def test_build_all_clean(temp_db, tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'app_data_dir', lambda: str(tmp_path))
    pid = db.upsert_project('P1', 'Grain Terminal')
    sid = db.insert_snapshot(pid, '2026-07-31', '/p.xml', '/c.xml', 'h', 10, 1)
    db.insert_metrics(sid, {'pv': 1000, 'ev': 900, 'ac': 950, 'spi': 0.9, 'cpi': 0.95,
                            'delay_days': 12, 'overall_planned_pct': 0.6,
                            'overall_actual_pct': 0.54, 'variance': -100})
    db.insert_category_metrics(sid, {'Civil': {'weight': 1.0, 'planned_pct': 0.5,
        'actual_pct': 0.4, 'bac': 1, 'ac': 1, 'activity_count': 1, 'overridden': False}})

    result = p6_powerbi.build_all()
    assert result['errors'] == []
    assert os.path.exists(result['pbip'])
    assert os.path.exists(result['dataset'])
