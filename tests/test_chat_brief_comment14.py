"""Owner comment 14 — every AI Chat answer must be simple, clear and easy to understand:
"put your hand on the problem and give advice".

Each of the 15 answers now OPENS with a short plain brief — the problem, where it is, why, what to
do — built by ``p6_chat/merged/_brief.py`` from the same grounded facts as the long analysis, which
is folded underneath. These tests hold the brief to the rules that make it clear:
short, no planner shorthand, the activity named with its ID and dates, actions that say what to do.
"""
import os
import re

import pytest

from p6_chat.merged import _brief as B

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QIDS = ['q%02d' % i for i in range(1, 16)]


def _act(i, name, tf, pct, fin, bl, slip, wbs, typ='Task', done=False):
    return {'id': i, 'name': name, 'tf': tf, 'pct': pct, 'finish': fin, 'baseline_finish': bl, 'slip_wd': slip,
            'wbs': wbs, 'type': typ, 'done': done}


def _facts(delay=60, cost_derived=True):
    return {
        'ok': True, 'project_name': 'Test Works', 'data_date': '19-Jul-2026', 'activity_count': 1500,
        'calendar_count': 4, 'baseline_finish': '09-Feb-2027',
        'forecast_finish': '02-May-2027' if delay > 0 else '09-Feb-2027',
        'delay_days': delay, 'spi': 0.66 if delay > 0 else 1.0, 'cpi': 1.0, 'pv': 562.7e6,
        'ev': 370.4e6 if delay > 0 else 562.7e6, 'ac': 370.4e6, 'cost_derived': cost_derived,
        'planned_pct': 63, 'actual_pct': 41 if delay > 0 else 63, 'has_history': False,
        'disciplines': [
            {'name': 'Construction Works', 'weight': 0.95, 'planned': 61, 'actual': 40 if delay > 0 else 61,
             'gap': 21 if delay > 0 else 0},
            {'name': 'MCC Design & Engineering', 'weight': 0.01, 'planned': 74, 'actual': 0 if delay > 0 else 74,
             'gap': 74 if delay > 0 else 0}],
        'value_gap': {'dimension': 'Type of Works', 'groups': [
            {'code': 'Civil Works', 'pv': 560e6, 'ev': 369e6, 'gap': 190.8e6 if delay > 0 else 0, 'pct_of_gap': 99.2},
            {'code': 'Equipment Works', 'pv': 1e5, 'ev': 8e4, 'gap': 2e4 if delay > 0 else 0, 'pct_of_gap': 0.01}]},
        'submittals': [{'trade': 'MEP', 'submittal_type': 'Detailed Design', 'planned_appr': 52, 'actual_appr': 0}],
        'audit': {'lag_lead': {'kpis': {'need_justification_count': 72, 'critical_count': 197, 'long_threshold_days': 14}}},
        'critical_oos': 2, 'dangling_count': 20, 'dangling_pct': 1.4, 'open_ends': 0,
        'neg_float_count': 712 if delay > 0 else 0, 'neg_float_pct': 48.6, 'float_above': 404, 'float_threshold': 44,
    }


def _network(delay=60, inputs=True):
    head = _act('CONS.PL.S9.1000', 'Drilling For Piles', -61, 0, '06-Sep-2026', '23-Jun-2026', 61,
                'Construction Works / Silos Civil Works / Phase C / Silo 9')
    mid = _act('CONS.PL.S10.1040', 'Excavation Works for Silo 10', -59, 0, '24-Nov-2026', '16-Sep-2026', 58,
               'Construction Works / Silos Civil Works / Phase C / Silo 10')
    tail = _act('CONS.CE.1150', 'Termination For MCC Room', -60, 0, '02-May-2027', '09-Feb-2027', 60,
                'Construction Works / Cable Erection Works / Phase C')
    late_in = [_act('INP.EMP.1010', 'Layout Approval', -48, 0, '20-Aug-2026', '04-Mar-2026', 122, 'Inputs From Client / Layout'),
               _act('INP.EMP.1030', 'Design Road Level From Client', -40, 0, '19-Jul-2026', '10-Feb-2026', 114,
                    'Inputs From Client / Road Level', 'StartMilestone')]
    fin = _act('CM.1020', 'Scope Completion', -delay, 0, '02-May-2027' if delay > 0 else '09-Feb-2027', '09-Feb-2027', delay,
               'Control Milestones', 'FinishMilestone')
    return {'ok': True, 'finish_milestone': fin, 'finish_tf': -delay, 'chain': [head, mid, tail], 'chain_count': 52,
            'chain_band': 5, 'deepest': [mid], 'milestones': [fin] + late_in,
            'milestones_open_late': ([fin] + late_in) if delay > 0 else [],
            'client_inputs': late_in, 'client_inputs_late_open': late_in if (inputs and delay > 0) else [],
            'client_inputs_late_done': []}


def _text(b):
    return ' '.join([b['problem']] + b['where'] + b['why'] + b['do'])


def _all(delay=60, inputs=True, net=True):
    F = _facts(delay)
    N = _network(delay, inputs) if net else {'ok': False, 'error': 'file not found'}
    return {q: B.build(q, {}, F, N) for q in QIDS}


CASES = {'behind': dict(delay=60), 'behind, no client item': dict(delay=60, inputs=False),
         'on time': dict(delay=0), 'ahead': dict(delay=-12), 'file missing': dict(delay=60, net=False)}


@pytest.mark.parametrize('case', sorted(CASES))
def test_every_question_opens_with_a_complete_brief(case):
    for q, b in _all(**CASES[case]).items():
        assert b, (case, q)
        assert b['problem'].strip() and b['do'], (case, q)
        assert set(b) == {'problem', 'where', 'why', 'do'}
        assert len(b['where']) <= B.MAX_WHERE and len(b['why']) <= B.MAX_WHY and 1 <= len(b['do']) <= B.MAX_DO, (case, q)
        assert all(isinstance(x, str) and x.strip() for x in b['where'] + b['why'] + b['do']), (case, q)


@pytest.mark.parametrize('case', sorted(CASES))
def test_the_brief_is_short_and_in_short_sentences(case):
    for q, b in _all(**CASES[case]).items():
        words = len(_text(b).split())
        assert words <= 300, (case, q, words)               # the full answers ran 2,000-10,000 words
        for sent in re.split(r'(?<=[.!?])\s+', re.sub(r'\*\*', '', _text(b))):
            n = len(sent.split())
            assert n <= 45, (case, q, n, sent)


SHORTHAND = [r'\bwd\b', r'\bchain\b', r'\btrunk\b', r'\bladder\b', r'\bbipolar\b', r'\btells\b', r'\bTIA\b', r'\bEOT\b',
             r'\bdanglers?\b', r'\bfragnets?\b', r'\bcaps out\b', r'\bDCMA\b']


@pytest.mark.parametrize('case', sorted(CASES))
def test_no_planner_shorthand_in_any_brief(case):
    for q, b in _all(**CASES[case]).items():
        for pat in SHORTHAND:
            assert not re.search(pat, _text(b)), (case, q, pat, _text(b))
        # no missing value leaking into a sentence ('due None', 'forecast for None') — the English
        # 'None of them has started' / 'None is in the schedule' is fine
        assert not re.search(r'\bNone\b(?! (of|is)\b)', _text(b)), (case, q, _text(b))
        assert 'nan' not in _text(b).lower().split(), (case, q)


def test_it_puts_a_hand_on_the_problem_the_activity_its_id_and_its_dates():
    b = _all()['q01']
    t = _text(b)
    assert '60 working days late' in b['problem']
    assert 'Drilling For Piles' in t and 'CONS.PL.S9.1000' in t           # the activity, by name AND id
    assert '23-Jun-2026' in t and '06-Sep-2026' in t                      # planned and forecast
    assert 'Phase C, Silo 9' in t                                         # where on the job
    assert '02-May-2027' in t and '09-Feb-2027' in t                      # the finish, forecast and baseline
    assert 'Construction Works' in t and '95%' in t                       # the discipline that carries it
    assert 'Layout Approval' in t and 'INP.EMP.1010' in t                 # the client's late item


def test_advice_says_what_to_do_and_to_which_activity():
    for q in ('q01', 'q02', 'q04', 'q05'):
        do = _all()[q]['do']
        assert do[0].startswith('Start **Drilling For Piles** (CONS.PL.S9.1000) now.'), (q, do[0])
        assert 'firm start date' in do[0]
    # never the old shorthand advice
    assert 'Aim recovery' not in ' '.join(x for b in _all().values() for x in b['do'])
    assert any('Write to the client today about **Layout Approval**' in x for x in _all()['q01']['do'])
    # health: each fix names the screen that does it
    do = ' '.join(_all()['q06']['do'])
    assert 'Out of Sequence' in do and 'Resolve & Correct' in do and 'Lag Report' in do


def test_it_never_claims_more_than_the_file_shows():
    b = _all(inputs=False)
    assert 'No late client item is in the file' in ' '.join(b['q01']['why'])
    assert b['q13']['problem'].startswith('Not from this file alone.')    # no client event → no claim from the file
    assert "contractor's" in b['q13']['problem']
    assert 'no real actual cost' in ' '.join(b['q08']['why'])              # CPI 1.00 is not 'on budget'
    assert 'cannot show whether manpower is the cause' in b['q09']['problem']
    assert 'does not include any allowance for bad weather' in b['q14']['problem']
    # the schedule file could not be re-read: say so, do not invent an activity
    miss = _all(net=False)
    assert 'could not re-read the schedule file' in _text(miss['q01'])
    assert 'Drilling' not in _text(miss['q01'])


def test_a_project_that_is_not_late_is_not_told_it_is():
    for case in ('on time', 'ahead'):
        for q, b in _all(**CASES[case]).items():
            assert ' late**' not in b['problem'] and 'To recover' not in b['problem'], (case, q, b['problem'])
    assert 'on its baseline finish date' in _all(delay=0)['q01']['problem']
    assert 'ahead' in _all(delay=-12)['q01']['problem']
    assert 'no extension of time to claim' in _all(delay=0)['q13']['problem']
    assert 'matches the plan' in _all(delay=0)['q08']['problem']


def test_plain_words_filter():
    assert B.plain('float -61 wd on the finish chain') == 'float -61 working days on the critical path'
    assert B.plain('+60wd') == '+60 working days'
    assert B.plain('the driving path and the trunk') == 'the critical path and the main sequence'
    assert B.plain('20 danglers; run a TIA for the EOT') == \
        '20 activities with a missing link; run a time impact analysis for the extension of time'
    assert B.plain('the supply chain') == 'the supply chain'              # an ordinary word is left alone
    assert B.plain(None) == ''
    a = B.plain_answer({'verdict': 'One chain sets it at -60 wd.', 'measured': 'TF in wd',
                        'actions': ['Clean up the 20 danglers.'], 'pills': [{'text': '+60 wd', 'tone': 'danger'}],
                        'sections': [{'label': 'Driving path', 'paras': ['The chain is late.'],
                                      'table': {'cols': ['Activity', 'Slip (wd)'],
                                                'rows': [['Chain Link Fence', '+5 wd']], 'note': 'in wd'}}],
                        'drilldowns': [{'to': 'q05', 'text': 'How do I recover the chain?'}]})
    assert a['verdict'] == 'One critical path sets it at -60 working days.'
    assert a['actions'] == ['Clean up the 20 activities with a missing link.']
    assert a['pills'][0]['text'] == '+60 working days'
    sec = a['sections'][0]
    assert sec['label'] == 'Critical path' and sec['paras'] == ['The critical path is late.']
    assert sec['table']['cols'] == ['Activity', 'Slip (working days)'] and sec['table']['note'] == 'in working days'
    # in a table cell only the unit is spelled out — an activity name is never reworded
    assert sec['table']['rows'] == [['Chain Link Fence', '+5 working days']]
    assert a['drilldowns'][0]['text'] == 'How do I recover the critical path?'
    assert B.plain('If those all sat on a single chain you would have one.') == \
        'If those all sat on a single line of activities you would have one.'


def test_build_never_raises_and_gives_none_when_it_cannot():
    assert B.build('q01', {}, {'ok': False}, {}) is None
    assert B.build('q99', {}, _facts(), _network()) is None
    assert B.build('q01', None, {'ok': True}, None) is not None           # almost no facts: still an honest brief
    for q in QIDS:
        B.build(q, {}, {'ok': True, 'delay_days': 'x', 'disciplines': None}, {'ok': True, 'chain': None})


def test_every_answer_gets_its_brief_and_the_plain_words_pass():
    src = open(os.path.join(ROOT, 'p6_chat', 'merged', '__init__.py'), encoding='utf-8').read()
    assert "out['brief'] = _brief.build(qid, out, F, N)" in src and '_brief.plain_answer(out)' in src
    assert set(B._BUILDERS) == set(QIDS)
