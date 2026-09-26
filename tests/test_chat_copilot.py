"""Contract + invariant tests for the Offline AI Chat ▸ AI-Copilot backend bridge
(``p6_chat.copilot``).

Seeds a real snapshot into a temp DB the same way the other DB-backed chat/special tests
do (``temp_db`` + ``upsert_project`` / ``insert_snapshot`` / ``insert_metrics`` /
``insert_category_metrics``), then exercises the bridge end-to-end. Assertions check the
response SHAPE and its invariants (the exact response contracts the frontend is built to),
never the fixture's specific numbers.
"""
import json
import os
import re

import pytest

import db
import p6_chat
from p6_chat import copilot


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def snap(temp_db, xml_path):
    """A behind-schedule snapshot with categories + finish dates, seeded into the temp DB.
    Returns the snapshot id; the XML path is the minimal parseable fixture so the routes
    that re-parse (whatif / activities / scenario / impact) have a real schedule to read."""
    pid = db.upsert_project('P1', 'Grain Bulk Terminal')
    sid = db.insert_snapshot(pid, '2026-01-01', str(xml_path), str(xml_path), 'h1', 10, 2)
    db.insert_metrics(sid, {
        'pv': 100.0, 'ev': 60.0, 'ac': 70.0, 'spi': 0.6, 'cpi': 0.857, 'delay_days': 47,
        'overall_planned_pct': 0.614, 'overall_actual_pct': 0.404, 'variance': -40.0,
    })
    db.insert_category_metrics(sid, {
        'Marine & Jetty Works': {'weight': 40, 'planned_pct': 0.70, 'actual_pct': 0.45,
                                 'bac': 1000, 'ac': 700, 'activity_count': 50, 'overridden': False},
        'Silo Structure': {'weight': 30, 'planned_pct': 0.55, 'actual_pct': 0.40,
                           'bac': 800, 'ac': 500, 'activity_count': 30, 'overridden': False},
    })
    db.save_evm_extras(sid, {'baseline_finish': '2026-06-30', 'expected_finish': '2026-09-15'})
    return sid


# ── project_brain ──────────────────────────────────────────────────────────────

def test_project_brain_returns_ctx_with_expected_keys(snap):
    ctx = copilot.project_brain(snap)
    assert ctx is not None
    for key in ('project_name', 'data_date', 'baseline_finish', 'forecast_finish',
                'delay_days', 'pace_pct', 'planned_pct', 'actual_pct',
                'disciplines', 'worst_discipline', 'trend', 'oos_count', 'float_grade',
                'history', '_result'):
        assert key in ctx, key
    assert isinstance(ctx['disciplines'], list) and ctx['disciplines']
    assert isinstance(ctx['history'], list)
    assert isinstance(ctx['_result'], dict)
    # finish dates were pulled from evm_extras onto the result
    assert ctx['baseline_finish'] and ctx['forecast_finish']


def test_project_brain_same_date_reimport_is_not_a_trend(snap, xml_path):
    """Re-importing the same update (same data date) is not a previous period — even when the
    older import stored a different delay (e.g. before the delay-sign fix)."""
    pid = db.get_project_id_for_snapshot(snap)
    sid2 = db.insert_snapshot(pid, '2026-01-01', str(xml_path), str(xml_path), 'h1', 10, 2)
    db.insert_metrics(sid2, {'pv': 100.0, 'ev': 60.0, 'ac': 70.0, 'spi': 0.6, 'cpi': 0.857, 'delay_days': -47,
                             'overall_planned_pct': 0.614, 'overall_actual_pct': 0.404, 'variance': -40.0})
    assert copilot.project_brain(sid2)['trend'] is None


# ── chat-side corrections to the Copilot engine (weighted driver, project type) ─
RAW_LEADER_WORDING = re.compile(r'biggest gap on the project|the largest variance|largest schedule variance sits|'
                                r'furthest behind', re.I)
CATS = {'Construction Works': {'weight': 0.95, 'planned_pct': 0.61, 'actual_pct': 0.40},
        'MCC Design': {'weight': 0.01, 'planned_pct': 0.74, 'actual_pct': 0.0},
        'Procurement': {'weight': 0.04, 'planned_pct': 1.0, 'actual_pct': 1.0}}


def _weighted_ctx():
    from p6_copilot.context import build_context
    return copilot.weigh_driver(build_context({'delay_days': 30, 'project_name': 'Test', 'categories': CATS,
                                               'spi': 0.66, 'overall_planned_pct': 0.63, 'overall_actual_pct': 0.41},
                                              audit={'modules': {'out_of_sequence': {'kpis': {'oos_count': 9}},
                                                                 'float': {'grade': 'Critical'}}}))


def test_project_brain_names_the_weighted_driver_not_the_widest_gap(temp_db, xml_path):
    pid = db.upsert_project('P2', 'Weighted')
    sid = db.insert_snapshot(pid, '2026-02-01', str(xml_path), str(xml_path), 'h2', 10, 2)
    db.insert_metrics(sid, {'pv': 100.0, 'ev': 60.0, 'ac': 60.0, 'spi': 0.6, 'cpi': 1.0, 'delay_days': 30,
                            'overall_planned_pct': 0.63, 'overall_actual_pct': 0.41, 'variance': -40.0})
    db.insert_category_metrics(sid, {k: dict(v, bac=1, ac=1, activity_count=1, overridden=False) for k, v in CATS.items()})
    ctx = copilot.project_brain(sid)
    assert ctx['worst_discipline']['name'] == 'Construction Works'     # 95% x 21 pts moves the finish
    assert ctx['widest_gap']['name'] == 'MCC Design'                    # 1% x 74 pts is only the widest gap


def _chat_outputs(ctx):
    from p6_copilot.answers import _ANSWERS
    from p6_copilot.report import build_manager_report
    outs = [copilot.engine_answer(qid, ctx, mode) for (mode, qid) in _ANSWERS if qid != 'project_needs']
    outs.append(copilot.chat_wording(build_manager_report(copilot.engine_view(ctx)), (ctx['delay_days'] or 0) > 0))
    return json.dumps(outs, ensure_ascii=False)


def test_copilot_answers_in_the_chat_never_call_the_driver_the_widest_gap():
    ctx = _weighted_ctx()
    blob = _chat_outputs(ctx)
    assert not RAW_LEADER_WORDING.search(blob), RAW_LEADER_WORDING.findall(blob)
    assert 'MCC Design** work is causing' not in blob
    assert 'Construction Works' in copilot.engine_answer('which_wbs', ctx, 'management')['headline']


@pytest.mark.parametrize('delay', [-12, 0, None])
def test_nothing_is_said_to_delay_a_finish_that_is_not_late(delay):
    ctx = _weighted_ctx()
    ctx['delay_days'] = delay
    blob = _chat_outputs(ctx)
    assert 'drag on the finish' not in blob and 'causing most of the delay' not in blob
    assert copilot.engine_answer('which_wbs', ctx, 'management')['headline'].startswith('No part of the project')


def test_after_the_driver_the_next_areas_follow_their_weight():
    from p6_copilot.context import build_context
    cats = {'Construction': {'weight': 0.60, 'planned_pct': 0.91, 'actual_pct': 0.70},
            'MEP': {'weight': 0.30, 'planned_pct': 0.60, 'actual_pct': 0.40},
            'Design': {'weight': 0.01, 'planned_pct': 1.0, 'actual_pct': 0.26}}
    ctx = copilot.weigh_driver(build_context({'delay_days': 30, 'project_name': 'T', 'categories': cats}))
    body = ' '.join(copilot.engine_answer('which_wbs', ctx, 'management')['body'])
    assert body.index('MEP') < body.index('Design') and '(74 pts behind)' in body


def _n(names_by_wbs, root='Grain Bulk Terminal'):
    acts = [{'name': n, 'wbs_path': f'{root} / {w} / Area {k}'} for w, names in names_by_wbs.items() for n in names
            for k in range(3)]
    return {'ok': True, 'activity_count': len(acts), 'kb_view': {'wbs': [], 'activities': acts}}


SILO_N = _n({'Silos Civil Works': ['Drilling For Piles', 'Pile Load Test', 'Elevated Raft'],
             'Silos Mechanical Installations Works': ['Erection Of Silos Sheets', 'Install Silo Roof',
                                                      'Install Belt Conveyor', 'Bucket Elevator Installation']})


def test_project_type_is_read_from_the_file_not_the_name():
    a = copilot.project_needs(SILO_N)
    if a['headline'].startswith('None of the Knowledge Base'):
        pytest.skip('Construction KB not bundled in this build')
    blob = json.dumps(a, ensure_ascii=False)
    assert 'Silos' in a['headline'] and 'Marine' not in blob and 'Airports' not in blob
    bullets = {b.split('**')[1]: b for b in a['body'] if b.startswith('•')}
    assert 'present' in bullets['Slipform / Silo Structure']           # steel silo erection counts as the structure
    assert 'present' in bullets['Conveying & Handling Equipment']
    assert 'not visible' in bullets['Fill Trial / Commissioning']       # a pile load test is not commissioning
    assert not any(copilot._NOT_CONSTRUCTION.search(k) for k in bullets)


def test_a_wbs_root_on_every_row_does_not_decide_the_type():
    jetty = _n({'Marine Works': ['Marine Piling', 'Fenders Installation', 'Bollards Installation', 'Dredging',
                                 'Deck Slab', 'Quay Wall', 'Berthing Trial']}, root='Red Sea Passenger Terminal')
    h = copilot.project_needs(jetty)['headline']
    if h.startswith('None of the Knowledge Base'):
        pytest.skip('Construction KB not bundled in this build')
    assert 'Airports' not in h and 'Marine' in h


def test_type_names_take_the_right_article():
    assert [copilot._a(w) for w in ('Airports', 'Oil & Gas', 'HVDC Link', 'Silos & Storage', 'EV Charging',
                                    'Road')] == ['an', 'an', 'an', 'a', 'an', 'a']


def test_project_type_without_the_file_says_so():
    a = copilot.project_needs({'ok': False})
    assert 'P6 file' in a['headline']


def test_merged_answers_route_the_project_type_question_to_the_chat():
    from p6_chat.qa_service import _original_answer
    s = _original_answer({'id': 't01q09', 'q': 'What does this project type usually need?', 'cap': 'assistant',
                          'qid': 'project_needs', 'mode': 'planning'}, {'ok': True}, {'project_name': 'Harbour Road'},
                         SILO_N)
    assert 'Marine' not in s['headline']
    assert 'checked against your file' in s['headline'] or s['headline'].startswith('None of')


def test_reimports_of_one_update_are_not_update_history(snap, xml_path):
    pid = db.get_project_id_for_snapshot(snap)
    for h in ('h2', 'h3'):
        s = db.insert_snapshot(pid, '2026-01-01', str(xml_path), str(xml_path), h, 10, 2)
        db.insert_metrics(s, {'pv': 100.0, 'ev': 60.0, 'ac': 70.0, 'spi': 0.6, 'cpi': 0.857, 'delay_days': 47,
                              'overall_planned_pct': 0.614, 'overall_actual_pct': 0.404, 'variance': -40.0})
    assert len(copilot.project_brain(s)['history']) == 1


@pytest.mark.parametrize('delay,prev,want_trend,want_tile', [
    (-12, 10, 'about 2 weeks ahead now', 'about 2 weeks ahead'),
    (-3, -20, 'about 4 weeks ahead last update', 'about 3 working days ahead'),
    (30, 10, 'about 6 weeks late now', 'about 6 weeks late')])
def test_briefing_trend_and_finish_keep_the_delay_sign(delay, prev, want_trend, want_tile):
    from p6_copilot.context import build_context
    from p6_copilot.report import build_manager_report
    ctx = copilot.weigh_driver(build_context({'delay_days': delay, 'project_name': 'T', 'categories': CATS,
                                              'baseline_finish': '2027-03-01', 'expected_finish': '2027-02-10'},
                                             prev_delay=prev))
    rep = copilot.fix_report(build_manager_report(ctx), ctx)
    assert want_trend in rep['trend']['text'] and rep['finish']['later'] == want_tile


def test_project_brain_none_when_no_project(temp_db):
    assert copilot.project_brain(999999) is None
    assert copilot.project_brain(None) is None


# ── ask ─────────────────────────────────────────────────────────────────────────

def _assert_answer_shape(a):
    assert isinstance(a, dict)
    for key in ('headline', 'body', 'advice', 'evidence'):
        assert key in a, key
    assert isinstance(a['headline'], str) and a['headline']
    assert isinstance(a['body'], list)
    assert isinstance(a['advice'], list)
    assert isinstance(a['evidence'], list)


def test_ask_repertoire_question(snap):
    out = copilot.ask(snap, question_id='why_delayed')
    assert out['ok'] is True
    assert out['matched'] is True
    assert out['question_id'] == 'why_delayed'
    assert isinstance(out['question_label'], str) and out['question_label']
    _assert_answer_shape(out['answer'])


def test_ask_free_text_routes_via_intent(snap):
    out = copilot.ask(snap, question_text='Why are we behind schedule?')
    assert out['ok'] is True
    assert out['matched'] is True
    assert out['question_id'] == 'why_delayed'
    _assert_answer_shape(out['answer'])


def test_ask_unknown_free_text_defers_gracefully(snap):
    out = copilot.ask(snap, question_text='zzz qqq nonsense text')
    assert out['ok'] is True
    assert out['matched'] is False
    assert out['question_id'] is None
    _assert_answer_shape(out['answer'])


def test_ask_planning_mode(snap):
    out = copilot.ask(snap, question_id='critical_driver', mode='planning')
    assert out['ok'] is True
    assert out['matched'] is True
    _assert_answer_shape(out['answer'])


def test_ask_without_project_errors(temp_db):
    out = copilot.ask(999999, question_id='why_delayed')
    assert out['ok'] is False and out['error']


# ── tia ──────────────────────────────────────────────────────────────────────────

def test_tia_returns_contract(snap):
    out = copilot.tia(snap)
    assert out['ok'] is True
    assert isinstance(out['tia'], dict)
    for key in ('baseline_finish', 'forecast_finish', 'likely_finish', 'likely_slip',
                'worst_finish', 'worst_slip', 'components'):
        assert key in out['tia'], key
    assert isinstance(out['tia']['components'], list)
    for comp in out['tia']['components']:
        assert set(('key', 'label', 'days', 'basis')) <= set(comp)
    assert isinstance(out['insights'], list)
    assert isinstance(out['has_forecast'], bool)


# ── whatif ────────────────────────────────────────────────────────────────────────

def test_whatif_delay_returns_estimate(snap, xml_path):
    out = copilot.whatif(str(xml_path), 'delay', activity_id='ACT001', days=5)
    assert out['ok'] is True
    r = out['result']
    for key in ('impact_days', 'direction', 'headline', 'basis', 'advice', 'estimate'):
        assert key in r, key
    assert r['estimate'] is True
    assert isinstance(r['headline'], str) and r['headline']


def test_whatif_unknown_activity_errors(snap, xml_path):
    out = copilot.whatif(str(xml_path), 'delay', activity_id='NOPE', days=5)
    assert out['ok'] is False and out['error']


# ── activities ────────────────────────────────────────────────────────────────────

def test_activities_lists_rows(snap, xml_path):
    out = copilot.activities(str(xml_path))
    assert out['ok'] is True
    assert isinstance(out['activities'], list) and out['activities']
    row = out['activities'][0]
    for key in ('id', 'name', 'wbs_path', 'is_milestone'):
        assert key in row, key
    assert isinstance(row['is_milestone'], bool)
    ids = [r['id'] for r in out['activities']]
    assert ids == sorted(ids)


# ── manager_report ─────────────────────────────────────────────────────────────────

def test_manager_report_preview_returns_html(snap):
    out = copilot.manager_report(snap, xml_path=None, preview=True)
    assert out['ok'] is True
    assert isinstance(out['report'], dict)
    assert 'one_line' in out['report']
    assert isinstance(out['html'], str)
    assert 'Manager Report' in out['html']


def test_manager_report_without_project_errors(temp_db):
    out = copilot.manager_report(999999, preview=True)
    assert out['ok'] is False and out['error']


def test_manager_report_pdf_needs_output_path(snap):
    out = copilot.manager_report(snap, preview=False, output_path='')
    assert out['ok'] is False and out['error']


# ── scenario / impact validation (no F9 round-trip in a unit test) ─────────────────

def test_scenario_requires_output_path(snap, xml_path):
    out = copilot.scenario(str(xml_path), 'delay', activity_id='ACT001', days=5, output_path='')
    assert out['ok'] is False and out['error']


def test_scenario_delay_requires_activity_and_days(snap, xml_path, tmp_path):
    out = copilot.scenario(str(xml_path), 'delay', activity_id=None, days=None,
                           output_path=str(tmp_path / 'out.xml'))
    assert out['ok'] is False and out['error']


def test_scenario_writes_file(snap, xml_path, tmp_path):
    out_path = tmp_path / 'scenario.xml'
    out = copilot.scenario(str(xml_path), 'delay', activity_id='ACT001', days=5,
                           output_path=str(out_path))
    assert out['ok'] is True, out.get('error')
    assert os.path.isfile(out['output_path'])
    assert 'activity_name' in out and 'label' in out


def test_impact_requires_rescheduled_file(snap, xml_path):
    out = copilot.impact(str(xml_path), rescheduled_path='does_not_exist.xml')
    assert out['ok'] is False and out['error']


# ── module wiring ──────────────────────────────────────────────────────────────────

def test_bridge_exposed_on_package():
    assert p6_chat.copilot is copilot
    for fn in ('project_brain', 'ask', 'tia', 'whatif', 'activities', 'scenario',
               'impact', 'manager_report'):
        assert callable(getattr(copilot, fn))
