"""Permanent acceptance gate for the repeated-work-front engine (Narrative Slice 2).

These wire the cross-sector fixtures in ``tests/intel_fixtures.py`` — each carrying a
KNOWN planning truth in its docstring — into the test suite as a regression/acceptance
gate. They are no longer scratchpad experiments: any future selector change must keep
them green. They run against the default selector (the validated shape-based baseline).

The two real baselines (Saint-Gobain, Alstom) are deliberately NOT asserted here — their
ground truth belongs to the planner, established from the group-by-group scorecard in
``tests/intel_scorecard.py``, never invented as a numeric target by the tool.

Every fixture also proves the two non-negotiables that hold for any schedule: complete
traceability (every front carries its P6 activity object_ids) and an exact coverage
partition (every step object_id appears exactly once across groups + singletons).
"""
import json
from pathlib import Path

import pytest

from p6_narrative.intel import build_context, detect_repeats
from tests import intel_fixtures as F


def _run(data):
    return detect_repeats(build_context(data))


def _assert_traceable_and_partitioned(result):
    """Traceability + the exact-coverage partition, required of every result."""
    cov = result['coverage']
    assert cov['exact'] is True
    assert cov['pct'] == 100.0
    assert cov['duplicate_ids'] == [] and cov['missing_ids'] == [] and cov['foreign_ids'] == []
    seen = list(result['singletons'])
    for g in result['groups']:
        for front in g['fronts']:
            assert front['activity_ids'], 'a front carries no activity object_ids'
            seen.extend(front['activity_ids'])
    assert len(seen) == len(set(seen)), 'an activity object_id appears more than once'
    assert len(seen) == cov['steps']


def _labels_unique(result):
    labels = [g['label'] for g in result['groups']]
    assert len(labels) == len(set(labels)), 'two groups share a label (duplicate front)'


# ── road: one repeated scope of twelve chainage fronts ───────────────────────
def test_road_is_one_scope_of_twelve_fronts():
    r = _run(F.road(12))
    assert len(r['groups']) == 1, 'road must not fragment into per-step trade buckets'
    g = r['groups'][0]
    assert g['front_count'] == 12, 'twelve chainage fronts, not collapsed to one'
    assert len(g['typical_sequence']) == 7
    assert g['activity_count'] == 84
    assert r['singletons'] == []
    _labels_unique(r)
    _assert_traceable_and_partitioned(r)


# ── tower: 25 typical floors as one scope, podium kept separate ───────────────
def test_tower_keeps_podium_separate_from_typical_floors():
    r = _run(F.tower(25, podium=True))
    assert len(r['groups']) == 1, 'only the typical floors form a repeated scope'
    g = r['groups'][0]
    assert g['front_count'] == 25
    assert len(g['typical_sequence']) == 6
    assert g['activity_count'] == 150, 'the structurally different podium must not merge in'
    assert len(r['singletons']) == 7, 'the podium (7 activities, one instance) stays out'
    _assert_traceable_and_partitioned(r)


# ── opaque: honest — the real fronts or nothing, never invented from numbers ──
def test_opaque_ids_return_the_real_fronts_or_an_honest_nothing():
    r = _run(F.opaque(8, 5))
    if r['groups']:
        assert len(r['groups']) == 1, 'no groups invented from the sequence numbering'
        assert r['groups'][0]['front_count'] == 8
        assert len(r['groups'][0]['typical_sequence']) == 5
    else:
        assert len(r['singletons']) == 40, 'an honest "cannot tell" leaves every step a singleton'
    _assert_traceable_and_partitioned(r)


# ── phase vs trade: three scope worlds preserved, phase code explains nothing ─
def test_phase_vs_trade_preserves_three_scope_worlds():
    r = _run(F.phase_vs_trade(14))
    fronts = sorted(g['front_count'] for g in r['groups'])
    assert fronts == [8, 10, 14], (
        'expected exactly three worlds — construction (14 building fronts), engineering '
        '(8) and procurement (10); got front counts %s. A selector that follows the coarse '
        'phase code finds no fronts at all.' % fronts)
    _labels_unique(r)
    _assert_traceable_and_partitioned(r)


# ── hostile: no repetition at all ────────────────────────────────────────────
def test_no_repetition_yields_only_singletons():
    r = _run(F.no_repetition(40))
    assert r['groups'] == []
    assert len(r['singletons']) == 40
    _assert_traceable_and_partitioned(r)


# ── deterministic output, byte for byte ──────────────────────────────────────
def test_output_is_deterministic_byte_for_byte():
    for build in (lambda: F.road(12), lambda: F.phase_vs_trade(14), lambda: F.tower(25)):
        ctx = build_context(build())
        a = json.dumps(detect_repeats(ctx), sort_keys=True)
        b = json.dumps(detect_repeats(ctx), sort_keys=True)
        assert a == b


# ── reasonable runtime + determinism at scale (≈13,000 activities) ───────────
@pytest.mark.slow
def test_scale_runs_within_budget_and_is_deterministic():
    import time
    ctx = build_context(F.scale(650, 20))
    t0 = time.perf_counter()
    a = detect_repeats(ctx)
    elapsed = time.perf_counter() - t0
    b = detect_repeats(ctx)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert elapsed < 30.0, 'engine took %.1fs on ~13k activities' % elapsed


# ── matrix-WBS EPC: the instance-primary path is detected and gated ──────────
def test_matrix_epc_routes_to_instance_primary_and_merges_phases():
    from p6_narrative.intel.fronts import detect_fronts, has_matrix_structure
    ctx = build_context(F.matrix_epc(4))
    assert has_matrix_structure(ctx), 'the Submittal/Approval mirror is the matrix signature'
    r = detect_fronts(ctx)
    assert r['mode'] == 'instance-primary'
    worlds = {w['world']: w for w in r['worlds']}
    assert 'Engineering' in worlds and 'Construction' in worlds, 'both worlds represented'

    # Submittal + Approval collapse into ONE document-control front (both phases inside);
    # neither ever appears as a phase-only front (that would be a split mirror = duplicate).
    eng = worlds['Engineering']
    seqs = [' '.join(p for p, _ in f['phase_flow']) for f in eng['fronts']]
    assert any('Submittal' in s and 'Approval' in s for s in seqs), \
        'Submittal and Approval must be one front, not two mirror fronts'
    for s in seqs:
        if 'Submittal' in s or 'Approval' in s:
            assert 'Submittal' in s and 'Approval' in s, 'a front is never a lone phase'

    # construction: the four buildings form one repeated front at work-package altitude
    con = worlds['Construction']
    assert any(f['n_instances'] == 4 for f in con['fronts'])

    # every activity is grouped and traceable to its P6 id
    for w in r['worlds']:
        assert w['grouped'] == w['total']
        for f in w['fronts']:
            assert f['activities'] and all(a['id'] for a in f['activities'])


def test_instance_primary_output_is_deterministic():
    from p6_narrative.intel.fronts import detect_fronts
    ctx = build_context(F.matrix_epc(4))
    a = json.dumps(detect_fronts(ctx), sort_keys=True, default=list)
    b = json.dumps(detect_fronts(ctx), sort_keys=True, default=list)
    assert a == b


# ── no project-specific hardcoding in the intelligence layer ─────────────────
def test_engine_carries_no_client_or_project_names():
    """Criterion #10, enforced: the engine must generalise, never key off a client file."""
    banned = ('alstom', 'gobain', 'mafi', 'noor', 'saint-gobain')
    intel_dir = Path(__file__).resolve().parent.parent / 'p6_narrative' / 'intel'
    for py in sorted(intel_dir.glob('*.py')):
        text = py.read_text(encoding='utf-8').lower()
        for name in banned:
            assert name not in text, '%s references client/project name %r' % (py.name, name)
