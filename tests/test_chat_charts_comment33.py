"""Owner comment 33 — "AI Chat: build more charts when answering the questions".

Each of the 15 answers carries the charts that fit its question (``p6_chat/merged/_charts.py``),
built from the same grounded facts as its words. These tests hold the charts to: the right chart
for the question, real numbers only, and nothing drawn when the facts are not there.
"""
import os

from p6_chat.merged import _charts as C
from tests.test_chat_brief_comment14 import QIDS, _facts, _network

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TYPES = {'kpi', 'bars', 'pairs', 'hbar'}


def _all(delay=60, inputs=True, net=True):
    F = _facts(delay)
    F['activity_count'] = 1500
    N = _network(delay, inputs) if net else {'ok': False}
    return {q: C.build(q, F, N) for q in QIDS}


def test_every_chart_is_well_formed_and_at_most_two_per_answer():
    for q, charts in _all().items():
        assert len(charts) <= 2, q
        for c in charts:
            assert c['type'] in TYPES and c['title'].strip() and c['items'], (q, c)
            assert len(c['items']) <= C.MAX_ROWS
            for it in c['items']:
                if c['type'] == 'kpi':
                    assert it['label'] and it['value'] and it['tone'] in ('bad', 'warn', 'good', 'info')
                elif c['type'] == 'bars':
                    assert it['name'] and 0 <= it['planned'] <= 100 and 0 <= it['actual'] <= 100
                elif c['type'] == 'pairs':
                    assert it['name'] and it['a'] >= 0 and it['b'] >= 0 and it['la'] and it['lb']
                else:
                    assert it['name'] and it['value'] >= 0 and str(it['label']) and it['tone'] in ('bad', 'warn', 'good', 'info')


def test_each_question_gets_the_charts_that_fit_it():
    ch = _all()
    kinds = {q: [c['type'] for c in v] for q, v in ch.items()}
    assert kinds['q01'] == ['kpi', 'bars']                       # where do we stand: the figures + progress by discipline
    assert kinds['q02'] == ['hbar'] and 'Milestones' in ch['q02'][0]['title']
    assert [c['title'] for c in ch['q04']] == ['The critical path — activities by area',
                                              'Total float — how the activities are spread']
    assert ch['q06'][0]['title'] == 'Schedule logic — what to fix'
    assert kinds['q08'] == ['pairs', 'hbar']                     # cost: planned against done, then what is behind
    assert ch['q10'][0]['title'].startswith('Engineering and procurement')
    assert ch['q13'][0]['title'].startswith('Client items still open')
    assert ch['q14'] == []                                       # weather: nothing in the file to chart
    assert sum(1 for v in ch.values() if v) >= 14


def test_the_numbers_in_a_chart_are_the_tools_own():
    ch = _all()
    k = {i['label']: i for i in ch['q01'][0]['items']}
    assert k['SPI']['value'] == '0.66' and k['SPI']['tone'] == 'bad'
    assert k['Progress']['value'] == '41%' and k['Progress']['hint'] == 'planned 63%'
    assert k['Finish']['value'] == '60 days late'
    assert 'CPI' not in k                                        # no real actual cost in the file: no CPI tile
    d = {i['name']: i for i in ch['q01'][1]['items']}
    assert d['Construction Works'] == {'name': 'Construction Works', 'planned': 61.0, 'actual': 40.0}
    late = {i['name']: i['value'] for i in ch['q13'][0]['items']}
    assert late == {'Layout Approval (INP.EMP.1010)': 122, 'Design Road Level From Client (INP.EMP.1030)': 114}
    first = ch['q03'][0]['items'][0]
    assert first['name'] == 'Drilling For Piles (CONS.PL.S9.1000)' and first['value'] == 61 and first['label'] == '61 days'
    bands = {i['name']: i['value'] for i in ch['q04'][1]['items']}
    assert bands == {'Negative total float (behind)': 712, '0 to 44 days of total float': 384,
                     'More than 44 days of total float': 404}
    assert sum(bands.values()) == 1500
    fix = {i['name']: i['value'] for i in ch['q06'][0]['items']}
    assert fix == {'Activities with a missing link': 20, 'Critical activities out of sequence': 2,
                   'Lags longer than 14 days': 72, 'Lags on the critical path': 197}     # 0 open ends: no empty bar
    pk = ch['q08'][0]['items'][0]
    assert pk['name'] == 'Civil Works' and pk['la'] == '560.0 million' and pk['lb'] == '369.0 million'
    assert [i['name'] for i in ch['q08'][1]['items']] == ['Civil Works']                 # a package under 1 % is not a bar


def test_a_real_cpi_gets_its_tile():
    F = _facts()
    F['cost_derived'], F['cpi'] = False, 1.52
    k = {i['label']: i for i in C.build('q01', F, _network())[0]['items']}
    assert k['CPI']['value'] == '1.52' and k['CPI']['tone'] == 'good'


def test_no_facts_no_chart_and_never_a_crash():
    # the schedule file could not be re-read: charts that need it are left out, the others stay
    miss = _all(net=False)
    assert [c['type'] for c in miss['q01']] == ['kpi', 'bars']
    assert miss['q02'] == [] and miss['q13'] == [] and miss['q09'] == []
    # no client item late: that chart is not drawn
    assert all('Client items' not in c['title'] for c in _all(inputs=False)['q13'])
    # a project on time has no late milestone to chart
    on = _all(delay=0)
    assert on['q02'] == [] and on['q07'] == []
    assert C.build('q01', {'ok': False}, {}) == [] and C.build('q99', _facts(), _network()) == []
    for q in QIDS:
        assert isinstance(C.build(q, {'ok': True, 'disciplines': None, 'value_gap': 7, 'audit': None}, {'ok': True, 'chain': 3}), list)
    # one chart failing must not take the other with it
    F = _facts()
    F['activity_count'] = 1500
    F['audit'] = 'broken'
    assert [c['title'] for c in C.build('q06', F, _network())] == ['Total float — how the activities are spread']


def test_long_names_are_cut_for_the_row_but_keep_the_id():
    N = _network()
    N['chain'][0]['name'] = 'A very long activity name that would never fit on one chart row of the answer'
    lab = C.build('q03', _facts(), N)[0]['items'][0]['name']
    assert lab.endswith('… (CONS.PL.S9.1000)') and len(lab) < 70


def test_charts_are_attached_to_every_answer():
    src = open(os.path.join(ROOT, 'p6_chat', 'merged', '__init__.py'), encoding='utf-8').read()
    assert "out['charts'] = _charts.build(qid, F, N)" in src
    assert set(C._PLAN) == set(QIDS)


def test_dashboard_verdict_explains_a_late_finish_with_value_ahead():
    src = open(os.path.join(ROOT, 'p6_chat', 'dashboard.py'), encoding='utf-8').read()
    assert 'The value of work done is ahead of plan, but the finish is late' in src
    assert 'The finish date holds, but less work is done than planned' in src
