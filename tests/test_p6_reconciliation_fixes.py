"""Final test — "all results in the tool match P6" (owner instruction, 2 Oct 2026).

The values P6 itself stores in the export file were read independently and compared with what
each feature reports (Grain Bulk, Saint Gobain, Alstom).  Three differences were found and
fixed; these tests pin them.
"""
from datetime import datetime

from p6_compare.model import _rels_by_pair, rel_count


class _Data:
    def __init__(self, acts, rels):
        self.activities = acts
        self.relationships = rels


def _acts():
    return {1: {'id': 'A', 'name': 'a'}, 2: {'id': 'B', 'name': 'b'}, 3: {'id': 'C', 'name': 'c'}}


def test_two_links_between_the_same_pair_are_two_relationships():
    # P6 allows an SS and an FF between the same two activities.  The pair map kept one and the
    # Baseline Revision "Total relationships" read 2,589 where P6 holds 2,631.
    d = _Data(_acts(), [{'pred_id': 1, 'succ_id': 2, 'type': 'FF', 'lag_days': 0, 'lag_hours': 0},
                        {'pred_id': 1, 'succ_id': 2, 'type': 'SS', 'lag_days': 0, 'lag_hours': 0},
                        {'pred_id': 2, 'succ_id': 3, 'type': 'FS', 'lag_days': 1, 'lag_hours': 8}])
    rels = _rels_by_pair(d)
    assert len(rels) == 2 and rel_count(rels) == 3
    assert rels[('A', 'B')]['links'] == 2 and rels[('A', 'B')]['multi'] == 'FF+0 + SS+0'
    assert rels[('B', 'C')]['links'] == 1 and rels[('B', 'C')]['multi'] == ''


def test_a_change_to_the_second_link_of_a_pair_is_a_change():
    from p6_revcompare.compare import _logic_stats
    pair = lambda ff_h: {('A', 'B'): {'type': 'SS', 'lag_days': 0, 'lag_hours': 0, 'links': 2,
                                      'all_links': (('FF', ff_h), ('SS', 0.0)),
                                      'link_days': (('FF', ff_h / 8.0), ('SS', 0.0))}}
    base, same, moved = pair(0.0), pair(0.0), pair(16.0)       # moved: the FF got a 2-day lag

    class M:
        def __init__(self, b, u):
            self.baseline_rels, self.update_rels = b, u
    assert _logic_stats(M(base, same))['total'] == 0
    # counted per P6 link (comment 44): the FF's lag changed — one lag change, not a type change
    st = _logic_stats(M(base, moved))
    assert (st['lag'], st['type'], st['total']) == (1, 0, 1)


def test_baseline_revision_quality_counts_relationships_as_p6_does():
    from p6_revcompare.quality import build_quality

    class M:
        baseline_by_code = {'A': {'id': 'A'}, 'B': {'id': 'B'}}
        update_by_code = {'A': {'id': 'A'}, 'B': {'id': 'B'}}
        baseline_rels = {('A', 'B'): {'type': 'SS', 'lag_days': 0, 'links': 2}}
        update_rels = {('A', 'B'): {'type': 'SS', 'lag_days': 0, 'links': 1}}
    q = build_quality(None, None, M(), None)
    assert q['total_rels'] == {'rev0': 2, 'rev1': 1}


def test_baseline_revision_dates_are_the_dates_p6_shows():
    # a revision that already carries progress: P6's Finish column is the ACTUAL finish
    from p6_revcompare.dates import _p6_finish, _p6_start
    a = {'planned_start': datetime(2025, 5, 10), 'planned_finish': datetime(2025, 7, 17),
         'actual_start': datetime(2025, 5, 13), 'actual_finish': datetime(2025, 7, 19)}
    assert _p6_start(a) == datetime(2025, 5, 13) and _p6_finish(a) == datetime(2025, 7, 19)
    b = {'planned_start': datetime(2025, 5, 10), 'planned_finish': datetime(2025, 7, 17)}
    assert _p6_start(b) == datetime(2025, 5, 10) and _p6_finish(b) == datetime(2025, 7, 17)


def test_consultant_review_shows_the_actual_date_of_an_achieved_milestone():
    import inspect
    from p6_compare import report
    src = inspect.getsource(report)
    assert "u.get('actual_finish') or u.get('planned_finish') or u.get('remaining_early_finish')" in src
    assert "b.get('actual_finish') or b.get('planned_finish')" in src
