"""Schedule Health roll-up — the weighted, context-aware overall score.

The locked structure (2026-08-12): nine sub-features summing to 100, merged rows
scoring the lower of their parts, circular logic as a gate rather than a weight.
"""
import pytest

from p6_audit.health import (SUB_FEATURES, schedule_health, status_for,
                             PROVISIONAL_ON_LOOP)


def _m(key, score, findings=None, **kw):
    """A minimal module result — only what the roll-up reads."""
    r = {'module': key, 'name': key, 'score': score, 'grade': 'x',
         'pct': round(100 - score, 1), 'kpis': {}, 'findings': findings or []}
    r.update(kw)
    return r


def _modules(**overrides):
    """All modules at 100 unless overridden — makes each test state one thing."""
    keys = ['hard_constraints', 'cpli', 'float', 'dangling', 'whole_day', 'leads',
            'negative_float', 'open_ends', 'relationship_types', 'high_duration']
    mods = {k: _m(k, 100.0) for k in keys}
    mods['circular'] = _m('circular', 100.0, blocking=False, kpis={'loops': 0})
    mods['out_of_sequence'] = _m('out_of_sequence', 40.0)   # not weighted — must be ignored
    for k, v in overrides.items():
        mods[k] = v
    return mods


def _row(health, key):
    return next(r for r in health['sub_features'] if r['key'] == key)


# ── the locked structure itself ────────────────────────────────────────────
def test_weights_are_the_locked_hundred():
    assert sum(s['weight'] for s in SUB_FEATURES) == 100
    assert len(SUB_FEATURES) == 9


def test_perfect_schedule_scores_100_and_is_ready():
    h = schedule_health(_modules())
    assert h['score'] == 100.0
    assert h['verdict'] == 'Ready to submit'
    assert h['ready'] is True
    assert h['blocking'] is False
    assert h['counts']['Pass'] == 9


def test_out_of_sequence_is_not_part_of_the_baseline_roll_up():
    """It needs actual progress, so it is a separate feature — a bad score there
    must not touch Schedule Health."""
    h = schedule_health(_modules())
    assert h['score'] == 100.0
    assert 'out_of_sequence' not in {k for r in h['sub_features'] for k in r['modules']}


# ── the arithmetic Ibrahim will hand-check ─────────────────────────────────
def test_overall_equals_the_hand_calculation():
    """Float 45 (wt 15) and Dangling 72 (wt 15), everything else perfect:
    45x.15 + 72x.15 + 70 = 6.75 + 10.8 + 70 = 87.55 -> 87.6"""
    h = schedule_health(_modules(float=_m('float', 45.0), dangling=_m('dangling', 72.0)))
    assert _row(h, 'float')['points'] == 6.8        # 45 x 15 / 100, one decimal
    assert _row(h, 'dangling')['points'] == 10.8
    assert h['score'] == pytest.approx(87.6, abs=0.05)
    assert h['verdict'] == 'Not ready to submit'
    assert h['ready'] is False


def test_sub_features_are_ordered_worst_first():
    h = schedule_health(_modules(float=_m('float', 45.0),
                                 relationship_types=_m('relationship_types', 88.0)))
    assert [r['key'] for r in h['sub_features']][:2] == ['float', 'relationship_types']


# ── merged sub-features score the LOWER part ───────────────────────────────
def test_merged_leads_and_negative_float_takes_the_lower_part():
    h = schedule_health(_modules(leads=_m('leads', 100.0),
                                 negative_float=_m('negative_float', 60.0)))
    row = _row(h, 'leads_negative_float')
    assert row['score'] == 60.0        # a clean Leads score cannot hide negative float
    assert row['driver'] == 'negative_float'
    assert row['modules'] == ['leads', 'negative_float']


# ── per-check targets ──────────────────────────────────────────────────────
def test_relationship_types_uses_the_dcma_fs_target():
    """FS >= 90% is the DCMA line, so 88% is Review — on the default 95/90 bands
    it would have read Critical."""
    assert status_for('relationship_types', 88.0) == 'Review'
    assert status_for('cpli', 88.0) == 'Critical'
    assert status_for('cpli', 94.0) == 'Review'
    assert status_for('cpli', 95.0) == 'Pass'


def test_checks_status_counts_match_the_donut():
    h = schedule_health(_modules(
        float=_m('float', 45.0), hard_constraints=_m('hard_constraints', 50.0),
        dangling=_m('dangling', 72.0), relationship_types=_m('relationship_types', 88.0),
        cpli=_m('cpli', 94.0), high_duration=_m('high_duration', 95.0),
        whole_day=_m('whole_day', 96.0), open_ends=_m('open_ends', 97.0)))
    assert h['counts'] == {'Pass': 4, 'Review': 2, 'Critical': 3, 'Not computed': 0}


# ── the circular gate ──────────────────────────────────────────────────────
def test_a_loop_blocks_and_marks_the_date_checks_provisional():
    h = schedule_health(_modules(
        circular=_m('circular', 50.0, blocking=True, kpis={'loops': 2})))
    assert h['blocking'] is True
    assert h['ready'] is False                  # nothing submits while P6 cannot F9
    assert h['verdict'] == 'Blocked'
    assert h['gate']['loops'] == 2
    provisional = {r['key'] for r in h['sub_features'] if r.get('provisional')}
    assert provisional == PROVISIONAL_ON_LOOP


def test_the_gate_never_scores_into_the_total():
    """Circular is a gate, not a weight — a terrible loop score must not move the
    number, only block it."""
    clean = schedule_health(_modules())
    looped = schedule_health(_modules(
        circular=_m('circular', 5.0, blocking=True, kpis={'loops': 1})))
    assert looped['score'] == clean['score'] == 100.0


# ── renormalisation when a check cannot be computed ────────────────────────
def test_uncomputable_check_redistributes_its_weight():
    """CPLI declares itself uncomputable on a file with no dated finish. Its 15
    must not score a free 100, and must not shrink the total either."""
    mods = _modules(float=_m('float', 50.0))
    mods['cpli'] = _m('cpli', 100.0, kpis={'computable': False})
    h = schedule_health(mods)

    cpli_row = _row(h, 'cpli')
    assert cpli_row['available'] is False
    assert cpli_row['points'] is None
    assert cpli_row['status'] == 'Not computed'
    assert h['weight_covered'] == 85            # 100 - CPLI's 15
    # float now carries 15/85 of the total: 50 x 17.6% = 8.8, rest perfect
    assert _row(h, 'float')['effective_weight'] == pytest.approx(17.6, abs=0.05)
    assert h['score'] == pytest.approx(91.2, abs=0.1)
    assert h['scored_count'] == 8


# ── where the problems are ─────────────────────────────────────────────────
def test_problem_areas_group_by_wbs_discipline():
    mods = _modules(open_ends=_m('open_ends', 80.0, findings=[
        {'wbs_path': 'Terminal > Civil > Foundations'},
        {'wbs_path': 'Terminal > Civil > Slabs'},
        {'wbs_path': 'Terminal > MEP > Ducting'},
    ]))
    areas = schedule_health(mods)['problem_areas']
    assert areas['total_findings'] == 3
    assert areas['areas'][0] == {'name': 'Civil', 'findings': 2, 'pct': 66.7}
    assert areas['areas'][1]['name'] == 'MEP'


def test_problem_areas_ignore_the_gate_and_undated_rows():
    """Loop chains carry no WBS and circular is not weighted — neither may inflate
    the discipline split."""
    mods = _modules(circular=_m('circular', 50.0, blocking=True, kpis={'loops': 1},
                                findings=[{'chain': [], 'loop_index': 1}]))
    assert schedule_health(mods)['problem_areas']['total_findings'] == 0


# ── fix these first ────────────────────────────────────────────────────────
def test_fix_first_ranks_by_points_won_back_not_by_score():
    """A weak check on a heavy weight beats a slightly weaker one on a light weight."""
    h = schedule_health(_modules(
        float=_m('float', 60.0, findings=[{'recommendation': 'Add the missing successors'}]),
        high_duration=_m('high_duration', 50.0)))
    first, second = h['fix_first'][0], h['fix_first'][1]
    assert first['key'] == 'float'          # 40 x 15 / 100 = 6.0 points back
    assert first['lift'] == 6.0
    assert first['recommendation'] == 'Add the missing successors'
    assert second['key'] == 'high_duration'  # 50 x 5 / 100 = 2.5, despite the worse score
    assert second['lift'] == 2.5


def test_fix_first_skips_perfect_checks():
    assert schedule_health(_modules())['fix_first'] == []


def test_fix_first_falls_back_when_findings_carry_no_fix_line():
    """Dangling words its advice as suggested_fix, and the CPLI driving path is a
    route rather than a defect list — neither may leave the line blank."""
    h = schedule_health(_modules(
        dangling=_m('dangling', 70.0, findings=[{'suggested_fix': 'Link to EX-1010'}]),
        cpli=_m('cpli', 60.0, findings=[{'note': 'On the driving/critical path'}])))
    by_key = {f['key']: f['recommendation'] for f in h['fix_first']}
    assert by_key['dangling'] == 'Link to EX-1010'          # the register's own wording
    assert by_key['cpli'].startswith('Recover the driving path')   # the check's default
