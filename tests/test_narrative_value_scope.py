"""Narrative concerns round (Ibrahim, Nov 2026) — approved:

1. Contract Value fully defined: split by an ORDERED code list (planner's, else the scope code +
   Controlyx's suggestions); cost carrying none of them is named by its WBS in P6; no
   "Unclassified"; the lines add up to exactly 100 %.
2. Scope of Work written as "Detailed … Scope of Work includes: ➢ … consists of: 1. … ✓ …",
   every building shown, elements in P6 date order (same-day starts by construction logic).
"""
from datetime import datetime
from types import SimpleNamespace

from docx import Document

from p6_narrative import classify as C
from p6_narrative import scope_detail as SD
from p6_narrative.report import _contract_value, _scope, value_classification
from p6_narrative.html import _scope as html_scope, _value_bars as html_value
from p6_narrative.docx_writer import _render_scope

WBS = {
    'R': {'name': 'Project', 'parent_object_id': None},
    'C': {'name': 'Construction', 'parent_object_id': 'R'},
    'S1': {'name': 'Silo 1', 'parent_object_id': 'C'},
    'S2': {'name': 'Silo 2', 'parent_object_id': 'C'},
    'TQ': {'name': 'Towers On Quay', 'parent_object_id': 'C'},
    'T35': {'name': 'Tower 35', 'parent_object_id': 'C'},
    'H': {'name': 'Restoration Buildings', 'parent_object_id': 'C'},
    'EB': {'name': 'Eiffel Bridge - Building NO.(32)', 'parent_object_id': 'H'},
    'EBF': {'name': 'FIRST FLOOR', 'parent_object_id': 'EB'},
    'EBW': {'name': 'Wall Works', 'parent_object_id': 'EBF'},
    'SV': {'name': 'Savannah Exhibit', 'parent_object_id': 'C'},
}


def _act(oid, wbs, start, codes, task='Task'):
    return {'object_id': oid, 'id': oid, 'name': oid, 'wbs_id': wbs, 'task_type': task,
            'planned_start': datetime.fromisoformat(start), 'planned_finish': datetime.fromisoformat(start),
            'activity_codes': codes}


def _data():
    T, B, E, H, CL = 'Type of Works', 'Building', 'Element', 'Heritage', 'Cost loading'
    acts = [
        _act('a1', 'S1', '2026-01-01', {T: 'Civil Works', B: 'Silo 1', E: 'Pile Works', CL: 'Cost'}),
        _act('a2', 'S1', '2026-03-01', {T: 'Civil Works', B: 'Silo 1', E: 'Columns', CL: 'Cost'}),
        _act('a3', 'S2', '2026-02-01', {T: 'Civil Works', B: 'Silo 2', E: 'Pile Works', CL: 'Cost'}),
        _act('a4', 'S2', '2026-04-01', {T: 'Civil Works', B: 'Silo 2', E: 'Columns', CL: 'Cost'}),
        _act('a5', 'TQ', '2026-05-01', {T: 'Civil Works', B: 'Towers On Quay', E: 'Pedestals', CL: 'Cost'}),
        _act('a6', 'T35', '2026-05-02', {T: 'Civil Works', B: 'Tower 35', E: 'Pile Works', CL: 'Cost'}),
        _act('a7', 'T35', '2026-06-02', {T: 'Civil Works', B: 'Tower 35', E: 'Foundation', CL: 'Cost'}),
        # no Type of Works — the Heritage code covers them (a code specific to that gap)
        _act('h1', 'EBW', '2026-07-01', {H: 'Heritage Buildings', CL: 'Cost'}),
        # SOG and Earth Work start the SAME day — construction logic: Earth Work first
        _act('v1', 'SV', '2026-11-09', {T: 'Civil Works', B: 'Savannah Exhibit', E: 'SOG', CL: 'Cost'}),
        _act('v2', 'SV', '2026-11-09', {T: 'Civil Works', B: 'Savannah Exhibit', E: 'Earth Work', CL: 'Cost'}),
        # no code at all → named by its WBS in P6
        _act('x1', 'S1', '2026-08-01', {}),
        _act('m1', 'C', '2026-01-01', {}, task='FinishMilestone'),
    ]
    bac = {'a1': 300, 'a2': 100, 'a3': 300, 'a4': 100, 'a5': 50, 'a6': 40, 'a7': 30,
           'h1': 200, 'v1': 20, 'v2': 40, 'x1': 7}
    return SimpleNamespace(activities={a['object_id']: a for a in acts}, bac_by_activity=bac, wbs=WBS,
                           activity_code_types=[T, B, E, H, CL], project={'name': 'P'},
                           relationships=[])


# ── concern 1 — Contract Value ────────────────────────────────────────────────
def test_suggestion_adds_the_specific_code_not_the_catch_all():
    d = _data()
    codes = C.suggest_codes(C.costed_items(d), 'Type of Works', d.activity_code_types)
    assert codes[:2] == ['Type of Works', 'Heritage']        # not "Cost loading = Cost"
    assert 'Cost loading' not in codes


def test_value_split_has_no_unclassified_and_adds_to_100():
    d = _data()
    sp = C.value_split(d, ['Type of Works', 'Heritage'])
    names = [r['name'] for r in sp['rows']]
    assert 'Unclassified' not in names
    assert 'Heritage Buildings' in names and 'Silo 1' in names       # x1 named by its WBS folder
    assert abs(sum(r['amount'] for r in sp['rows']) - sp['total']) < 1e-6
    assert round(sum(r['pct'] for r in sp['rows']), 1) == 100.0
    assert next(r for r in sp['rows'] if r['name'] == 'Silo 1')['source'] == 'WBS'


def test_shares_always_add_to_exactly_100():
    assert round(sum(C.shares_to_100([1, 1, 1], 3)), 1) == 100.0
    assert round(sum(C.shares_to_100([595.2, 395.6, 393.6, 284.2, 103.0, 46.0, 14.3, 8.4, 1.9], 1842.2)), 1) == 100.0


def test_planner_code_list_wins_and_contract_value_carries_it():
    d = _data()
    sec = _contract_value(d, {'value_codes': ['Type of Works']})
    p = sec.payload
    assert p['codes'] == ['Type of Works'] and p['codes_auto'] is False
    assert 'Unclassified' not in [r['name'] for r in p['rows']]
    assert 'Restoration Buildings' not in [r['name'] for r in p['rows']]
    assert 'Wall Works' in [r['name'] for r in p['rows']]            # h1 → its own WBS folder
    auto = _contract_value(d, {}).payload
    assert auto['codes_auto'] is True and auto['codes'][:2] == ['Type of Works', 'Heritage']


def test_scope_overview_is_the_contract_value_split():
    d = _data()
    cv = {r['name']: r['pct'] for r in _contract_value(d, {}).payload['rows']}
    sc = _scope(d, {'scope_analyses': [{'codes': ['Type of Works', 'Building', 'Element']}]}).payload
    assert {r['name']: r['pct'] for r in sc['disciplines']} == cv


# ── concern 2 — Scope of Work ────────────────────────────────────────────────
def _detail():
    d = _data()
    vc = value_classification(d, {'scope_analyses': [{'codes': ['Type of Works', 'Building', 'Element']}]})
    return SD.describe(d, ['Type of Works', 'Building', 'Element'], vc['codes'])


def test_describe_groups_families_and_categories():
    det = _detail()
    civil = next(t for t in det['types'] if t['name'] == 'Civil Works')
    by = {g['label']: g for g in civil['groups']}
    silos = by['Silos']
    assert silos['kind'] == 'family' and silos['count'] == 2 and silos['members'] == 'Silos 1–2'
    assert silos['elements'] == ['Pile Works', 'Columns']            # P6 date order
    towers = by['Towers']
    assert [c['label'] for c in towers['categories']] and len(towers['categories']) == 2
    assert round(sum(g['pct'] for g in civil['groups']), 1) == 100.0


def test_same_day_elements_follow_construction_logic():
    civil = next(t for t in _detail()['types'] if t['name'] == 'Civil Works')
    sav = next(g for g in civil['groups'] if g['label'] == 'Savannah Exhibit')
    assert sav['elements'] == ['Earth Work', 'SOG']


def test_building_without_code_is_named_by_the_wbs_folder_that_names_the_building():
    her = next(t for t in _detail()['types'] if t['name'] == 'Heritage Buildings')
    assert her['groups'][0]['label'] == 'Eiffel Bridge - Building NO.(32)'   # not "FIRST FLOOR"
    assert her['groups'][0]['elements'] == ['Wall Works']


def test_types_match_contract_value_exactly():
    d = _data()
    det = _detail()
    cv = {r['name']: (r['amount'], r['pct']) for r in _contract_value(d, {}).payload['rows']}
    assert {t['name']: (t['amount'], t['pct']) for t in det['types']} == cv


def test_ladder_and_compact_helpers():
    assert SD.ladder_phase('Earth Work') < SD.ladder_phase('Pile Works') < SD.ladder_phase('Columns') \
        < SD.ladder_phase('Elevated Raft') or SD.ladder_phase('Elevated Raft') == 5
    assert SD.compact(['Silo 10', 'Silo 2', 'Silo 1', 'Silo 3', 'Silo 4', 'Silo 5', 'Silo 6', 'Silo 7',
                       'Silo 8', 'Silo 9']) == 'Silos 1–10'
    assert SD.clean_element('Pile Works - Main Silos', 'Silo 1') == 'Pile Works'
    assert SD.clean_element('Towers on Quay Pedestals', 'Towers on Quay') == 'Pedestals'


# ── rendering: screen / PDF / Word / Excel ───────────────────────────────────
def _scope_payload():
    return _scope(_data(), {'scope_analyses': [{'codes': ['Type of Works', 'Building', 'Element']}]}).payload


def test_html_writes_consists_of_without_unclassified():
    out = html_scope(_scope_payload(), '7', 'Scope of Work', {}, '')
    assert '7.2.1) Detailed Civil Works Scope of Work includes:' in out
    assert 'consist of:' in out and 'divided into 2 categories' in out and 'Unclassified' not in out
    assert out.index('Earth Work.') < out.index('SOG.')
    # detail lines are report content, not editable <p> prose that would silently not save
    assert '<p class="sc-' not in out


def test_html_contract_value_has_no_unclassified():
    out = html_value(_contract_value(_data(), {}).payload, '6', 'Contract Value', {}, '')
    assert 'Unclassified' not in out and 'Heritage Buildings' in out


def test_word_scope_twin(tmp_path):
    doc = Document()
    _render_scope(doc, _scope_payload(), '7', None)
    txt = '\n'.join(p.text for p in doc.paragraphs)
    assert '7.2.1) Detailed Civil Works Scope of Work includes:' in txt
    assert 'Unclassified' not in txt and 'The Towers are divided into 2 categories:' in txt
    assert txt.index('Earth Work.') < txt.index('SOG.')
    doc.save(str(tmp_path / 'scope.docx'))


def test_excel_scope_rows():
    from p6_narrative.xlsx_report import _scope as xl_scope
    blocks = xl_scope(_scope_payload(), {'title': 'Scope of Work'})
    flat = repr(blocks)
    assert 'detailed scope of work' in flat and 'Unclassified' not in flat and 'Pedestals' in flat


# ── end to end: a whole schedule → build_report → HTML + Word ─────────────────
def test_end_to_end_report_has_no_unclassified_and_agrees(tmp_path):
    from tests import intel_fixtures as F
    from p6_narrative.report import build_report
    from p6_narrative.html import render_narrative_html
    from p6_narrative.docx_writer import write_docx
    data = F.matrix_epc(4)
    # cost-load the fixture; strip the codes from two costed activities so the gap must be filled
    acts = list(data.activities.values())
    data.bac_by_activity = {a['object_id']: 100.0 + i for i, a in enumerate(acts)}
    stripped = [a for a in acts if (a.get('activity_codes') or {}).get('Trade')][:2]
    for a in stripped:
        a['activity_codes'] = {}
    doc = build_report(data, setup={'scope_analyses': [{'codes': ['Trade', 'Building', 'Work Type']}]}).to_dict()
    S = {s['kind']: s['payload'] for s in doc['sections']}
    cv, sc = S['value_bars'], S['scope']
    assert cv['codes'][0] == 'Trade'
    assert round(sum(r['pct'] for r in cv['rows']), 1) == 100.0
    assert abs(sum(r['amount'] for r in cv['rows']) - sum(data.bac_by_activity.values())) < 1e-6
    assert [(r['name'], r['pct']) for r in sc['disciplines']] == [(r['name'], r['pct']) for r in cv['rows']]
    assert sc['details'] and 'Unclassified' not in str(sc['details'])
    html = render_narrative_html(doc)
    assert 'Unclassified' not in html
    out = tmp_path / 'n.docx'
    write_docx(doc, str(out))
    assert 'Unclassified' not in '\n'.join(p.text for p in Document(str(out)).paragraphs)


def test_report_says_which_codes_split_the_value():
    from p6_narrative.html import value_basis_text, scope_levels_text
    p = _contract_value(_data(), {}).payload
    t = value_basis_text(p)
    assert '“Type of Works”, then “Heritage”' in t and 'suggested by Controlyx' in t and '100%' in t
    own = value_basis_text(_contract_value(_data(), {'value_codes': ['Type of Works']}).payload)
    assert 'suggested' not in own and 'named by its WBS in P6' in own
    assert 'type of work: Type of Works, then Heritage' in scope_levels_text(_detail())
