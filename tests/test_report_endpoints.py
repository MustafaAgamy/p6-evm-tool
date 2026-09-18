"""The two Global Print-Preview endpoints, exercised without a live HTTP server.

We build a Handler instance bypassing BaseHTTPRequestHandler.__init__ (which would try
to service a socket) and capture what it would have sent via _json. This locks the
manifest/render JSON contract the UI depends on, and proves the preview HTML the
endpoint returns is the very document the framework assembler produced.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import server
from p6_report import build_document, get_spec

REPORT = {
    'project_type': 'Data Center',
    'confidence': {'level': 'high', 'hits': 6, 'signatures': 8},
    'score': {'overall': 64, 'band': 'orange', 'band_label': 'Significant',
              'logic': 60, 'completeness': 66, 'structure': 72},
    'verdict': {'title': 'Buildable with fixes', 'detail': 'Sequence gaps in commissioning'},
    'dashboard': {'illogical_count': 4, 'illogical_pct': 3, 'total_relationships': 130,
                  'missing_count': 1, 'missing_pct': 1, 'missing_wbs': 0,
                  'critical_affected': False, 'critical_count': 0, 'coverage': 91},
    'illogical': [{'activity_id': 'C1', 'activity_name': 'UPS commissioning', 'wbs_path': 'MEP',
                   'why': 'No power predecessor', 'impact': 'Critical',
                   'current_preds': [], 'current_succs': [], 'suggested_preds': [], 'suggested_succs': []}],
    'missing': [],
    'conclusion': 'Tie commissioning to permanent power.',
}


def _handler():
    h = server.Handler.__new__(server.Handler)
    h._captured = []
    h._json = lambda status, data: h._captured.append((status, data))
    return h


def test_manifest_endpoint_returns_component_list():
    h = _handler()
    h._handle_report_manifest({'feature': 'constructability', 'report': REPORT})
    status, data = h._captured[-1]
    assert status == 200 and data['ok'] is True
    ids = [c['id'] for c in data['components']]
    assert 'illogical' in ids and 'verdict' in ids
    assert data['title'].startswith('Constructability Review')


def test_manifest_endpoint_unknown_feature_errors_cleanly():
    h = _handler()
    h._handle_report_manifest({'feature': 'nope', 'report': REPORT})
    status, data = h._captured[-1]
    assert status == 200 and data['ok'] is False and 'Unknown report feature' in data['error']


def test_render_endpoint_preview_returns_the_assembler_document():
    h = _handler()
    h._handle_report_render({'feature': 'constructability', 'report': REPORT,
                             'selected_ids': ['verdict', 'illogical'],
                             'order': ['verdict', 'illogical']})
    status, data = h._captured[-1]
    assert status == 200 and data['ok'] is True
    spec = get_spec('constructability', REPORT)
    expected = build_document(spec, REPORT, ['verdict', 'illogical'], ['verdict', 'illogical'])
    # the endpoint returns exactly what the framework assembler produces
    assert data['html'] == expected
    assert 'UPS commissioning' in data['html']
    assert 'Missing Activities' not in data['html']       # not selected


def test_render_endpoint_selection_none_uses_defaults():
    h = _handler()
    h._handle_report_render({'feature': 'constructability', 'report': REPORT})
    status, data = h._captured[-1]
    assert data['ok'] is True
    # default = the two Constructability sections (one score); legacy sections default off
    assert 'Project Risk Summary' in data['html'] and 'Constructability Findings' in data['html']
    assert 'Illogical Relationships' not in data['html']


def test_render_endpoint_unknown_feature_errors():
    h = _handler()
    h._handle_report_render({'feature': 'ghost', 'report': REPORT})
    status, data = h._captured[-1]
    assert data['ok'] is False and 'Unknown report feature' in data['error']


# ── Constructability Knowledge Base export / import / provenance endpoints ────

def _seed_kb(base):
    import p6_kb.pattern_learning as PL
    from p6_kb.tagging import tag_view
    for pid in ('EP-1', 'EP-2'):
        oid = [{'object_id': f'O{i}', 'id': f'A{i}', 'name': n, 'wbs_path': '',
                'activity_codes': {}, 'task_type': 'Task'} for i, n in enumerate(
                [f'{pid} Process Pipe Spool Erection', f'{pid} Process Pipe Hydrotest',
                 f'{pid} Process Pipe Insulation'])]
        v = {'activities_oid': oid, 'by_oid': {a['object_id']: a for a in oid},
             'relationships_oid': [{'pred_oid': 'O0', 'succ_oid': 'O1', 'type': 'FS', 'lag_days': 0},
                                   {'pred_oid': 'O1', 'succ_oid': 'O2', 'type': 'FS', 'lag_days': 0}],
             'activities': oid, 'by_code': {}, 'relationships': [], 'wbs': [],
             'activity_count': 3, 'relationship_count': 2, 'activity_code_types': []}
        tag_view(v)
        PL.learn_from_view(v, pid, 'process', base=base)


def test_kb_knowledge_export_import_and_provenance(tmp_path, monkeypatch):
    import p6_kb.pattern_learning as PL
    src, dst = tmp_path / 'src', tmp_path / 'dst'
    src.mkdir(); dst.mkdir()

    monkeypatch.setattr(PL, 'app_data_dir', lambda: str(src))
    _seed_kb(str(src))
    h = _handler()
    h._handle_kb_knowledge_get()
    assert h._captured[-1][1]['ok'] and h._captured[-1][1]['projects_learned'] == 2

    out = str(tmp_path / 'knowledge.json')
    h = _handler()
    h._handle_kb_knowledge_export({'output_path': out})
    assert h._captured[-1][1]['ok'] and os.path.exists(out)
    # the exported file carries no raw activity text
    assert 'Spool Erection' not in open(out, encoding='utf-8').read()

    monkeypatch.setattr(PL, 'app_data_dir', lambda: str(dst))   # a fresh environment
    h = _handler()
    h._handle_kb_knowledge_import({'input_path': out})
    res = h._captured[-1][1]
    assert res['ok'] and res['result']['imported'] == 2 and res['projects_learned'] == 2


def test_kb_knowledge_import_rejects_bad_file(tmp_path, monkeypatch):
    import p6_kb.pattern_learning as PL
    monkeypatch.setattr(PL, 'app_data_dir', lambda: str(tmp_path))
    bad = str(tmp_path / 'bad.json')
    with open(bad, 'w', encoding='utf-8') as f:
        f.write('{"format": "not-ours"}')
    h = _handler()
    h._handle_kb_knowledge_import({'input_path': bad})
    assert h._captured[-1][1]['ok'] is False
