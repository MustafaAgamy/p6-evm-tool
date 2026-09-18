"""Slice-2 Schedule Intelligence — repeated work-front detection.

``detect_repeats`` must find repeated work FRONTS (silos, floors, chainage segments,
equipment trains, bridge spans) that share the same internal work sequence, so the
narrative can say "repeated across N fronts; the typical sequence is A -> B -> C"
instead of repeating one paragraph N times.

What this slice must guarantee:
  * grouping comes from CONTEXT (WBS position, activity codes, logic, durations) —
    NEVER from identical activity names;
  * everything is keyed on ``object_id`` (P6 exports can carry the same activity CODE
    twice), so duplicate codes can never double-count;
  * nothing is ever dropped — every step object_id appears exactly once across
    ``groups`` + ``singletons`` and ``coverage.pct`` is exactly 100.0;
  * pure, deterministic and JSON-serialisable — same input twice yields
    byte-identical output;
  * project-agnostic — every label is derived from the file.
"""
import json
from pathlib import Path

import pytest

from p6_evm.calendars import Calendar
from p6_evm.parser import ScheduleData, parse_file
from p6_narrative.intel import build_context, build_profile, detect_repeats
from p6_narrative.intel.hierarchy import DedupIntegrityError, assert_coverage, prove_coverage
from p6_narrative.intel.signals import QUANTITY_UNAVAILABLE_REASON, quantity_signal

from tests.test_intel_context import _synthetic, _act

FIXTURE = Path(__file__).parent / 'fixtures' / 'minimal.xml'

# (id segment, name word) for the repeating trade cycle used by the fixtures below
_CYCLE = (('EXC', 'Excavate'), ('BLD', 'Blinding'), ('RFT', 'Rebar'), ('CON', 'Concrete'))


# ── synthetic schedule builders ─────────────────────────────────────────────
def _blank(day_hours=8.0):
    d = ScheduleData()
    d.calendars = {'C1': Calendar(object_id='C1', name='Cal', day_hours=day_hours)}
    d.project = {'data_date': None}
    d.wbs = {}
    d.activities = {}
    d.relationships = []
    d.activity_code_types = []
    d.bac_by_activity = {}
    d.ac_by_activity = {}
    return d


def _fronts(n=5, skip=(), doubled=(), cycle=False, dup_codes=False, link_fronts=False):
    """``n`` sibling WBS fronts under one parent, each an FS chain of the same steps.

    ``skip`` / ``doubled`` are ``(front_index, segment)`` pairs. ``cycle`` adds a
    back-edge inside front 1. ``dup_codes`` gives every front the SAME activity codes
    (distinct object_ids) — the duplicate-code export hazard.
    """
    d = _blank()
    d.wbs['PRJ'] = {'name': 'Project', 'parent_object_id': None}
    d.wbs['GRP'] = {'name': 'Storage Bins', 'parent_object_id': 'PRJ'}
    heads, tails = [], []
    for u in range(1, n + 1):
        wid = 'GRP%d' % u
        d.wbs[wid] = {'name': 'Bin %d' % u, 'parent_object_id': 'GRP'}
        chain = []
        for seg, word in _CYCLE:
            if (u, seg) in skip:
                continue
            oid = 'o-%d-%s' % (u, seg)
            hours = 40.0 * (2.0 if (u, seg) in doubled else 1.0)
            act = _act(oid, '%s Bin %d' % (word, u), wid, dur_hours=hours)
            act['id'] = ('DUP-%s' % seg) if dup_codes else ('B%d-%s-01' % (u, seg))
            d.activities[oid] = act
            chain.append(oid)
        for a, b in zip(chain, chain[1:]):
            d.relationships.append({'pred_id': a, 'succ_id': b, 'type': 'FS', 'lag_days': 0.0})
        if cycle and u == 1:
            d.relationships.append({'pred_id': chain[-1], 'succ_id': chain[0],
                                    'type': 'FS', 'lag_days': 0.0})
        heads.append(chain[0])
        tails.append(chain[-1])
    if link_fronts:                      # front i hands over to front i+1
        for a, b in zip(tails, heads[1:]):
            d.relationships.append({'pred_id': a, 'succ_id': b, 'type': 'FS', 'lag_days': 0.0})
    return d


def _two_work_types():
    """Two genuinely different work types, each repeated, under DIFFERENT WBS parents."""
    d = _blank()
    d.wbs['PRJ'] = {'name': 'Project', 'parent_object_id': None}
    families = (
        ('GRP', 'Storage Bins', 'Bin', ('Excavate', 'Rebar', 'Concrete')),
        ('ELE', 'Cable Routes', 'Route', ('Pull', 'Terminate', 'Test')),
    )
    for pid, pname, unit_word, words in families:
        d.wbs[pid] = {'name': pname, 'parent_object_id': 'PRJ'}
        for u in range(1, 4):
            wid = '%s%d' % (pid, u)
            d.wbs[wid] = {'name': '%s %d' % (unit_word, u), 'parent_object_id': pid}
            chain = []
            for i, word in enumerate(words):
                oid = '%s-%d-%d' % (pid, u, i)
                d.activities[oid] = _act(oid, '%s %s %d' % (word, unit_word, u), wid,
                                         dur_hours=24.0)
                chain.append(oid)
            for a, b in zip(chain, chain[1:]):
                d.relationships.append({'pred_id': a, 'succ_id': b,
                                        'type': 'FS', 'lag_days': 0.0})
    return d


def _opaque_names(n=4):
    """Meaningless activity names ("Activity 1010") but clean WBS siblings + ID segments."""
    d = _blank()
    d.wbs['PRJ'] = {'name': 'Project', 'parent_object_id': None}
    d.wbs['GRP'] = {'name': 'Bored Piles', 'parent_object_id': 'PRJ'}
    for u in range(1, n + 1):
        wid = 'GRP%d' % u
        d.wbs[wid] = {'name': 'Group %d' % u, 'parent_object_id': 'GRP'}
        chain = []
        for i, seg in enumerate(('EXC', 'RFT', 'CON')):
            oid = 'p-%d-%s' % (u, seg)
            act = _act(oid, 'Activity %d' % (1000 * u + 10 * i), wid, dur_hours=24.0)
            act['id'] = 'P%d-%s-01' % (u, seg)
            d.activities[oid] = act
            chain.append(oid)
        for a, b in zip(chain, chain[1:]):
            d.relationships.append({'pred_id': a, 'succ_id': b, 'type': 'FS', 'lag_days': 0.0})
    return d


_TRADE_BY_SEG = {'EXC': 'Civil', 'BLD': 'Civil', 'RFT': 'Civil', 'CON': 'Concrete'}


def _add_trade_codes(d, dup=False):
    """Tag every activity with a 'Trade' code by STEP ROLE — constant across every
    front (a legitimate discipline-like dimension, unlike a per-front marker), plus an
    exact-duplicate 'Trade2' when ``dup``.
    """
    for oid, act in d.activities.items():
        seg = oid.rsplit('-', 1)[-1]
        trade = _TRADE_BY_SEG.get(seg)
        if trade:
            codes = dict(act.get('activity_codes') or {})
            codes['Trade'] = trade
            if dup:
                codes['Trade2'] = trade
            act['activity_codes'] = codes
    d.activity_code_types = ['Trade', 'Trade2'] if dup else ['Trade']
    return d


def _unrelated_same_name_activities(n=6):
    """``n`` activities sharing ONE identical name, scattered under ``n`` unrelated WBS
    nodes, no shared code dimension, no relationships at all — nothing agrees except the
    literal name. Used to prove name equality alone can never establish a work front.
    """
    d = _blank()
    d.wbs['PRJ'] = {'name': 'Project', 'parent_object_id': None}
    for i in range(1, n + 1):
        wid = 'ISOLATED%d' % i
        d.wbs[wid] = {'name': 'Area %d' % i, 'parent_object_id': 'PRJ'}
        oid = 'iso-%d' % i
        act = _act(oid, 'Plain Concrete', wid, dur_hours=24.0)
        act['id'] = 'MISC-%d' % (100 + i * 37)      # no shared delimiter structure either
        d.activities[oid] = act
    return d


def _alstom_regime_fronts(n=4):
    """Instance baked into the NAME SUFFIX (every activity name is distinct), but WBS
    position, step composition and internal logic agree across fronts — the Alstom
    regime (92% of its real names carry a trailing zone/building suffix).
    """
    d = _blank()
    d.wbs['PRJ'] = {'name': 'Project', 'parent_object_id': None}
    d.wbs['GRP'] = {'name': 'Submittal Packages', 'parent_object_id': 'PRJ'}
    for u in range(1, n + 1):
        wid = 'GRP%d' % u
        d.wbs[wid] = {'name': 'Package %d' % u, 'parent_object_id': 'GRP'}
        chain = []
        for seg, word in _CYCLE:
            oid = 'al-%d-%s' % (u, seg)
            act = _act(oid, '%s - Zone %d - Building %d' % (word, u, u + 10), wid,
                       dur_hours=16.0)
            act['id'] = 'A%d-%s' % (u, seg)
            d.activities[oid] = act
            chain.append(oid)
        for a, b in zip(chain, chain[1:]):
            d.relationships.append({'pred_id': a, 'succ_id': b, 'type': 'FS', 'lag_days': 0.0})
    return d


def _sng_regime_fronts(n=5):
    """Names are IDENTICAL across every front (no per-front suffix at all); the instance
    marker lives ONLY in the WBS node / activity id — the Saint-Gobain regime ('Plain
    Concrete' x14 across 14 different WBS nodes, elevation the only in-name marker).
    """
    d = _blank()
    d.wbs['PRJ'] = {'name': 'Project', 'parent_object_id': None}
    d.wbs['GRP'] = {'name': 'Foundations', 'parent_object_id': 'PRJ'}
    for u in range(1, n + 1):
        wid = 'GRP%d' % u
        d.wbs[wid] = {'name': 'Footing %d' % u, 'parent_object_id': 'GRP'}
        chain = []
        for seg, word in _CYCLE:
            oid = 'sg-%d-%s' % (u, seg)
            act = _act(oid, word, wid, dur_hours=16.0)      # no per-front suffix at all
            act['id'] = 'S-%s-%d' % (seg, u)
            d.activities[oid] = act
            chain.append(oid)
        for a, b in zip(chain, chain[1:]):
            d.relationships.append({'pred_id': a, 'succ_id': b, 'type': 'FS', 'lag_days': 0.0})
    return d


# ── shared invariant ────────────────────────────────────────────────────────
def _assert_lossless(ctx, out):
    """Every step object_id appears EXACTLY once across groups + singletons."""
    seen = []
    for g in out['groups']:
        for inst in g['instances']:
            seen.extend(inst['activity_ids'])
    seen.extend(out['singletons'])
    assert len(seen) == len(set(seen)), 'an object_id appeared twice'
    assert set(seen) == set(ctx.steps), 'groups + singletons do not equal the steps'
    cov = out['coverage']
    assert cov['steps'] == len(ctx.steps)
    assert cov['in_groups'] + cov['singletons'] == len(ctx.steps)
    assert cov['pct'] == 100.0


# ── tests ───────────────────────────────────────────────────────────────────
def test_five_identical_fronts_collapse_to_one_group_in_logic_order():
    ctx = build_context(_fronts(n=5))
    out = detect_repeats(ctx)
    assert out['axis'] == 'wbs_siblings'
    assert len(out['groups']) == 1
    g = out['groups'][0]
    assert g['instance_count'] == 5
    assert g['activity_count'] == 20
    assert g['label'] == 'Storage Bins'              # derived from the file, no keywords
    assert g['discipline'] == 'Storage Bins'
    assert g['wbs_parent_id'] == 'GRP'
    # consensus sequence follows the INTERNAL LOGIC, not the alphabet, not the dates
    assert [s['step'] for s in g['consensus_sequence']] == \
        ['excavate', 'blinding', 'rebar', 'concrete']
    assert all(s['instances'] == 5 for s in g['consensus_sequence'])
    assert all(s['median_days'] == 5.0 for s in g['consensus_sequence'])   # 40h / 8h
    # identical fronts deviate in nothing
    assert [i['deviations'] for i in g['instances']] == [[], [], [], [], []]
    assert [i['unit_label'] for i in g['instances']] == \
        ['Bin 1', 'Bin 2', 'Bin 3', 'Bin 4', 'Bin 5']
    assert out['singletons'] == []
    assert 0.0 <= g['confidence'] <= 1.0
    _assert_lossless(ctx, out)


def test_missing_step_and_doubled_duration_stay_grouped_and_are_reported():
    d = _fronts(n=5, skip=((3, 'BLD'),), doubled=((4, 'RFT'),), link_fronts=True)
    ctx = build_context(d)
    out = detect_repeats(ctx)
    assert len(out['groups']) == 1
    g = out['groups'][0]
    assert g['instance_count'] == 5
    assert g['activity_count'] == 19                # front 3 lost one step
    dev = {i['unit_label']: i['deviations'] for i in g['instances']}
    # front 1 is the only one nobody hands over to
    assert dev['Bin 1'] == ['different predecessor hand-off: concrete']
    assert dev['Bin 2'] == []
    assert dev['Bin 3'] == ['internal logic FS0x2 vs typical FS0x3',
                            'missing step: blinding']
    assert dev['Bin 4'] == ['duration outlier: rebar 10 d vs typical 5 d']
    # front 5 is symmetrically the only one nobody hands over TO the next front
    assert dev['Bin 5'] == ['different successor hand-off: excavate']
    # the consensus still carries blinding, seen in 4 of the 5 fronts
    seq = {s['step']: s for s in g['consensus_sequence']}
    assert [s['step'] for s in g['consensus_sequence']] == \
        ['excavate', 'blinding', 'rebar', 'concrete']
    assert seq['blinding']['instances'] == 4
    assert seq['rebar']['median_days'] == 5.0       # the doubled front is the outlier
    _assert_lossless(ctx, out)


def test_two_different_work_types_under_different_parents_are_never_merged():
    ctx = build_context(_two_work_types())
    out = detect_repeats(ctx)
    assert len(out['groups']) == 2
    labels = sorted(g['label'] for g in out['groups'])
    assert labels == ['Cable Routes', 'Storage Bins']
    for g in out['groups']:
        assert g['instance_count'] == 3
        assert g['activity_count'] == 9
        oids = [o for i in g['instances'] for o in i['activity_ids']]
        prefixes = {o.split('-')[0] for o in oids}
        assert len(prefixes) == 1, 'a group mixed two unrelated work types'
    # and the two groups keep their own consensus sequences
    seqs = sorted(tuple(s['step'] for s in g['consensus_sequence']) for g in out['groups'])
    assert seqs == [('excavate', 'rebar', 'concrete'), ('pull', 'terminate', 'test')]
    _assert_lossless(ctx, out)


def test_meaningless_names_still_group_via_the_fallback_ladder():
    ctx = build_context(_opaque_names(n=4))
    out = detect_repeats(ctx)
    # names carry no repeatable token at all -> the ladder drops to the ID segment
    assert out['step_key_basis'] == 'id_segment'
    assert out['axis'] == 'wbs_siblings'
    assert len(out['groups']) == 1
    g = out['groups'][0]
    assert g['instance_count'] == 4
    assert g['activity_count'] == 12
    assert [s['step'] for s in g['consensus_sequence']] == ['EXC', 'RFT', 'CON']
    assert g['label'] == 'Bored Piles'              # no shared token -> WBS parent name
    _assert_lossless(ctx, out)


def test_grouping_is_not_name_equality():
    d = _fronts(n=5)
    names = [a['name'] for a in d.activities.values()]
    assert len(names) == len(set(names)) == 20, 'fixture must have 20 DISTINCT names'
    ctx = build_context(d)
    out = detect_repeats(ctx)
    # 20 unique names, yet context alone collapses them into one repeated front
    assert len(out['groups']) == 1 and out['groups'][0]['instance_count'] == 5


def test_schedule_without_repetition_yields_only_singletons():
    for d in (parse_file(str(FIXTURE)), _synthetic()):
        ctx = build_context(d)
        out = detect_repeats(ctx)
        assert out['groups'] == []
        assert out['singletons'] == sorted(ctx.steps)
        assert out['coverage']['in_groups'] == 0
        _assert_lossless(ctx, out)


def test_output_is_deterministic_byte_for_byte():
    for d in (_fronts(n=5), _fronts(n=5, skip=((3, 'BLD'),), doubled=((4, 'RFT'),),
                                    link_fronts=True),
              _two_work_types(), _opaque_names(), _synthetic()):
        a = json.dumps(detect_repeats(build_context(d)), sort_keys=True)
        b = json.dumps(detect_repeats(build_context(d)), sort_keys=True)
        assert a == b


def test_output_is_json_serialisable():
    out = detect_repeats(build_context(_fronts(n=5)))
    assert json.loads(json.dumps(out)) == out


def test_duplicate_activity_codes_never_double_count():
    d = _fronts(n=5, dup_codes=True)
    codes = [a['id'] for a in d.activities.values()]
    assert len(set(codes)) == 4 and len(codes) == 20, 'fixture must reuse activity CODES'
    ctx = build_context(d)
    out = detect_repeats(ctx)
    assert len(out['groups']) == 1
    assert out['groups'][0]['activity_count'] == 20      # 20 object_ids, 4 codes
    _assert_lossless(ctx, out)                            # exactly 100%, no duplicates


def test_relationship_cycle_inside_a_front_is_cycle_safe_and_deterministic():
    d = _fronts(n=5, cycle=True)
    ctx = build_context(d)
    out = detect_repeats(ctx)                             # must not hang
    _assert_lossless(ctx, out)
    again = detect_repeats(build_context(_fronts(n=5, cycle=True)))
    assert json.dumps(out, sort_keys=True) == json.dumps(again, sort_keys=True)
    # the cyclic front still reports a full, ordered step list
    inst = {i['unit_label']: i for g in out['groups'] for i in g['instances']}
    assert len(inst['Bin 1']['activity_ids']) == 4
    assert len(inst['Bin 1']['steps']) == 4


def test_empty_and_single_activity_schedules_do_not_crash():
    empty = build_context(_blank())
    out = detect_repeats(empty)
    assert out['groups'] == [] and out['singletons'] == []
    cov = out['coverage']
    # non-circular proof (contract item G): checked field-by-field, not by construction
    assert cov['steps'] == 0 and cov['in_groups'] == 0 and cov['singletons'] == 0
    assert cov['pct'] == 100.0 and cov['exact'] is True
    assert cov['duplicate_ids'] == [] and cov['missing_ids'] == [] and cov['foreign_ids'] == []
    assert out['axis'] is None

    one = _blank()
    one.wbs['PRJ'] = {'name': 'Project', 'parent_object_id': None}
    one.activities = {'x': _act('x', 'Lonely Task', 'PRJ', dur_hours=8.0)}
    ctx = build_context(one)
    out = detect_repeats(ctx)
    assert out['groups'] == [] and out['singletons'] == ['x']
    _assert_lossless(ctx, out)


def test_axis_scores_are_recorded_for_every_axis_for_traceability():
    out = detect_repeats(build_context(_fronts(n=5)))
    assert set(out['axis_scores']) == {'wbs_siblings', 'code_dimension',
                                       'id_segment', 'name_token'}
    for name, score in out['axis_scores'].items():
        assert isinstance(score, float) and 0.0 <= score <= 1.0
    # the winner is the highest-scoring axis (ties broken by the fixed order)
    assert out['axis_scores'][out['axis']] == max(out['axis_scores'].values())


def test_params_default_to_the_profile_and_are_echoed_back():
    ctx = build_context(_fronts(n=5))
    prof = build_profile(ctx)
    assert detect_repeats(ctx)['params'] == prof['params']
    # an explicit override wins and is echoed
    tight = dict(prof['params'], min_instances=99)
    out = detect_repeats(ctx, params=tight)
    assert out['params']['min_instances'] == 99
    assert out['groups'] == []                       # 5 fronts can't satisfy 99
    _assert_lossless(ctx, out)


def test_milestones_loe_and_summary_are_not_treated_as_steps():
    d = _fronts(n=5)
    d.wbs['ANC'] = {'name': 'Anchors', 'parent_object_id': 'PRJ'}
    d.activities['ms'] = _act('ms', 'Bins Complete', 'ANC', tt='FinishMilestone')
    d.activities['lo'] = _act('lo', 'Supervision Bins', 'ANC', tt='LOE', dur_hours=800.0)
    ctx = build_context(d)
    out = detect_repeats(ctx)
    covered = [o for g in out['groups'] for i in g['instances'] for o in i['activity_ids']]
    assert 'ms' not in covered and 'lo' not in covered
    assert 'ms' not in out['singletons'] and 'lo' not in out['singletons']
    _assert_lossless(ctx, out)


# ── the five-level hierarchy (contract item B) ──────────────────────────────
def test_all_five_hierarchy_levels_are_present_and_addressable_with_object_ids():
    d = _fronts(n=5, skip=((3, 'BLD'),), doubled=((4, 'RFT'),), link_fronts=True)
    ctx = build_context(d)
    out = detect_repeats(ctx)
    h = out['hierarchy']
    assert set(h['level_names']) == {'1', '2', '3', '4', '5'}
    assert h['level_names']['1'] == 'repeated_activity'
    assert h['level_names']['2'] == 'activity_family'
    assert h['level_names']['3'] == 'repeated_work_front'
    assert h['level_names']['4'] == 'typical_sequence'
    assert h['level_names']['5'] == 'project_specific_exception'
    assert set(h['level_keys'].values()) == {
        'activities', 'families', 'fronts', 'typical_sequences', 'exceptions'}

    # level 1 - every step activity is addressable, grouped or not
    assert set(h['activities']) == set(ctx.steps)
    for oid, row in h['activities'].items():
        assert row['object_id'] == oid

    # level 2 - families carry the object_ids that belong to them
    assert h['families'], 'expected at least one activity family'
    for fam in h['families']:
        assert fam['activity_ids'], 'a family with no object_ids cannot be traced back'
        assert all(o in ctx.steps for o in fam['activity_ids'])

    # level 3 - fronts carry the object_ids that belong to them
    assert h['fronts']
    for front in h['fronts']:
        assert front['activity_ids']
        assert all(o in ctx.steps for o in front['activity_ids'])

    # level 4 - typical sequence: consensus steps with median duration + front count
    assert h['typical_sequences']
    for seq in h['typical_sequences']:
        assert seq['steps']
        for step in seq['steps']:
            assert 'median_days' in step and 'fronts' in step

    # level 5 - every exception carries the object_ids it refers to
    assert h['exceptions'], 'this fixture has engineered deviations'
    for exc in h['exceptions']:
        assert exc['activity_ids'], 'an exception with no object_ids is not traceable'

    assert h['counts']['activities'] == len(h['activities'])
    assert h['counts']['families'] == len(h['families'])
    assert h['counts']['fronts'] == len(h['fronts'])
    assert h['counts']['typical_sequences'] == len(h['typical_sequences'])
    assert h['counts']['exceptions'] == len(h['exceptions'])
    _assert_lossless(ctx, out)


# ── name equality is one signal, never sufficient alone (contract item A) ──
def test_name_equality_alone_forms_no_group_when_wbs_codes_logic_and_neighbourhood_disagree():
    d = _unrelated_same_name_activities(n=6)
    names = {a['name'] for a in d.activities.values()}
    assert names == {'Plain Concrete'}, 'fixture must share ONE identical name'
    ctx = build_context(d)
    out = detect_repeats(ctx)
    # no axis structurally partitions these into comparable multi-step work fronts -
    # the architecture itself refuses the "same name only" case, before evidence scoring
    assert out['axis'] is None
    assert out['groups'] == []
    assert out['rejected_groups'] == []
    assert sorted(out['singletons']) == sorted(ctx.steps)
    _assert_lossless(ctx, out)


def test_alstom_regime_group_forms_when_every_name_is_distinct_but_structure_agrees():
    d = _alstom_regime_fronts(n=4)
    names = [a['name'] for a in d.activities.values()]
    assert len(names) == len(set(names)), 'fixture must have ALL-DISTINCT names (Alstom regime)'
    ctx = build_context(d)
    out = detect_repeats(ctx)
    assert len(out['groups']) == 1
    g = out['groups'][0]
    assert g['instance_count'] == 4
    assert g['activity_count'] == 16
    assert [s['step'] for s in g['consensus_sequence']] == \
        ['excavate', 'blinding', 'rebar', 'concrete']
    assert g['evidence']['supporting_count'] >= 2      # never one signal alone
    _assert_lossless(ctx, out)


def test_sng_regime_group_forms_when_names_are_identical_across_different_wbs_nodes():
    d = _sng_regime_fronts(n=5)
    names = [a['name'] for a in d.activities.values()]
    assert len(set(names)) == 4, 'fixture must reuse the SAME 4 step names in every front'
    ctx = build_context(d)
    out = detect_repeats(ctx)
    assert len(out['groups']) == 1
    g = out['groups'][0]
    assert g['instance_count'] == 5
    assert g['activity_count'] == 20
    assert g['evidence']['supporting_count'] >= 2
    _assert_lossless(ctx, out)


# ── code-dimension de-duplication never inflates confidence (contract item C) ──
def test_duplicate_code_dimension_is_one_piece_of_evidence_and_never_inflates_confidence():
    base = _add_trade_codes(_fronts(n=5), dup=False)
    dup = _add_trade_codes(_fronts(n=5), dup=True)
    out_base = detect_repeats(build_context(base))
    out_dup = detect_repeats(build_context(dup))
    assert len(out_base['groups']) == len(out_dup['groups']) == 1
    g_base, g_dup = out_base['groups'][0], out_dup['groups'][0]
    # adding a byte-identical second code dimension must not move confidence or evidence
    assert g_base['confidence'] == g_dup['confidence']
    assert g_base['evidence'] == g_dup['evidence']
    classes = out_dup['dimensions']['classes']
    assert any(c['exact_duplicates'] == ['Trade2'] for c in classes)
    collapsed = {c['dimension']: c for c in out_dup['dimensions']['collapsed']}
    assert collapsed['Trade2']['merged_into'] == 'Trade'
    assert collapsed['Trade2']['relation'] == 'exact'


# ── quantity is never available and never inferred (contract item E) ───────
def test_quantity_signal_is_always_unavailable_with_a_reason_and_never_a_number():
    for d in (_blank(), _fronts(n=5), _two_work_types(), _opaque_names(),
              _unrelated_same_name_activities(), _synthetic()):
        ctx = build_context(d)
        sig = quantity_signal(ctx)
        assert sig['available'] is False
        assert sig['reason'] == QUANTITY_UNAVAILABLE_REASON
        assert sig['consumed'] is False
        out = detect_repeats(ctx)
        assert out['signals']['quantity'] == sig
        # every group's own evidence must also carry an unavailable/zero quantity signal
        for g in out['groups']:
            qrow = next(s for s in g['evidence']['signals'] if s['signal'] == 'quantity')
            assert qrow['available'] is False
            assert qrow['support'] == 0.0


def test_quantity_signal_flips_to_available_but_still_derives_no_number_when_wired():
    ctx = build_context(_fronts(n=5))
    # simulate a future parser exposing a resource table - presence only, never consumed
    ctx.data.qty_by_activity = {'o-1-EXC': 12.0}
    sig = quantity_signal(ctx)
    assert sig['available'] is True
    assert sig['source'] == 'qty_by_activity'
    assert sig['consumed'] is False
    out = detect_repeats(ctx)
    assert out['signals']['quantity']['available'] is True
    # detect_repeats never surfaces a quantity NUMBER anywhere in its output
    assert json.dumps(out).find('"quantity_days"') == -1
    for g in out['groups']:
        assert 'quantity' not in g


# ── the non-circular coverage proof (contract item G) ───────────────────────
def test_coverage_proof_detects_an_injected_duplicate_placement_not_100pct_by_construction():
    ctx = build_context(_fronts(n=5))
    out = detect_repeats(ctx)
    assert out['coverage']['exact'] is True

    tampered = json.loads(json.dumps(out['groups']))       # deep copy, JSON round-trip
    victim = tampered[0]['fronts'][0]['activity_ids'][0]
    tampered[0]['fronts'][1]['activity_ids'].append(victim)  # simulate an engine bug

    cov = prove_coverage(ctx, tampered, out['singletons'])
    assert cov['exact'] is False
    assert victim in cov['duplicate_ids']
    # every step is still HIT at least once - proves pct alone can never catch this
    assert cov['pct'] == 100.0
    with pytest.raises(DedupIntegrityError):
        assert_coverage(cov)


def test_coverage_proof_detects_a_missing_id_dropped_from_every_front():
    ctx = build_context(_fronts(n=5))
    out = detect_repeats(ctx)
    tampered = json.loads(json.dumps(out['groups']))
    dropped = tampered[0]['fronts'][0]['activity_ids'].pop()
    cov = prove_coverage(ctx, tampered, out['singletons'])
    assert cov['exact'] is False
    assert dropped in cov['missing_ids']
    assert cov['pct'] < 100.0
    with pytest.raises(DedupIntegrityError):
        assert_coverage(cov)


# ── degenerate inputs ────────────────────────────────────────────────────────
def test_all_milestone_file_yields_no_steps_and_does_not_crash():
    d = _blank()
    d.wbs['PRJ'] = {'name': 'Project', 'parent_object_id': None}
    d.activities = {
        'm1': _act('m1', 'Project Start', 'PRJ', tt='StartMilestone'),
        'm2': _act('m2', 'Phase 1 Complete', 'PRJ', tt='FinishMilestone'),
        'm3': _act('m3', 'Phase 2 Complete', 'PRJ', tt='FinishMilestone'),
    }
    ctx = build_context(d)
    assert ctx.steps == {}
    out = detect_repeats(ctx)
    assert out['groups'] == [] and out['singletons'] == []
    assert out['coverage']['exact'] is True and out['coverage']['pct'] == 100.0
    assert out['hierarchy']['counts']['activities'] == 0
    _assert_lossless(ctx, out)


def test_activities_with_wbs_id_none_do_not_crash_and_stay_covered():
    d = _blank()
    d.wbs['PRJ'] = {'name': 'Project', 'parent_object_id': None}
    d.activities = {
        'a1': _act('a1', 'Orphan One', None, dur_hours=8.0),
        'a2': _act('a2', 'Orphan Two', None, dur_hours=8.0),
    }
    ctx = build_context(d)
    out = detect_repeats(ctx)
    _assert_lossless(ctx, out)
