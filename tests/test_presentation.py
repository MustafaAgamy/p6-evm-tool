"""The normalized presentation is the single source the screen, PDF and Excel share.
These lock the shape (tiles, columns, rows parallel to findings) and the once-only
formatting (mono / wbs+title / severity badge / 'N d' / ISO date / loop chain)."""
from p6_audit.presentation import build_presentation, short_wbs


def _open_ends():
    return {
        'module': 'open_ends', 'name': 'Open Ends', 'score': 97.0, 'grade': 'Good', 'pct': 3.0,
        'kpis': {'total_activities': 100, 'open_ends': 3, 'open_end_pct': 3.0,
                 'no_predecessor': 2, 'no_successor': 1},
        'findings': [{'activity_id': 'A1', 'activity_name': 'Mobilize', 'wbs_path': 'P > Civil > Earthworks',
                      'severity': 'High', 'issue': 'No predecessor', 'recommendation': 'Add a predecessor'}],
    }


def test_standard_module_shape_and_formatting():
    p = build_presentation(_open_ends())
    # tiles pre-formatted
    assert p['tiles'][0] == {'label': 'Total Activities', 'value': '100'}
    # columns carry no '#', labels ported verbatim
    assert [c['label'] for c in p['columns']] == \
        ['Activity ID', 'Activity Name', 'WBS Path', 'Severity', 'Issue', 'Recommendation']
    # one row per finding
    assert len(p['rows']) == 1
    row = p['rows'][0]
    assert row[0] == {'text': 'A1', 'cls': 'mono'}          # activity id mono
    assert row[2]['title'] == 'P > Civil > Earthworks'      # wbs full path in title
    assert row[3] == {'text': 'High', 'badge': 't-high'}    # severity as a badge, not text
    assert 'open on at least one side' in p['verdict']
    assert '3%' in p['verdict']   # 3.0 renders like the screen: '3%', not '3.0%'


def test_rows_are_parallel_to_findings():
    m = _open_ends()
    m['findings'] = m['findings'] * 5
    p = build_presentation(m)
    assert len(p['rows']) == 5   # UI filters findings and renders rows by the same index


def test_days_and_num_columns_right_align():
    m = {'module': 'high_duration', 'pct': 4.0,
         'kpis': {'total_activities': 100, 'over_threshold': 4, 'high_pct': 4.0, 'threshold': 44, 'max_duration': 120},
         'findings': [{'activity_id': 'A2', 'activity_name': 'Long', 'wbs_path': 'P', 'duration_days': 120,
                       'severity': 'Medium', 'recommendation': 'Break it down'}]}
    p = build_presentation(m)
    dur_idx = [c['label'] for c in p['columns']].index('Duration')
    assert p['columns'][dur_idx]['align'] == 'num'
    assert p['rows'][0][dur_idx] == {'text': '120 d', 'cls': 'num'}
    assert 'longer than 44 working days' in p['verdict']


def test_cpli_tiles_use_module_score_and_dates():
    m = {'module': 'cpli', 'name': 'Critical Path / CPLI', 'score': 99.0, 'grade': 'Excellent', 'pct': 1.0,
         'kpis': {'cpli': 0.99, 'computable': True, 'critical_path_length_days': 366, 'cpl_basis': 'working',
                  'project_total_float_days': 4, 'target': 0.95, 'finish_milestone_id': 'A1130'},
         'findings': [{'activity_id': 'A1000', 'activity_name': 'Mob', 'wbs_path': 'P > Civil',
                       'start': '2026-02-09', 'finish': '2026-02-27', 'total_float_days': 0}]}
    p = build_presentation(m)
    assert p['tiles'][0] == {'label': 'CPLI', 'value': '99%'}         # from module score, not raw 0.99
    assert p['tiles'][3] == {'label': 'DCMA Target', 'value': '95%'}
    start_idx = [c['label'] for c in p['columns']].index('Start')
    assert p['rows'][0][start_idx] == {'text': '2026-02-09', 'cls': 'mut'}
    assert 'CPLI 99%' in p['verdict']


def test_cpli_not_computable():
    m = {'module': 'cpli', 'score': None, 'grade': None, 'pct': None,
         'kpis': {'cpli': None, 'computable': False, 'critical_path_length_days': None,
                  'project_total_float_days': None, 'target': 0.95, 'finish_milestone_id': None},
         'findings': []}
    p = build_presentation(m)
    assert p['tiles'][0] == {'label': 'CPLI', 'value': '—'}
    assert 'not computable' in p['verdict']


def test_circular_chain_joins_and_gate_verdict():
    clear = build_presentation({'module': 'circular', 'pct': 0.0,
                                'kpis': {'total_activities': 100, 'loops': 0}, 'findings': []})
    assert 'No circular logic' in clear['verdict']
    looped = build_presentation({'module': 'circular', 'pct': 2.0,
        'kpis': {'total_activities': 100, 'loops': 1, 'activities_in_loops': 3, 'longest_loop': 3, 'circular_pct': 3.0},
        'findings': [{'loop_index': 1, 'activity_count': 3, 'recommendation': 'Break one link',
                      'chain': [{'id': 'A'}, {'id': 'B'}, {'id': 'C'}, {'id': 'A'}]}]})
    chain_idx = [c['label'] for c in looped['columns']].index('Closing Chain')
    assert looped['rows'][0][chain_idx] == {'text': 'A → B → C → A', 'cls': 'mono'}
    assert 'block' in looped['verdict']


def test_unknown_module_uses_generic_fallback():
    p = build_presentation({'module': 'mystery', 'pct': 5.0, 'kpis': {'foo': 1, 'bar': 2},
                            'findings': [{'activity_id': 'X', 'activity_name': 'y', 'wbs_path': 'P',
                                          'severity': 'Low', 'recommendation': 'r'}]})
    assert [c['label'] for c in p['columns']] == \
        ['Activity ID', 'Activity Name', 'WBS Path', 'Severity', 'Recommendation']
    assert p['verdict'] == '5% of items flagged.'
    assert len(p['rows']) == 1


def test_short_wbs_keeps_last_levels():
    assert short_wbs('A > B > C > D > E') == 'C > D > E'
    assert short_wbs('') == ''


def test_scoring_descriptor_is_transparent():
    s = build_presentation(_open_ends())['scoring']   # 3 of 100 = 3% -> 97
    assert s['formula'] == 'Score = 100 − defect%'
    assert '3 of 100' in s['derivation']
    assert 'Score = 100 − 3% = 97' in s['derivation']
    assert 'Excellent' in s['bands'] and 'Critical' in s['bands']
    assert 'Metric 3' in s['benchmark']


def test_scoring_relationship_types_shows_fs_derivation():
    m = {'module': 'relationship_types', 'pct': 10.7, 'score': 89.3,
         'kpis': {'total_relationships': 2631, 'non_fs': 282, 'fs_pct': 89.3,
                  'ss_pct': 5.1, 'ff_pct': 0, 'sf_pct': 0}, 'findings': []}
    s = build_presentation(m)['scoring']
    assert '282 of 2,631' in s['derivation']
    assert 'not Finish-to-Start' in s['derivation']
    assert 'Score = 100 − 10.7% = 89.3' in s['derivation']
    assert 'FS ≥ 90%' in s['benchmark']         # DCMA benchmark, separate from the score


def test_cpli_scoring_has_its_own_formula():
    m = {'module': 'cpli', 'score': 99.0, 'pct': 1.0,
         'kpis': {'cpli': 0.99, 'computable': True, 'critical_path_length_days': 366,
                  'project_total_float_days': 4, 'target': 0.95, 'finish_milestone_id': 'A1130'},
         'findings': []}
    s = build_presentation(m)['scoring']
    assert 'CPLI' in s['formula'] and '(CPL + TF)' in s['formula']
    assert 'Metric 13' in s['benchmark']
