"""Routes for the format-agnostic engineering-log reader:
POST /api/e1/inspect  → layout proposal + preview (nothing saved)
POST /api/e1/preview  → re-count with the planner's edited layout
POST /api/e1/upload   → optional confirmed 'layouts' (per file); the layout is remembered
POST /api/e1/ai-suggest → offline-AI second opinion, refused cleanly when no brain.

Every workbook is synthetic (openpyxl, built here); expected counts are worked by hand.
"""
import http.client
import json
import os
from datetime import datetime

import openpyxl
import pytest


def _post(port, path, payload):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
    conn.request('POST', path, body=json.dumps(payload).encode(),
                 headers={'Content-Type': 'application/json'})
    resp = conn.getresponse()
    return resp.status, json.loads(resp.read())


def _shop_log(path):
    """Row-7 headings under a code legend; two 'Type' columns; a 'TYPE' discipline column;
    revisions keyed by Drawings No. Hand count, Civil / SD: 4 drawings —
    D-1 C→B approved, D-2 B, D-3 C (not approved), D-4 W (under review)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Civil'
    ws.append(['Project Name: TEST', None, None, None, None, None, None, None, None, None,
               'Approved ( A )', 'Approved as Noted ( B )', 'Revise & Resubmit ( C )', 'Pending ( W )'])
    for _ in range(5):
        ws.append(['banner'])
    ws.append(['Ser.', 'Transmittal No.', 'Rev.', 'Sent Date', 'Type', 'Title', 'Type',
               'Drawings No', 'Received Date', 'Action', 'TYPE'])
    d = datetime(2025, 4, 1)
    for r in [[1, 'T-1', 0, d, 'RFT', 'Raft', 'SD', 'D-1', d, 'C', 'Civil'],
              [2, 'T-1 Rev.01', 1, d, 'RFT', 'Raft', 'SD', 'D-1', d, 'B', 'Civil'],
              [3, 'T-2', 0, d, 'RFT', 'Walls', 'SD', 'D-2', d, 'B', 'Civil'],
              [4, 'T-3', 0, d, 'Concrete Dimension', 'Slab', 'SD', 'D-3', d, 'C', 'Civil'],
              [5, 'T-4', 0, d, 'RFT', 'Roof', 'SD', 'D-4', None, 'W', 'Civil']]:
        ws.append(r)
    wb.save(path)


@pytest.fixture
def shop_log(tmp_path):
    p = tmp_path / 'Shop_Log.xlsx'
    _shop_log(p)
    return str(p)


def _civil(sheets):
    return next(s for s in sheets if s['sheet'] == 'Civil')


def test_inspect_proposes_a_layout_and_saves_nothing(test_server, shop_log, tmp_path):
    status, data = _post(test_server, '/api/e1/inspect', {'paths': [shop_log]})
    assert status == 200 and data['ok'] is True
    assert data['ai_ready'] in (True, False)
    prop = data['files'][0]
    sh = _civil(prop['sheets'])
    assert sh['header_rows'] == [7] and sh['kind'] == 'register'
    fields = {(c['header'], c['index']): c['field'] for c in sh['columns']}
    assert fields[('Type', 6)] == 'submittal_type' and fields[('Type', 4)] == 'ignore'
    assert fields[('TYPE', 10)] == 'trade' and fields[('Drawings No', 7)] == 'drawing_no'
    civil = next(t for t in prop['preview']['by_trade'] if t['trade'] == 'Civil')
    assert (civil['req'], civil['approved_rows'], civil['not_approved_rows'],
            civil['under_review_rows']) == (4, 2, 1, 1)
    assert prop['remembered'] is None
    assert not os.path.exists(tmp_path / 'elog_layouts' / 'layouts.json')   # nothing remembered yet


def test_inspect_missing_file(test_server):
    _, data = _post(test_server, '/api/e1/inspect', {'paths': ['/nope.xlsx']})
    assert data['ok'] is False


def test_inspect_reports_an_unreadable_file_without_hiding_the_others(test_server, shop_log, tmp_path):
    bad = tmp_path / 'old.xls'
    bad.write_bytes(b'not a workbook')
    _, data = _post(test_server, '/api/e1/inspect', {'paths': [str(bad), shop_log]})
    assert data['ok'] is True
    assert 'xlsx' in data['files'][0]['error']
    assert data['files'][1]['sheets']


def test_preview_recounts_with_an_edited_layout(test_server, shop_log):
    _, data = _post(test_server, '/api/e1/inspect', {'paths': [shop_log]})
    layout = data['files'][0]
    sh = _civil(layout['sheets'])
    for c in sh['columns']:                      # group by the OTHER 'Type' (RFT / Concrete Dimension)
        if c['index'] == 4:
            c['field'] = 'submittal_type'
        elif c['index'] == 6:
            c['field'] = 'ignore'
    _, out = _post(test_server, '/api/e1/preview', {'path': shop_log, 'layout': layout})
    assert out['ok'] is True
    groups = {(g['trade'], g['submittal_type']): g['req'] for g in out['layout']['preview']['groups']}
    assert groups == {('Civil', 'RFT'): 3, ('Civil', 'Concrete Dimension'): 1}


def test_upload_with_confirmed_layout_counts_and_remembers(test_server, shop_log, tmp_path):
    _, data = _post(test_server, '/api/e1/inspect', {'paths': [shop_log]})
    layout = data['files'][0]
    layout['code_map']['W'] = 'ignore'           # the planner's choice for this log
    _, up = _post(test_server, '/api/e1/upload', {'paths': [shop_log], 'layouts': {shop_log: layout},
                                                   'category_names': ['Engineering']})
    assert up['ok'] is True
    row = next(r for r in up['engineering_e1'] if (r['trade'], r['submittal_type']) == ('Civil', 'SD'))
    # D-4 (W) no longer counts as under review — it is still submitted
    assert (row['req'], row['submitted_rows'], row['approved_rows'], row['under_review_rows']) == (4, 4, 2, 0)
    assert row['bucket'] == 'engineering'        # the file name says Shop
    assert os.path.exists(tmp_path / 'elog_layouts' / 'layouts.json')
    # the next inspect of a log with the same layout opens with the planner's choices
    p2 = tmp_path / 'Shop_Log_next_week.xlsx'
    _shop_log(p2)
    _, again = _post(test_server, '/api/e1/inspect', {'paths': [str(p2)]})
    prop2 = again['files'][0]
    assert prop2['remembered']['file'] == 'Shop_Log.xlsx'
    assert prop2['code_map']['W'] == 'ignore'


def test_upload_layouts_as_a_list(test_server, shop_log):
    _, data = _post(test_server, '/api/e1/inspect', {'paths': [shop_log]})
    _, up = _post(test_server, '/api/e1/upload', {'paths': [shop_log], 'layouts': [data['files'][0]]})
    assert up['ok'] is True
    assert any((r['trade'], r['submittal_type'], r['req']) == ('Civil', 'SD', 4) for r in up['engineering_e1'])


def test_upload_without_layouts_keeps_the_original_reader(test_server, shop_log):
    from p6_evm.e1_log import read_e1_rows, summarize_e1
    _, up = _post(test_server, '/api/e1/upload', {'paths': [shop_log]})
    assert up['ok'] is True
    old = summarize_e1(read_e1_rows(shop_log))
    assert {(r['trade'], r['submittal_type']) for r in up['engineering_e1']} == set(old)


def test_ai_suggest_refused_cleanly_without_the_offline_brain(test_server, shop_log, monkeypatch):
    from p6_evm import elog_smart
    monkeypatch.setattr(elog_smart, 'local_ai_ready', lambda: False)
    _, data = _post(test_server, '/api/e1/inspect', {'paths': [shop_log]})
    assert data['ai_ready'] is False
    _, out = _post(test_server, '/api/e1/ai-suggest', {'layout': data['files'][0]})
    assert out['ok'] is False and 'offline AI' in out['error']


def test_ai_suggest_with_a_ready_brain_only_labels_suggestions(test_server, shop_log, monkeypatch):
    from p6_evm import elog_smart
    _, data = _post(test_server, '/api/e1/inspect', {'paths': [shop_log]})
    monkeypatch.setattr(elog_smart, 'local_ai_ready', lambda: True)
    real = elog_smart.suggest_columns_with_local_ai
    monkeypatch.setattr(elog_smart, 'suggest_columns_with_local_ai',
                        lambda lay: real(lay, generate=lambda s, u: '{"suggestions": []}'))
    _, out = _post(test_server, '/api/e1/ai-suggest', {'layout': data['files'][0]})
    assert out['ok'] is True
    assert _civil(out['layout']['sheets'])['columns'] == _civil(data['files'][0]['sheets'])['columns']
