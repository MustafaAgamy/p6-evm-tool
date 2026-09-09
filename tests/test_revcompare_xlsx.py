"""Baseline Revision Comparison Excel export — builds a representative report dict
(the shape the client holds / POSTs to /api/revcompare/excel), runs the exporter
through the shared write_sections_xlsx, and asserts a valid, section-mirroring .xlsx.
"""
import zipfile
import xml.etree.ElementTree as ET

from p6_revcompare.xlsx_export import revcompare_excel
from p6_evm.xlsx_writer import write_sections_xlsx

_EXPECTED_SHEETS = [
    'Executive Summary', 'Key Findings', 'Critical Path & Float',
    'Change Register', 'Cost & Resources', 'Scope & Structure',
]


def _report():
    """A representative report mirroring compare.build_report_from_data's return shape."""
    return {
        'rev0': {'file': 'ProjectA_Rev00.xml', 'activities': 120, 'data_date': '01-Jan-2026', 'finish': '30-Jun-2027'},
        'rev1': {'file': 'ProjectA_Rev01.xml', 'activities': 126, 'data_date': '01-Jan-2026', 'finish': '14-Aug-2027'},
        'warnings': ['Rev.01 carries no baseline float on 3 activities.'],
        'summary': {
            'activities0': 120, 'activities1': 126, 'net': 6, 'added': 8, 'removed': 2,
            'modified': 14, 'id_changes': 3, 'renamed': 1, 'moved_wbs': 4,
            'duration_change_wd': 32, 'finish_shift_days': 45,
            'logic': {'total': 12, 'added': 7, 'removed': 5, 'type': 0, 'lag': 0},
            'sequence': 2, 'cp_in': 3, 'cp_out': 1, 'cp_length_change_wd': 32,
            'criticality': 2, 'float_moves': 5, 'calendar_reassigned': 6, 'calendar_changed': 1,
            'constraint_changes': 2, 'wbs_added': 2, 'wbs_removed': 1, 'wbs_renamed': 1,
            'cost_activities': 3, 'budget_delta': 150000, 'resource_changes': 2,
        },
        'profile': [
            {'key': 'logic', 'label': 'Logic', 'count': 12, 'color': '#2563eb'},
            {'key': 'sequence', 'label': 'Sequence', 'count': 2, 'color': '#7c3aed'},
            {'key': 'scope', 'label': 'Scope', 'count': 10, 'color': '#0891b2'},
        ],
        'ledger': [
            {'label': 'Total activities', 'rev0': 120, 'rev1': 126, 'delta': 6},
            {'label': 'New / removed activities', 'rev0': 8, 'rev1': 2, 'delta': None},
            {'label': 'Meaningful sequence changes', 'rev0': 2, 'rev1': None, 'delta': None},
        ],
        'findings': [
            {'severity': 'crit', 'title': 'Erect Steel Frame — Re-sequenced', 'change_type': 'sequence',
             'type_label': 'Sequence', 'body': 'Moved from before to after Pour Slab.',
             'flow_impact': 'Execution-order change'},
            {'severity': 'hi', 'title': 'Substantial Completion — +45 d', 'change_type': 'milestone',
             'type_label': 'Milestone', 'body': 'Governing finish milestone slipped 45 days.',
             'flow_impact': 'Later completion'},
        ],
        'milestones': [
            {'name': 'Substantial Completion', 'rev0': '30-Jun-2027', 'rev1': '14-Aug-2027',
             'change': 45, 'kind': 'delayed', 'change_days': 45},
            {'name': 'Foundations Complete', 'rev0': '10-Mar-2026', 'rev1': '10-Mar-2026',
             'change': 0, 'kind': 'unchanged', 'change_days': 0},
            {'name': 'New Handover MS', 'rev0': None, 'rev1': '20-Aug-2027',
             'change': None, 'kind': 'new', 'change_days': None},
        ],
        'critical_path': {
            'rev0': [{'code': 'A100', 'name': 'Site Handover', 'tf': 0.0, 'is_ms': False, 'state': ''},
                     {'code': 'A200', 'name': 'Pour Slab', 'tf': 0.0, 'is_ms': False, 'state': 'leave'}],
            'rev1': [{'code': 'A100', 'name': 'Site Handover', 'tf': 0.0, 'is_ms': False, 'state': ''},
                     {'code': 'A300', 'name': 'Erect Steel Frame', 'tf': 0.0, 'is_ms': False, 'state': 'enter'}],
            'entered': [{'code': 'A300', 'name': 'Erect Steel Frame'}],
            'left': [{'code': 'A200', 'name': 'Pour Slab'}],
            'length_change_wd': 32,
        },
        'sequence': [
            {'a': 'A300', 'b': 'A200', 'a_name': 'Erect Steel Frame', 'b_name': 'Pour Slab',
             'rev0': 'before', 'rev1': 'after', 'chain0': ['Erect Steel Frame', 'Pour Slab'],
             'chain1': ['Pour Slab', 'Erect Steel Frame'], 'impact': 'material', 'severity': 'crit'},
        ],
        'float_movement': [
            {'activity_id': 'A300', 'name': 'Erect Steel Frame', 'rev0_tf': 12.0, 'rev1_tf': 0.0,
             'delta': -12.0, 'movement': 'Became critical', 'movement_cls': 'rem'},
        ],
        'register': [
            {'activity_id': 'A300', 'orig_id': 'A300', 'activity_name': 'Erect Steel Frame',
             'change_type': 'sequence', 'type_label': 'Sequence', 'rev0': 'before', 'rev1': 'after',
             'change': 'Re-sequenced', 'impact': 'material', 'severity': 'crit', 'status': 'open',
             'detail': {
                 'rev0': {'id': 'A300', 'name': 'Erect Steel Frame', 'wbs': 'Structures',
                          'start': '01-Apr-2026', 'finish': '30-Apr-2026', 'duration': '30 d',
                          'total_float': '12 d', 'criticality': 'Non-critical'},
                 'rev1': {'id': 'A300', 'name': 'Erect Steel Frame', 'wbs': 'Structures',
                          'start': '15-May-2026', 'finish': '14-Jun-2026', 'duration': '30 d',
                          'total_float': '0 d', 'criticality': 'Critical'},
                 'detected': 'Erect Steel Frame moved from before to after Pour Slab.',
                 'why': 'It changes the execution order on the critical path.',
                 'impact': 'Pushes the governing finish milestone out.',
                 'review': 'Confirm the re-sequence is an approved planning decision.'}},
            {'activity_id': 'A250', 'orig_id': None, 'activity_name': 'Install Rebar',
             'change_type': 'logic', 'type_label': 'Logic', 'rev0': 'FS A200', 'rev1': 'FS A200 +2',
             'change': 'Lag +2', 'impact': 'minor', 'severity': 'med', 'status': 'open', 'detail': None},
        ],
        'wbs_changes': {
            'added': [{'path': 'Structures > Steel'}], 'removed': [{'path': 'Temp Works'}],
            'renamed': [{'from': 'Civils', 'to': 'Civil Works'}], 'moved_activities': 4,
        },
        'calendar_changes': {
            'calendars': [{'name': '6-Day Week', 'change': 'added', 'detail': 'new calendar'}],
            'reassignments': [{'from': '5-Day', 'to': '6-Day Week', 'from_wd': 5, 'to_wd': 6, 'count': 6}],
        },
        'constraint_changes': [
            {'activity_id': 'A400', 'name': 'Commissioning', 'kind': 'added', 'hard': True,
             'rev0': '—', 'rev1': 'Must Finish On 10-Aug-2027'},
        ],
        'resource_changes': {
            'cost_available': True, 'resource_available': True,
            'total_budget': {'rev0': 1000000, 'rev1': 1150000, 'delta': 150000},
            'activity_cost_changes': [{'code': 'A300', 'name': 'Erect Steel Frame',
                                       'rev0': 200000, 'rev1': 260000, 'delta': 60000}],
            'assignment_changes': [{'code': 'A300', 'resource': 'Crane', 'kind': 'added',
                                    'rev0': '—', 'rev1': '1.0'}],
            'summary': {'cost_activities': 3},
        },
        'narrative': 'Rev.01 adds 6 activities and slips the governing finish milestone by 45 days.',
    }


def _open_sheets(path):
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        wb = z.read('xl/workbook.xml').decode('utf-8')
        sheets = {}
        i = 1
        while f'xl/worksheets/sheet{i}.xml' in names:
            sheets[i] = z.read(f'xl/worksheets/sheet{i}.xml').decode('utf-8')
            i += 1
    return names, wb, sheets


def test_full_report_produces_six_section_sheets(tmp_path):
    sheets = revcompare_excel(_report())
    assert [s['name'] for s in sheets] == _EXPECTED_SHEETS   # the six redesigned sections
    for s in sheets:
        assert s['blocks'] and all('headers' in b and 'rows' in b for b in s['blocks'])

    p = tmp_path / 'revcompare.xlsx'
    write_sections_xlsx(str(p), sheets)
    assert p.exists()

    names, wb, xml = _open_sheets(str(p))
    assert '[Content_Types].xml' in names and 'xl/workbook.xml' in names
    assert len(xml) == 6                                   # one worksheet per section
    for body in xml.values():
        ET.fromstring(body)                                # every worksheet is well-formed XML

    # workbook lists the section sheet names (& is XML-escaped in the workbook part)
    for nm in _EXPECTED_SHEETS:
        assert nm.replace('&', '&amp;') in wb

    all_xml = '\n'.join(xml.values())
    # content mirrored from the report's sections
    assert 'Erect Steel Frame' in all_xml                  # finding / register / critpath
    assert 'Substantial Completion' in all_xml             # milestone
    assert 'Must Finish On 10-Aug-2027' in all_xml         # constraint change
    assert '<v>150000</v>' in all_xml or '150,000' in all_xml   # budget delta present


def test_empty_report_never_crashes(tmp_path):
    sheets = revcompare_excel({})
    assert [s['name'] for s in sheets] == _EXPECTED_SHEETS
    p = tmp_path / 'empty.xlsx'
    write_sections_xlsx(str(p), sheets)
    assert p.exists()
    names, wb, xml = _open_sheets(str(p))
    assert len(xml) == 6
    for body in xml.values():
        ET.fromstring(body)
    all_xml = '\n'.join(xml.values())
    assert 'No data' in all_xml or 'No ' in all_xml or 'Not applicable' in all_xml  # placeholders, not a crash


def test_resource_not_applicable_when_absent(tmp_path):
    rpt = _report()
    rpt['resource_changes'] = {'cost_available': False, 'resource_available': False,
                               'total_budget': {'rev0': 0, 'rev1': 0, 'delta': 0},
                               'activity_cost_changes': [], 'assignment_changes': [],
                               'summary': {'cost_activities': 0}}
    sheets = revcompare_excel(rpt)
    res = next(s for s in sheets if s['name'] == 'Cost & Resources')   # resource lives here now
    flat = ' '.join(str(r) for b in res['blocks'] for r in b['rows'])
    assert 'Not applicable' in flat or 'not applicable' in flat.lower()
