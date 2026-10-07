"""Owner comments 59 / 60 / 103 on Baseline Revision (handwritten sheets, 7 Oct 2026).

59  the Schedule-quality signals table is removed (screen, PDF / Word, Excel)
60  the Comparison ledger names every count: one count per row, added under Rev.01, removed
    under Rev.00, a "What it means" line, and the arithmetic printed where it closes
103 "critical" is P6's own Critical flag - every activity type, the project's critical float
    limit / Longest Path setting - so the counts equal P6's Critical filter
"""
import re

from p6_revcompare import compare as C
from p6_revcompare import exporters, xlsx_export

SUMMARY = {
    'activities0': 1022, 'activities1': 1503, 'net': 481, 'added': 524, 'removed': 43,
    'modified': 944, 'id_changes': 103, 'sequence': 3,
    'logic': {'total': 2187, 'added': 1497, 'removed': 562, 'type': 55, 'lag': 73},
    'critical0': 214, 'critical1': 410, 'cp_in': 295, 'cp_out': 99, 'cp_length_change_wd': -58,
    'float_moves': 789,
}
RELS = {'rev0': 1696, 'rev1': 2631}


def _by_label(rows):
    return {(r['group'], r['label']): r for r in rows}


def test_ledger_names_every_count():
    rows = C._ledger(SUMMARY, RELS)
    led = _by_label(rows)
    added = led[('Activities', 'Added — new in Rev.01')]
    removed = led[('Activities', 'Removed — deleted from Rev.00')]
    # the owner's example: 524 is ADDED (under Rev.01), 43 is REMOVED (under Rev.00)
    assert (added['rev0'], added['rev1'], added['change']) == (None, 524, '+524 added')
    assert (removed['rev0'], removed['rev1'], removed['change']) == (43, None, '−43 removed')
    assert led[('Activities', 'Modified — in both, with a change')]['change'] == '944 modified'
    assert led[('Activities', 'Activity ID changed')]['span'] == 'in both revisions'
    rel = led[('Relationships (logic)', 'Total relationships')]
    assert (rel['rev0'], rel['rev1'], rel['change'], rel['sub']) == (1696, 2631, '+935', False)
    assert led[('Relationships (logic)', 'Added — new in Rev.01')]['change'] == '+1,497 added'
    crit = led[('Critical path & float', 'Critical activities')]
    assert (crit['rev0'], crit['rev1'], crit['change']) == (214, 410, '+196')
    assert led[('Critical path & float', 'Became critical in Rev.01')]['change'] == '+295 entered'
    assert led[('Critical path & float', 'No longer critical in Rev.01')]['change'] == '−99 left'
    assert led[('Critical path & float', 'Critical path length')]['change'] == '−58 d shorter'
    # no row puts two different counts under the Rev.00 / Rev.01 headings, and each says what it means
    assert all(r['meaning'] and r['change'] for r in rows)
    assert not any('/' in r['label'] for r in rows)


def test_ledger_checks_print_only_arithmetic_that_closes():
    assert C._ledger_checks(SUMMARY, RELS) == [
        '1,022 + 524 added − 43 removed = 1,503 activities',
        '1,696 + 1,497 added − 562 removed = 2,631 relationships',
        '214 + 295 became critical − 99 no longer critical = 410 critical activities',
    ]
    off = dict(SUMMARY, added=500)                       # does not close -> not printed
    assert not any('activities' in c and 'critical' not in c for c in C._ledger_checks(off, RELS))


def test_critical_is_p6s_own_flag():
    class D:                                             # the parser sets is_critical the P6 way
        activities = {
            1: {'id': 'TASK', 'task_type': 'TaskDependent', 'total_float_days': 0.0, 'is_critical': True},
            2: {'id': 'MS', 'task_type': 'FinishMilestone', 'total_float_days': 0.0, 'is_critical': True},
            3: {'id': 'LIMIT', 'task_type': 'TaskDependent', 'total_float_days': 0.5, 'is_critical': True},
            4: {'id': 'DONE', 'task_type': 'TaskDependent', 'total_float_days': 0.0, 'is_critical': False},
            5: {'id': 'FREE', 'task_type': 'TaskDependent', 'total_float_days': 12.0, 'is_critical': False},
        }
    # milestones count; an activity inside the project's critical float limit counts; one P6
    # does not flag (completed) does not - exactly P6's Critical filter
    assert C._critical_codes(D) == {'TASK', 'MS', 'LIMIT'}
    assert C._band(D.activities[3]) == 'crit' and C._band(D.activities[4]) == 'near'
    assert C._band(D.activities[5]) == 'safe' and C._band({'total_float_days': None}) is None


def test_report_shows_the_ledger_and_no_quality_signals_table():
    report = {'ledger': C._ledger(SUMMARY, RELS), 'ledger_checks': C._ledger_checks(SUMMARY, RELS),
              'quality': {'negative_float': {'rev0': 1, 'rev1': 2}, 'open_ends': {'rev0': 0, 'rev1': 0},
                          'hard_constraints': {'rev0': 0, 'rev1': 0}, 'leads': {'rev0': 0, 'rev1': 0}}}
    html = exporters._ledger(report)
    assert 'What it means' in html and '+524 added' in html and '−43 removed' in html
    assert 'In Rev.01 only; not in Rev.00.' in html
    assert '1,022 + 524 added − 43 removed = 1,503 activities' in html
    assert not hasattr(exporters, '_redflags')
    src = open(exporters.__file__, encoding='utf-8').read() + open(xlsx_export.__file__, encoding='utf-8').read()
    assert 'Schedule-quality signals' not in src
    js = open('ui/modules/revcompare.js', encoding='utf-8').read()
    assert 'Schedule-quality signals' not in js and 'rc-ledger' in js
    blocks = xlsx_export._summary_blocks(report)
    led = next(b for b in blocks if b['title'] == 'Comparison ledger')
    assert led['headers'] == ['Group', 'Measure', 'Rev.00', 'Rev.01', 'Change', 'What it means']
    row = next(r for r in led['rows'] if 'Added' in r[1] and r[0] == 'Activities')
    assert row[2:5] == ['—', '524', '+524 added']
    assert not any('quality' in b['title'].lower() for b in blocks)
