from p6_evm.gap import gap_by_code


def _rec(codes, bac, planned, actual):
    return {'activity': {'activity_codes': codes}, 'bac': bac,
            'planned_pct': planned, 'actual_pct': actual}


def test_gap_groups_by_code_and_shares():
    # Piles: PV=42, EV=30.1 → gap 11.9 ; Columns: PV=55, EV=46.5 → gap 8.5
    records = [
        _rec({'Type of Works': 'Piles Works'}, 42.0, 1.0, 30.1 / 42.0),
        _rec({'Type of Works': 'Columns Works'}, 55.0, 1.0, 46.5 / 55.0),
    ]
    out = gap_by_code(records, 'Type of Works')
    g = {row['code']: row for row in out['groups']}
    assert round(g['Piles Works']['gap'], 1) == 11.9
    assert round(g['Columns Works']['gap'], 1) == 8.5
    assert round(out['total_gap'], 1) == 20.4
    # shares of the total gap
    assert round(g['Piles Works']['pct_of_gap']) == 58     # 11.9 / 20.4
    # sorted worst-first
    assert out['groups'][0]['code'] == 'Piles Works'


def test_uncoded_activities_bucketed():
    records = [_rec({}, 10.0, 1.0, 0.5)]   # no code for this dimension
    out = gap_by_code(records, 'Type of Works')
    assert out['groups'][0]['code'] == '(uncoded)'
    assert round(out['groups'][0]['gap'], 1) == 5.0


def test_none_planned_pct_skipped():
    records = [_rec({'Type of Works': 'X'}, 10.0, None, 0.5)]
    out = gap_by_code(records, 'Type of Works')
    assert out['groups'] == []
