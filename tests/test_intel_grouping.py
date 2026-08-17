"""Slice-1 Schedule Intelligence — grouping (single source of truth).

discipline_of / package_of must be non-empty, stable, deterministic, and cover 100%
of the step activities. Discipline uses the Type-of-Works code when present, else the
adaptive WBS major branch. Project-agnostic — labels come from the file.
"""
from pathlib import Path

from p6_evm.parser import ScheduleData, parse_file
from p6_evm.calendars import Calendar
from p6_narrative.intel import (
    build_context, discipline_of, package_of, disciplines, packages,
)

from tests.test_intel_context import _synthetic, _act

FIXTURE = Path(__file__).parent / 'fixtures' / 'minimal.xml'


def test_discipline_from_type_of_works_code_when_present():
    ctx = build_context(_synthetic(with_codes=True))
    assert discipline_of(ctx, ctx.steps['a1']) == 'Civil'
    assert discipline_of(ctx, ctx.steps['a3']) == 'Mechanical'


def test_discipline_falls_back_to_major_wbs_branch_without_codes():
    ctx = build_context(_synthetic(with_codes=False))
    # PILE lives under the CIV major branch -> "Civil"; CONV under MEC -> "Mechanical"
    assert discipline_of(ctx, ctx.steps['a1']) == 'Civil'
    assert discipline_of(ctx, ctx.steps['a3']) == 'Mechanical'


def test_package_is_leaf_wbs_node_name():
    ctx = build_context(_synthetic())
    assert package_of(ctx, ctx.steps['a1']) == 'Pile'
    assert package_of(ctx, ctx.steps['a2']) == 'Pile'
    assert package_of(ctx, ctx.steps['a3']) == 'Conveyor'


def test_every_step_maps_to_a_discipline_and_package_100pct():
    for ctx in (build_context(parse_file(str(FIXTURE))),
                build_context(_synthetic()),
                build_context(_synthetic(with_codes=False))):
        covered = 0
        for oid, act in ctx.steps.items():
            disc = discipline_of(ctx, act)
            pkg = package_of(ctx, act)
            assert disc and isinstance(disc, str)
            assert pkg and isinstance(pkg, str)
            covered += 1
        assert covered == len(ctx.steps)
        # partitions cover exactly the steps, nothing lost or duplicated
        assert sum(len(v) for v in disciplines(ctx).values()) == len(ctx.steps)
        assert sum(len(v) for v in packages(ctx).values()) == len(ctx.steps)


def test_partitions_are_deterministic_and_stable():
    d = _synthetic()
    ctx = build_context(d)
    assert dict(disciplines(ctx)) == dict(disciplines(build_context(d)))
    assert dict(packages(ctx)) == dict(packages(build_context(d)))
    # discipline partition for the coded synthetic
    assert dict(disciplines(ctx)) == {'Civil': ['a1', 'a2'], 'Mechanical': ['a3']}


def test_general_fallback_when_wbs_missing_and_no_code():
    d = ScheduleData()
    d.calendars = {'C1': Calendar(object_id='C1', name='Cal', day_hours=8.0)}
    d.project = {'data_date': None}
    d.wbs = {}                       # no WBS tree at all
    d.activities = {'x': _act('x', 'Orphan Task', 'MISSING')}
    d.activity_code_types = []
    d.relationships = []
    ctx = build_context(d)
    assert discipline_of(ctx, ctx.steps['x']) == 'General'
    assert package_of(ctx, ctx.steps['x']) == 'General'
