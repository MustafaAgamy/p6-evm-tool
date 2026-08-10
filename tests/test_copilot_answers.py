"""Offline Copilot answer-engine tests (V2 Slice 1). Management answers must be plain and
jargon-free, advice-first, and cite evidence — understandable to a manager with no P6 sense.
"""
from p6_copilot.context import build_context
from p6_copilot.answers import answer
from p6_copilot.report import build_manager_report, render_manager_report_html

RESULT = {
    'project_name': 'Metro L3',
    'data_date': '2025-03-03T00:00:00',
    'baseline_finish': '2027-01-15T00:00:00',
    'expected_finish': '2027-03-12T00:00:00',
    'delay_days': 40,
    'spi': 0.85,
    'overall_planned_pct': 0.34,
    'overall_actual_pct': 0.29,
    'categories': {
        'MEP':        {'weight': 0.4, 'planned_pct': 0.34, 'actual_pct': 0.12},
        'Civil':      {'weight': 0.5, 'planned_pct': 0.60, 'actual_pct': 0.58},
        'Milestones': {'weight': 0.0, 'planned_pct': 0.0,  'actual_pct': 0.0},
    },
}

JARGON = ['SPI', 'CPI', 'critical path', 'float', 'WBS', 'fragnet', 'EVM']


def _text(a):
    return ' '.join([a['headline'], *a['body'], *a['advice']])


def test_context_finds_the_worst_area_and_scales_percents():
    ctx = build_context(RESULT)
    assert ctx['delay_days'] == 40 and ctx['behind'] is True
    assert ctx['pace_pct'] == 85                       # SPI 0.85 -> 85% of planned speed
    assert ctx['planned_pct'] == 34 and ctx['actual_pct'] == 29
    assert ctx['worst_discipline']['name'] == 'MEP'    # gap 34-12 = 22, the biggest
    assert ctx['worst_discipline']['gap'] == 22
    assert all(d['name'] != 'Milestones' for d in ctx['disciplines'])   # weight-0 rows excluded


def test_why_delayed_management_is_plain_and_points_at_the_driver():
    a = answer('why_delayed', build_context(RESULT), 'management')
    t = _text(a)
    assert '40' in a['headline']            # the delay, up front
    assert 'MEP' in t                       # the real driver named
    assert '12%' in t and '34%' in t        # done vs should-be-done
    assert a['advice']                      # advice-first: at least one action
    assert any(e['value'] == '40 working days' for e in a['evidence'])


def test_management_answer_is_anchored_to_the_update_date_and_finish_dates():
    a = answer('why_delayed', build_context(RESULT), 'management')
    t = _text(a)
    assert '03-Mar-2025' in a['headline']        # anchored to the update/cutoff date
    assert '15-Jan-2027' in t and '12-Mar-2027' in t   # planned finish -> forecast finish
    assert any(e['value'] == '03-Mar-2025' for e in a['evidence'])


def test_management_answers_carry_no_p6_jargon():
    ctx = build_context(RESULT)
    for qid in ('why_delayed', 'which_wbs', 'health'):
        t = _text(answer(qid, ctx, 'management')).lower()
        for term in JARGON:
            assert term.lower() not in t, f'{qid} leaked jargon: {term}'


def test_health_traffic_light_by_delay():
    assert 'Behind' in answer('health', build_context({**RESULT, 'delay_days': 40}), 'management')['headline']
    assert 'Slipping' in answer('health', build_context({**RESULT, 'delay_days': 5}), 'management')['headline']
    assert 'Healthy' in answer('health', build_context({**RESULT, 'delay_days': -3}), 'management')['headline']


def test_on_track_project_reads_positive():
    a = answer('why_delayed', build_context({**RESULT, 'delay_days': -5}), 'management')
    assert 'on track' in a['headline'].lower()
    assert 'MEP' not in _text(a)            # don't blame an area when we're not behind


def test_unknown_question_defers_gracefully():
    a = answer('meaning_of_life', build_context(RESULT), 'management')
    assert "can't answer that one yet" in a['headline'].lower()
    assert 'premium cloud' in _text(a).lower()


def test_risks_answer_lists_the_driver_and_out_of_order_work():
    ctx = build_context(RESULT, audit={'modules': {'out_of_sequence': {'kpis': {'oos_count': 3}}}})
    t = _text(answer('risks', ctx, 'management'))
    assert 'MEP' in t and '3' in t


def test_manager_report_is_manager_first_and_plain():
    ctx = build_context(RESULT, prev_delay=30)      # was 30 last update, 40 now -> worse
    r = build_manager_report(ctx)
    assert r['status'] == 'Behind'
    assert 'about 2 months' in r['one_line'] and 'MEP' in r['one_line']   # plain time, the driver
    assert r['finish']['promised'] == '15-Jan-2027' and r['finish']['forecast'] == '12-Mar-2027'
    assert r['trend']['dir'] == 'worse'
    assert r['money'] and r['actions']              # money + what-I-need-from-you present
    txt = ' '.join([r['one_line'], r['money'] or '', r['fault'] or '', *r['actions']])
    assert 'working days' not in txt.lower()        # manager never hears "working days"


def test_manager_report_html_renders_and_is_jargon_free():
    h = render_manager_report_html(build_manager_report(build_context(RESULT, prev_delay=30)), {})
    assert '<html' in h.lower() and 'Manager Report' in h
    assert 'Metro L3' in h and '03-Mar-2025' in h
    low = h.lower()
    for term in ('spi', 'critical path', ' float', 'fragnet'):
        assert term not in low, f'report leaked jargon: {term}'
