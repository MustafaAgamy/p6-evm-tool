"""Owner comment 29 — "Excel must include ALL the data of a feature, including features with
many sub-features."

Every feature's workbook was compared, table by table, with what its screen / PDF shows. These
lock the gaps that were found and closed:

  * Baseline Narrative — was a short status summary; now one sheet per report section (19);
  * Schedule Health checks — only the findings list; now also Summary (score, key figures,
    severity rules), By WBS, the Management view and the schedule's milestones;
  * Calendar Audit — now also Summary, Monthly Working Time, other calendars' exceptions, Issues;
  * Critical Path Analyzer — the activities behind the four float-migration counts;
  * Consultant Review — the milestone table; Constructability — WBS review & first fixes;
  * Update vs Update — S-curve numbers, progress by every activity code, critical path lists,
    the activities behind 'what moved'; Update Analysis — scope weight for every activity code.
"""
import json
import re
import zipfile

from p6_evm.parser import parse_file
from p6_evm.xlsx_writer import write_calendar_xlsx, write_sections_xlsx
from tests.test_narrative_critpath_blank_float import _xer
from tests.test_server import _post_json


def _book(path):
    """{sheet name: all its text} of a workbook written by the shared writer (inline strings)."""
    with zipfile.ZipFile(path) as z:
        names = re.findall(r'<sheet [^>]*name="([^"]*)"', z.read('xl/workbook.xml').decode('utf-8'))
        files = sorted((n for n in z.namelist() if re.match(r'xl/worksheets/sheet\d+\.xml$', n)),
                       key=lambda n: int(re.findall(r'\d+', n)[-1]))
        out = {}
        for nm, f in zip(names, files):
            xml = z.read(f).decode('utf-8')
            cells = re.findall(r'<t[^>]*>(.*?)</t>', xml, re.S) + re.findall(r'<v>(.*?)</v>', xml)
            out[nm.replace('&amp;', '&')] = '\n'.join(cells).replace('&amp;', '&').replace('&gt;', '>')
        return out


# ── Baseline Narrative ──────────────────────────────────────────────────────────

def _narrative_doc(tmp_path):
    from p6_narrative.report import build_report
    path = _xer(tmp_path)
    return path, build_report(parse_file(path), path=path, setup=None).to_dict()


def test_narrative_workbook_has_one_sheet_per_report_section(tmp_path):
    from p6_narrative.xlsx_report import narrative_sheets
    _path, doc = _narrative_doc(tmp_path)
    sheets = narrative_sheets(doc)
    assert len(sheets) == len(doc['sections']) >= 15
    for sh, sec in zip(sheets, doc['sections']):
        assert sh['blocks'], sec.get('title')
        for b in sh['blocks']:                       # every block is a real table for the writer
            assert b['headers'] and b['rows'], (sec.get('title'), b.get('title'))
            assert all(isinstance(r, list) for r in b['rows'])
    out = tmp_path / 'narr.xlsx'
    write_sections_xlsx(str(out), sheets)
    text = '\n'.join(_book(str(out)).values())
    # the schedule's own content reaches the workbook: the WBS, the critical path's zones and dates
    for needle in ('Batch House', 'Mixer Building', 'Piling / excavation', '3 Mar 2025', '21 Mar 2025'):
        assert needle in text, needle


def test_narrative_workbook_survives_an_odd_or_unknown_section():
    from p6_narrative.xlsx_report import narrative_sheets
    doc = {'sections': [{'kind': 'not-a-kind', 'title': 'Something new', 'number': '20', 'note': 'n'},
                        {'kind': 'scope', 'title': 'Scope', 'number': '7', 'payload': {'rows': 'broken'}},
                        'junk']}
    sheets = narrative_sheets(doc)
    assert len(sheets) == 2 and all(s['blocks'] for s in sheets)
    for empty in ({}, None):                       # no report yet → one sheet that says so
        only = narrative_sheets(empty)
        assert len(only) == 1 and only[0]['blocks'][0]['rows'] == [['Generate the narrative first.']]


def test_narrative_excel_route_writes_the_report_posted_by_the_screen(test_server, tmp_path):
    _path, doc = _narrative_doc(tmp_path)
    out = tmp_path / 'route.xlsx'
    _, data = _post_json(test_server, '/api/narrative/excel',
                         {'doc': json.loads(json.dumps(doc, default=str)), 'output_path': str(out)})
    assert data['ok'], data
    book = _book(str(out))
    assert len(book) == len(doc['sections'])
    assert 'Mixer Building' in '\n'.join(book.values())


def test_narrative_excel_route_rebuilds_the_report_when_none_is_posted(test_server, tmp_path):
    path, doc = _narrative_doc(tmp_path)
    out = tmp_path / 'rebuilt.xlsx'
    _, data = _post_json(test_server, '/api/narrative/excel', {'xml_path': path, 'output_path': str(out)})
    assert data['ok'], data
    assert len(_book(str(out))) == len(doc['sections'])
    _, data = _post_json(test_server, '/api/narrative/excel', {'output_path': str(tmp_path / 'none.xlsx')})
    assert data['ok'] is False and 're-import' in data['error']


# ── Schedule Health checks ──────────────────────────────────────────────────────

_MODULE = {
    'module': 'float', 'name': 'Float Analysis', 'score': 72.4, 'grade': 'Acceptable', 'pct': 27.6,
    'kpis': {'total_activities': 1466, 'above_threshold': 404, 'float_pct': 27.6, 'computable': True,
             'by_type': [{'type': 'FS', 'count': 252, 'pct': 62.8}, {'type': 'SS', 'count': 81, 'pct': 20.2}]},
    'wbs_summary': [{'wbs': 'Design > Approval', 'activities': 5, 'high': 5, 'pct': 100.0, 'grade': 'Critical'},
                    {'wbs': 'Construction', 'activities': 743, 'high': 12, 'pct': 1.6, 'grade': 'Good'}],
    'mgmt': {'float_health': 98.4, 'fh_color': 'green',
             'stats': {'total': 1165, 'critical': 722, 'is_update': True},
             'wbs': [{'wbs': 'Phase II Design', 'short': 'P2', 'activities': 392, 'avg_float': 71.2,
                      'is_construction': False}],
             'conclusion': 'The construction logic needs a planning review.'},
    'baseline_milestones': [{'activity_id': 'CM.1000', 'name': 'Commencement Date',
                             'task_type': 'StartMilestone', 'finish': '2024-10-24'}],
    'milestone_counts': {'On track': 2, 'Late': 1},
    'presentation': {
        'verdict': '27.6% of items flagged.',
        'tiles': [{'label': 'Total Activities', 'value': '1,466'}, {'label': 'Above Threshold', 'value': '404'}],
        'scoring': {'formula': 'Score = 100 − defect%', 'derivation': '404 of 1,466', 'bands': '≥ 98 Excellent',
                    'benchmark': 'DCMA Metric 6'},
        'severity': {'basis': 'Raised on the critical path.',
                     'levels': [{'level': 'High', 'criteria': 'Over the threshold, on the critical path'}]},
    },
}


def test_health_check_extra_sheets_carry_everything_but_the_findings(tmp_path):
    from p6_audit.excel_sheets import extra_sheets, label
    sheets = extra_sheets(_MODULE)
    names = [s['name'] for s in sheets]
    assert names == ['Summary', 'Management View', 'Management — WBS', 'By WBS', 'Schedule Milestones']
    out = tmp_path / 'm.xlsx'
    write_sections_xlsx(str(out), sheets)
    book = _book(str(out))
    summary = book['Summary']
    for needle in ('Acceptable', '27.6% of items flagged.', 'Score = 100 − defect%', 'DCMA Metric 6',
                   'Above Threshold', '1,466', 'Raised on the critical path.',
                   'Over the threshold, on the critical path', 'On track', 'FS', '62.8'):
        assert needle in summary, needle
    assert 'Computable' not in summary and 'green' not in book['Management View']      # display-only keys stay out
    assert 'The construction logic needs a planning review.' in book['Management View']
    assert 'Phase II Design' in book['Management — WBS'] and 'Average float (d)' in book['Management — WBS']
    assert 'Design > Approval' in book['By WBS'] and 'Construction' in book['By WBS']
    assert 'CM.1000' in book['Schedule Milestones'] and 'Commencement Date' in book['Schedule Milestones']
    assert label('above_threshold') == 'Above threshold' and label('float_pct') == 'Float %'


def test_health_check_extra_sheets_are_guarded():
    from p6_audit.excel_sheets import extra_sheets
    assert extra_sheets({}) == [] and extra_sheets(None) == []
    odd = extra_sheets({'kpis': {'a': 1}, 'wbs_summary': ['x', 3], 'mgmt': 'no', 'presentation': {'tiles': 'bad'}})
    assert [s['name'] for s in odd] == ['Summary']


def test_health_excel_route_keeps_the_findings_first_and_adds_the_rest(test_server, tmp_path, monkeypatch):
    import db
    mods = {'modules': {'float': dict(_MODULE, findings=[
        {'activity_id': 'A-100', 'activity_name': 'Pour slab', 'wbs_path': 'Construction',
         'total_float_days': 60, 'threshold': 44, 'status': 'High', 'severity': 'Medium'}])}}
    monkeypatch.setattr(db, 'get_audit_modules_for_snapshot', lambda sid: mods)
    out = tmp_path / 'float.xlsx'
    _, data = _post_json(test_server, '/api/export/excel',
                         {'snapshot_id': 1, 'module': 'float', 'output_path': str(out)})
    assert data['ok'], data
    book = _book(str(out))
    assert list(book)[0] == 'Float Analysis' and 'A-100' in book['Float Analysis']
    assert {'Summary', 'By WBS', 'Management View', 'Schedule Milestones'} <= set(book)


def test_milestone_check_export_lists_the_schedule_milestones_the_screen_holds(test_server, tmp_path, monkeypatch):
    import db
    stored = {'module': 'hard_constraints', 'name': 'Milestone Check', 'kpis': {'matched': 0},
              'findings': [], 'presentation': {'columns': [{'label': 'Contract Milestone'}], 'rows': []}}
    monkeypatch.setattr(db, 'get_audit_modules_for_snapshot', lambda sid: {'modules': {'hard_constraints': stored}})
    out = tmp_path / 'ms.xlsx'
    _, data = _post_json(test_server, '/api/export/excel', {
        'snapshot_id': 1, 'module': 'hard_constraints', 'output_path': str(out),
        'baseline_milestones': [{'activity_id': 'KD.CE-1000', 'name': 'Cable Erection Completion',
                                 'task_type': 'FinishMilestone', 'finish': '2027-02-09'}]})
    assert data['ok'], data
    book = _book(str(out))
    assert 'KD.CE-1000' in book['Schedule Milestones'] and 'Cable Erection Completion' in book['Schedule Milestones']


# ── Calendar Audit ──────────────────────────────────────────────────────────────

def _calendar_audit():
    def cal(oid, name, hols):
        return {'object_id': oid, 'name': name,
                'monthly_stats': [{'label': 'Jul 2026', 'working_days': 10, 'nonworking_days': 3, 'holidays': 1,
                                   'exceptions': 1, 'working_hours': 80.0, 'days': []}],
                'exceptions': {'holidays': hols, 'special': [], 'shutdowns': []},
                'hours_profiles': [{'name': 'Normal', 'hours': '08:00–16:00', 'hours_per_day': 8.0,
                                    'sub': '6 days/week', 'note': ''}],
                'totals': {'working_days': 188, 'nonworking_days': 37, 'working_hours': 1504.0}}
    return {
        'dashboard': {'data_date': '2026-07-19', 'total_working_days': 188, 'total_holidays': 5,
                      'normal_hours': '08:00–16:00'},
        'project': {}, 'primary_calendar_id': 'A',
        'assigned_calendars': [{'object_id': 'A', 'name': 'Main 6-Day'}, {'object_id': 'B', 'name': 'Night Shift'}],
        'by_calendar': {'A': cal('A', 'Main 6-Day', [{'description': '23 Jul 2026', 'days': 1, 'reason': 'Eid'}]),
                        'B': cal('B', 'Night Shift', [{'description': '6 Oct 2026', 'days': 1, 'reason': 'National day'}])},
        'comparison': [], 'usage': [],
        'conflicts': [{'type': 'mixed_wbs', 'severity': 'High', 'title': 'Mixed calendars inside "Piles"',
                       'detail': 'Activities split across 2 calendars.'}],
        'conclusion': ['Consistency: 98.1% of activities run on one calendar.'],
    }


def test_calendar_workbook_carries_summary_monthly_figures_and_issues(tmp_path):
    out = tmp_path / 'cal.xlsx'
    write_calendar_xlsx(str(out), _calendar_audit())
    book = _book(str(out))
    assert list(book)[:2] == ['Main 6-Day', 'Night Shift']           # the timelines still come first
    assert {'Exceptions', 'Comparison', 'Usage', 'Summary', 'Monthly Working Time',
            'Other Calendars Exceptions', 'Calendar Issues'} <= set(book)
    assert 'Working days' in book['Summary'] and '188' in book['Summary']
    assert 'Consistency: 98.1% of activities run on one calendar.' in book['Summary']
    assert '08:00–16:00' in book['Summary']
    assert 'Jul 2026' in book['Monthly Working Time'] and 'Night Shift' in book['Monthly Working Time']
    assert '6 Oct 2026' in book['Other Calendars Exceptions'] and 'National day' in book['Other Calendars Exceptions']
    assert '23 Jul 2026' not in book['Other Calendars Exceptions']    # the main calendar stays on Exceptions
    assert 'Mixed calendars inside "Piles"' in book['Calendar Issues'].replace('&quot;', '"')


def test_calendar_workbook_without_the_extra_data_is_unchanged(tmp_path):
    out = tmp_path / 'bare.xlsx'
    write_calendar_xlsx(str(out), {'assigned_calendars': [], 'by_calendar': {}})
    assert list(_book(str(out))) == ['Timeline', 'Exceptions', 'Comparison', 'Usage']


# ── Critical Path Analyzer ──────────────────────────────────────────────────────

def test_critical_path_workbook_lists_the_activities_behind_the_migration_counts():
    from p6_critpath.exporters import critpath_excel_sections
    report = {'float_migration_base': 'baseline', 'float_migration': {
        'counts': {'near_to_crit': 1, 'safe_to_near': 0, 'crit_to_recovered': 0, 'held_crit': 1},
        'rows': [{'id': 'B-2', 'from': 'crit', 'to': 'crit', 'kind': 'held_crit', 'name': 'Held one',
                  'base_tf': 0, 'curr_tf': -3.5},
                 {'id': 'A-1', 'from': 'near', 'to': 'crit', 'kind': 'near_to_crit', 'name': 'Lost float',
                  'base_tf': 6, 'curr_tf': 0}]}}
    sheet = next(s for s in critpath_excel_sections(report) if s['name'] == 'Float migration')
    assert len(sheet['blocks']) == 2
    moved = sheet['blocks'][1]
    assert moved['headers'][:3] == ['Activity ID', 'Activity Name', 'Move']
    assert [r[0] for r in moved['rows']] == ['A-1', 'B-2']                       # worst move first
    assert moved['rows'][0] == ['A-1', 'Lost float', 'Near-critical → CRITICAL', 'Near-critical', 'Critical', 6, 0]
    assert moved['rows'][1][-1] == -3.5
    # no rows → the counts block alone, as before
    report['float_migration']['rows'] = []
    assert len(next(s for s in critpath_excel_sections(report) if s['name'] == 'Float migration')['blocks']) == 1


def test_float_migration_rows_carry_the_name_and_both_floats():
    from types import SimpleNamespace
    from p6_critpath.tables import float_migration
    act = lambda tf: {1: {'id': 'A-1', 'name': 'Erect steel', 'task_type': 'TaskDependent', 'total_float_days': tf}}
    out = float_migration(SimpleNamespace(activities=act(0)), SimpleNamespace(activities=act(-4)))
    assert out['counts']['held_crit'] == 1
    assert out['rows'] == [{'id': 'A-1', 'from': 'crit', 'to': 'crit', 'kind': 'held_crit',
                            'name': 'Erect steel', 'base_tf': 0, 'curr_tf': -4}]


# ── Consultant Review · Constructability ────────────────────────────────────────

def test_consultant_review_workbook_has_the_milestone_table():
    from p6_compare.exporters import logic_excel_sections
    sheets = logic_excel_sections({'milestones': [
        {'activity_id': 'KD-1', 'name': 'Handover', 'baseline_finish': '09-Feb-2027', 'update_finish': '02-May-2027'}]})
    ms = next(s for s in sheets if s['name'] == 'Milestones')
    assert ms['blocks'][0]['rows'] == [['KD-1', 'Handover', '09-Feb-2027', '02-May-2027']]
    assert not any(s['name'] == 'Milestones' for s in logic_excel_sections({}))


def test_constructability_workbook_has_wbs_review_and_first_fixes():
    from p6_kb.exporters import findings_excel_sections
    sheets = findings_excel_sections({
        'project_type': 'Industrial › Steel Structures',
        'wbs_review': [{'name': 'Fabrication', 'status': 'ok', 'note': ''},
                       {'name': 'Surface Treatment', 'status': 'missing', 'note': 'Standard branch, not found.'}],
        'issues_by_wbs': [{'name': 'Erection', 'count': 45}],
        'priority_fixes': [{'severity': 'Critical', 'title': 'Erection of silo sheets', 'detail': 'add FS link'}],
        'conclusion': 'Advisory — review before acting.'})
    review = next(s for s in sheets if s['name'] == 'WBS Review')
    assert review['blocks'][0]['rows'] == [['Fabrication', 'Present', ''],
                                           ['Surface Treatment', 'Missing', 'Standard branch, not found.']]
    titles = {b['title']: b for b in sheets[0]['blocks']}
    assert titles['Findings by Work Stage']['rows'] == [['Erection', 45]]
    assert titles['Look at These First']['rows'] == [['Critical', 'Erection of silo sheets', 'add FS link']]
    assert 'Conclusion' not in titles            # it quotes the score — reference-first, no score in exports
    plain = findings_excel_sections({})
    assert [s['name'] for s in plain] == ['Summary'] and len(plain[0]['blocks']) == 2


# ── Update vs Update · Update Analysis ──────────────────────────────────────────

_PERIOD = {
    'scurve': {'periods': ['Jun 26', 'Jul 26'], 'forecast': [40.0, 55.2], 'actual': [30.1, None],
               'dd_prev_idx': 0, 'dd_now_idx': 1},
    'progress_by_code': {'Phase': [{'value': 'Phase A', 'planned': 10.5, 'actual': 10.7},
                                   {'value': 'Phase C', 'planned': 25.8, 'actual': 10.9}],
                         'Empty code': []},
    'critical_path': {'previous': [{'id': 'P-1', 'name': 'Drill piles', 'wbs_path': 'Piles',
                                    'start': '2026-07-19', 'finish': '2026-09-06'}],
                      'current': [{'id': 'C-1', 'name': 'Pour raft', 'wbs_path': 'Raft', 'start': None, 'finish': None}]},
    'buckets': {'counts': {'finished': 1, 'slipped': 1},
                'lists': {'slipped': [{'activity_id': 'S-9', 'activity_name': 'Late one'}],
                          'finished': [{'activity_id': 'F-1', 'activity_name': 'Done one'}]}},
}


def test_update_vs_update_extra_sheets():
    from p6_period.exporters import report_excel_extra_sheets
    sheets = {s['name']: s['blocks'] for s in report_excel_extra_sheets(_PERIOD)}
    assert list(sheets) == ['S-Curve', 'Progress by Code', 'Critical Path', 'What Moved']
    assert sheets['S-Curve'][0]['rows'] == [['Jun 26', 40.0, 30.1, 'Previous data date'],
                                            ['Jul 26', 55.2, '', 'Current data date']]
    assert sheets['Progress by Code'][0]['rows'] == [['Phase', 'Phase A', 10.5, 10.7, 0.2],
                                                     ['Phase', 'Phase C', 25.8, 10.9, -14.9]]
    prev, cur = sheets['Critical Path']
    assert prev['rows'] == [[1, 'P-1', 'Drill piles', 'Piles', '2026-07-19', '2026-09-06']]
    assert cur['rows'] == [[1, 'C-1', 'Pour raft', 'Raft', '', '']]
    assert sheets['What Moved'][0]['rows'] == [['Finished', 'F-1', 'Done one'], ['Slipped', 'S-9', 'Late one']]
    assert report_excel_extra_sheets({}) == [] and report_excel_extra_sheets(None) == []


def test_update_vs_update_route_keeps_sheet_one_and_adds_the_rest(test_server, tmp_path):
    out = tmp_path / 'period.xlsx'
    _, data = _post_json(test_server, '/api/period/excel',
                         {'report': dict(_PERIOD, project_name='Proj'), 'output_path': str(out)})
    assert data['ok'], data
    book = _book(str(out))
    assert list(book) == ['Update vs Update', 'S-Curve', 'Progress by Code', 'Critical Path', 'What Moved']
    assert 'Execution Dashboard' in book['Update vs Update'] and 'S-9' in book['What Moved']


def test_update_analysis_workbook_has_scope_weight_for_every_activity_code():
    from p6_update.exporters import report_excel_sections
    row = lambda v: {'value': v, 'bac': 1000, 'weight_pct': 50.0, 'planned': 40.0, 'actual': 30.0}
    report = {'scope_default': 'Phase',
              'scope': {'Phase': {'code_type': 'Phase', 'rows': [row('Phase A'), row('Phase B')]},
                        'Trade': {'code_type': 'Trade', 'rows': [row('Civil')]}}}
    sheets = {s['name']: s for s in report_excel_sections(report)}
    rows = sheets['Scope Weight - All Codes']['blocks'][0]['rows']
    assert [(r[0], r[1]) for r in rows] == [('Phase', 'Phase A'), ('Phase', 'Phase B'), ('Trade', 'Civil')]
    assert len(sheets['Scope Weight']['blocks'][0]['rows']) == 2          # the default one is unchanged
    one = {'scope_default': 'Phase', 'scope': {'Phase': report['scope']['Phase']}}
    assert 'Scope Weight - All Codes' not in {s['name'] for s in report_excel_sections(one)}
