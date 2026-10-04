"""Comments 51 and 53 — Schedule Health shows rounded numbers.

Ibrahim's rule: days (total float, durations, lags, variances) as whole numbers; percentages and
scores to one decimal (a small 0.2% stays visible). The Whole-Day check keeps the exact duration,
because the decimal IS its finding. The Milestone Check's Total Float column showed raw floats.
"""
from p6_audit.presentation import build_presentation, _days, _pct
from p6_audit.modules.relationship_types import _lag_txt


def test_days_whole_and_percent_one_decimal():
    assert _days(-10.4375) == '-10 d' and _days(117.6) == '118 d' and _days(-0.3) == '0 d'
    assert _pct(26.84) == '26.8%' and _pct(0.2) == '0.2%' and _pct(99.0) == '99%'


def test_negative_float_rows_show_whole_days():
    p = build_presentation({'module': 'negative_float', 'pct': 1.0, 'score': 99.0,
                            'kpis': {'total_activities': 10, 'remaining_activities': 10, 'negative_count': 1, 'neg_pct': 10.0},
                            'findings': [{'activity_id': 'A', 'activity_name': 'a', 'wbs_path': 'W',
                                          'total_float_days': -10.4375, 'severity': 'Critical', 'recommendation': ''}]})
    i = [c['label'] for c in p['columns']].index('Total Float')
    assert p['rows'][0][i]['text'] == '-10 d'


def test_whole_day_check_keeps_the_exact_duration():
    p = build_presentation({'module': 'whole_day', 'pct': 0.2, 'score': 99.8,
                            'kpis': {'total_activities': 10, 'decimal_count': 1, 'decimal_pct': 0.2},
                            'findings': [{'activity_id': 'A', 'original_days': 51.71, 'rounds_to': 52}]})
    cols = [c['label'] for c in p['columns']]
    assert p['rows'][0][cols.index('Original')]['text'] == '51.71 d'
    assert p['rows'][0][cols.index('Rounds To')]['text'] == '52 d'


def test_lag_text_whole_days():
    assert _lag_txt(4.0) == ' +4d' and _lag_txt(-1.6) == ' -2d' and _lag_txt(0.3) == '' and _lag_txt(0) == ''


def test_milestone_check_total_float_whole_days():
    from p6_audit.milestone_check import _milestone_presentation
    ev = {'contract_name': 'Handover', 'contract_date': '01-Jun.2026', 'matched_activity_id': 'M1',
          'matched_activity_name': 'Handover', 'scheduled_finish': '05-Jun.2026', 'variance_days': 4,
          'total_float_days': -10.4375, 'status': 'Late', 'recommendation': ''}
    p = _milestone_presentation([ev], {'Late': 1}, 80.0, 1, [ev])
    i = [c['label'] for c in p['columns']].index('Total Float')
    assert p['rows'][0][i]['text'] == '-10 d'                       # was '-10.4375 d' (comment 51)
