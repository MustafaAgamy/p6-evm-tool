"""Slice-2 Schedule Intelligence — activity-code dimensions (contract items C, D, F).

``dimensions.py`` has three jobs, all measured from the file, never from a dimension's
NAME:

  * de-duplicate exact/near-duplicate code dimensions so redundant coding never
    inflates confidence (item C);
  * pick the discipline dimension by measured coverage + partition quality, never by
    matching a name against a hard-coded word list (item D);
  * detect a location/zone axis STRUCTURALLY — the axis that partitions the schedule
    roughly orthogonally to the discipline axis — or report ``None`` (item F).
"""
from p6_evm.calendars import Calendar
from p6_evm.parser import ScheduleData
from p6_narrative.intel import build_context, discipline_of
from p6_narrative.intel.dimensions import (
    dedupe_dimensions, dimension_pairs, dimension_report, measured_discipline_dim,
    select_discipline_dim, select_location_axis,
)
from p6_narrative.sequence import pick_discipline_dim

from tests.test_intel_context import _act, _synthetic


def _blank():
    d = ScheduleData()
    d.calendars = {'C1': Calendar(object_id='C1', name='Cal', day_hours=8.0)}
    d.project = {'data_date': None}
    d.wbs = {'PRJ': {'name': 'Project', 'parent_object_id': None}}
    d.activities = {}
    d.relationships = []
    d.activity_code_types = []
    d.bac_by_activity = {}
    d.ac_by_activity = {}
    return d


def _activities_with_codes(n, dims):
    """``dims``: ``{dimension_name: fn(i) -> value|None}``, one row per index 0..n-1."""
    d = _blank()
    for i in range(n):
        oid = 'x%d' % i
        codes = {}
        for name, fn in dims.items():
            val = fn(i)
            if val is not None:
                codes[name] = val
        d.activities[oid] = _act(oid, 'Task %d' % i, 'PRJ', dur_hours=8.0, codes=codes)
    d.activity_code_types = sorted(dims)
    return d


# ── de-duplication (contract item C) ────────────────────────────────────────
def test_exact_duplicate_code_dimensions_collapse_into_one_evidence_class():
    d = _activities_with_codes(8, {
        'A': lambda i: 'X' if i % 2 == 0 else 'Y',
        'B': lambda i: 'X' if i % 2 == 0 else 'Y',        # byte-identical copy of A
        'C': lambda i: 'P' if i < 4 else 'Q',
    })
    ctx = build_context(d)
    report = dedupe_dimensions(ctx)
    assert report['dimensions'] == ['A', 'B', 'C']
    assert report['representatives'] == ['A', 'C']         # B collapsed into A
    classes = {c['representative']: c for c in report['classes']}
    assert classes['A']['exact_duplicates'] == ['B']
    assert classes['A']['near_duplicates'] == []
    collapsed = {c['dimension']: c for c in report['collapsed']}
    assert collapsed['B']['merged_into'] == 'A'
    assert collapsed['B']['relation'] == 'exact'


def test_near_duplicate_code_dimensions_are_grouped_without_being_called_exact():
    n = 20

    def trade(i):
        return 'X' if i % 2 == 0 else 'Y'

    def trade_alt(i):
        return None if i == 19 else trade(i)   # one row disagrees -> not byte-identical

    d = _activities_with_codes(n, {'RME-Trade': trade, 'RME-Alstom-Trade': trade_alt})
    ctx = build_context(d)
    report = dedupe_dimensions(ctx)
    assert report['representatives'] == ['RME-Alstom-Trade', 'RME-Trade']
    assert len(report['classes']) == 1
    cls = report['classes'][0]
    assert cls['representative'] == 'RME-Trade'             # shorter name wins
    assert cls['near_duplicates'] == ['RME-Alstom-Trade']
    assert cls['exact_duplicates'] == []
    assert report['near_duplicate_pairs']
    assert report['near_duplicate_pairs'][0]['agreement'] >= 0.9


def test_unrelated_dimensions_with_different_value_vocabularies_never_collapse():
    d = _activities_with_codes(8, {
        'Trade': lambda i: 'Civil' if i % 2 == 0 else 'Mechanical',
        'Zone': lambda i: 'Zone1' if i < 4 else 'Zone2',
    })
    ctx = build_context(d)
    report = dedupe_dimensions(ctx)
    assert report['representatives'] == ['Trade', 'Zone']
    assert len(report['classes']) == 2
    assert report['collapsed'] == []
    assert report['near_duplicate_pairs'] == []


# ── discipline selection by measured coverage (contract item D) ────────────
def test_select_discipline_dim_prefers_measured_coverage_over_a_name_matching_dimension():
    # 'Trade' matches the LEGACY name-hint list but only covers half the schedule;
    # 'XCode' matches no hint at all but covers every activity.
    trade = {0: 'Civil', 1: 'Mechanical', 2: 'Civil', 3: 'Mechanical'}.get

    def xcode(i):
        return 'C1' if i % 2 == 0 else 'C2'

    d = _activities_with_codes(8, {'Trade': trade, 'XCode': xcode})
    ctx = build_context(d)
    picked = select_discipline_dim(ctx)
    assert picked['selected'] == 'XCode'
    covers = {c['dimension']: c['coverage'] for c in picked['candidates']}
    assert covers['XCode'] > covers['Trade']
    # this is the OPPOSITE of what the legacy name-matching picker returns — the two
    # paths are deliberately not unified (see grouping.discipline_label's docstring)
    assert pick_discipline_dim(['Trade', 'XCode']) == 'Trade'
    assert measured_discipline_dim(ctx) == 'XCode'


def test_select_discipline_dim_rejects_an_identifier_and_a_constant_dimension():
    d = _activities_with_codes(6, {
        'SerialNo': lambda i: 'S%d' % i,        # one value per activity -> identifier
        'Constant': lambda i: 'Only',           # one value for everything -> partitions nothing
        'Real': lambda i: 'A' if i % 2 == 0 else 'B',
    })
    ctx = build_context(d)
    picked = select_discipline_dim(ctx)
    assert picked['selected'] == 'Real'
    rejected = {r['dimension']: r['reject_reason'] for r in picked['rejected']}
    assert 'SerialNo' in rejected and 'Constant' in rejected


def test_dimension_report_is_memoised_and_json_serialisable():
    import json
    ctx = build_context(_synthetic())
    r1 = dimension_report(ctx)
    r2 = dimension_report(ctx)
    assert r1 is r2                              # memoised by context identity
    assert json.loads(json.dumps(r1)) == r1


# ── location axis: structural orthogonality (contract item F) ──────────────
def test_select_location_axis_detects_a_structurally_orthogonal_dimension():
    # 2 disciplines x 3 zones, every combination present -> Zone crosses Trade
    disciplines_ = ['Civil', 'Mechanical']
    zones = ['Zone1', 'Zone2', 'Zone3']
    d = _activities_with_codes(12, {
        'Trade': lambda i: disciplines_[i % 2],
        'Zone': lambda i: zones[i % 3],
    })
    ctx = build_context(d)
    report = dimension_report(ctx)
    disc_labels = dict(dimension_pairs(ctx, 'Trade'))
    axis, candidates = select_location_axis(ctx, disc_labels, report, 'Trade')
    assert axis is not None
    assert axis['kind'] == 'code_dimension' and axis['dimension'] == 'Zone'
    assert axis['disciplines_per_location'] >= 2.0
    assert axis['locations_per_discipline'] >= 2.0
    assert any(c['dimension'] == 'Zone' for c in candidates)


def test_select_location_axis_reports_none_when_the_file_carries_no_orthogonal_axis():
    ctx = build_context(_synthetic())          # one code dimension, nothing to cross it with
    report = dimension_report(ctx)
    disc_labels = {oid: discipline_of(ctx, ctx.steps[oid]) for oid in ctx.steps}
    dim = report['discipline']['selected']
    axis, candidates = select_location_axis(ctx, disc_labels, report, dim)
    assert axis is None
    assert all(c['reject_reason'] for c in candidates)


def test_select_location_axis_rejects_a_hierarchical_sub_breakdown_of_discipline():
    # 'SubTrade' sits INSIDE 'Trade' (each SubTrade value belongs to exactly one Trade
    # value) -- a finer breakdown of the same axis, not an orthogonal location axis.
    d = _activities_with_codes(8, {
        'Trade': lambda i: 'Civil' if i % 2 == 0 else 'Mechanical',
        'SubTrade': lambda i: ('Civil-A' if i % 4 == 0 else 'Civil-B') if i % 2 == 0
                              else ('Mech-A' if i % 4 == 1 else 'Mech-B'),
    })
    ctx = build_context(d)
    report = dimension_report(ctx)
    disc_labels = dict(dimension_pairs(ctx, 'Trade'))
    axis, candidates = select_location_axis(ctx, disc_labels, report, 'Trade')
    assert axis is None
    rows = {c['dimension']: c for c in candidates if c['dimension'] == 'SubTrade'}
    assert rows['SubTrade']['reject_reason'] is not None
