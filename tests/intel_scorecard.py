"""Measurement framework for the repeated-work-front engine (Narrative Slice 2).

This is the permanent acceptance scorecard, not a scratchpad experiment. It runs every
permanent fixture and — when the files are present — the two real baselines (Saint-Gobain
and Alstom) through the engine under BOTH selectors:

  * ``shape``  — :func:`_select_axis_shape`, the validated shape-based baseline (default);
  * ``judge``  — :func:`_select_axis`, the rejected ``_judge`` scoring, kept for the
                 side-by-side only and never the default.

Every acceptance criterion Ibrahim locked is measured for each, side-by-side:

    meaningful repeated work fronts | meaningful schedule coverage | no over-lumping
    no artificial fragmentation | no duplicate fronts | WBS/parent/scope preserved
    complete traceability to the P6 activities | deterministic output | reasonable
    runtime | no project-specific hardcoding

The fixtures carry a KNOWN planning truth and are scored PASS/FAIL against it. The real
baselines are only MEASURED and shown group-by-group — the planner establishes their
ground truth, the tool never invents a numerical target for them.

Run it directly for the full report::

    python -m tests.intel_scorecard            # fixtures + real files if present
    python -m tests.intel_scorecard --fixtures # fixtures only

Real-file paths default to the Desktop test set and can be overridden with the
environment variables ``SNG_XER`` and ``ALSTOM_XER``.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from p6_evm.parser import parse_file                                    # noqa: E402
from p6_narrative.intel import build_context, detect_repeats           # noqa: E402
from p6_narrative.intel.dedup import _select_axis, _select_axis_shape  # noqa: E402
from tests import intel_fixtures as F                                   # noqa: E402

SELECTORS = {'shape': _select_axis_shape, 'judge': _select_axis}

# Real baselines. Not in the repo (real client schedules); measured when present.
REAL_FILES = {
    'Saint-Gobain': os.environ.get(
        'SNG_XER', r'C:/Users/7748/Desktop/XER File Test/SNT_GBN_Baseline_AS2-Fin-3.xer'),
    'Alstom': os.environ.get(
        'ALSTOM_XER', r'C:/Users/7748/Desktop/XER File Test/Alstom-BL-R02 baselne.xer'),
}


# ── the branch a group / activity belongs to (over-lumping + world separation) ──
def _branch_of(context, oid):
    """The major WBS branch of one activity, via the layer's own adaptive grouping."""
    wid = (context.data.activities.get(oid) or {}).get('wbs_id')
    return context.group_of.get(wid)


def _group_branches(context, group):
    branches = set()
    for front in group['fronts']:
        for oid in front['activity_ids']:
            b = _branch_of(context, oid)
            if b is not None:
                branches.add(b)
    return branches


# ── the ten criteria, measured on one finished result ─────────────────────────
def measure(context, result, runtime_s, deterministic):
    groups = result['groups']
    cov = result['coverage']
    steps = cov['steps'] or 1

    fronts_per_group = [g['front_count'] for g in groups]
    acts_per_front = [g['activity_count'] / g['front_count']
                      for g in groups if g['front_count']]

    labels = [g['label'] for g in groups]
    dup_labels = sum(c - 1 for c in Counter(labels).values() if c > 1)

    # duplicate FRONTS: two groups with the same (label, parent, step-key signature)
    sigs = [(g['label'], g.get('wbs_parent_id'),
             tuple(s['step'] for s in g['typical_sequence'])) for g in groups]
    dup_signatures = sum(c - 1 for c in Counter(sigs).values() if c > 1)

    # over-lumping: a group whose activities straddle >1 major WBS branch
    spans = [len(_group_branches(context, g)) for g in groups]
    branch_pure = sum(1 for s in spans if s <= 1)

    # artificial fragmentation: >1 group under the same parent+discipline that a planner
    # would read as one scope split apart (reported, judged by eye on real files).
    by_parent = Counter((g.get('wbs_parent_id'), g.get('discipline')) for g in groups)
    fragmented_parents = sum(c - 1 for c in by_parent.values() if c > 1)

    # scope worlds the groups actually touch (Engineering / Procurement / Construction …)
    world_branches = sorted({b for g in groups for b in _group_branches(context, g)})
    disciplines = sorted({g.get('discipline') for g in groups if g.get('discipline')})

    # traceability: every front carries its activity object_ids, and the coverage proof
    # is an exact multiset (each step object_id appears once across groups + singletons).
    traceable = all(front.get('activity_ids') for g in groups for front in g['fronts'])

    return {
        'axis': result['axis'],
        'unit_count': result['unit_count'],
        'n_groups': len(groups),
        'grouped_activities': cov['in_groups'],
        'total_activities': cov['steps'],
        'grouped_share': round(cov['in_groups'] / steps, 4),
        'singletons': len(result['singletons']),
        'singleton_share': round(len(result['singletons']) / steps, 4),
        'median_fronts_per_group': statistics.median(fronts_per_group) if fronts_per_group else 0,
        'median_acts_per_front': round(statistics.median(acts_per_front), 2) if acts_per_front else 0,
        'duplicate_labels': dup_labels,
        'duplicate_front_signatures': dup_signatures,
        'branch_pure_groups': branch_pure,
        'max_branch_span': max(spans) if spans else 0,
        'fragmented_parent_scopes': fragmented_parents,
        'world_branches': world_branches,
        'disciplines': disciplines,
        'coverage_exact': cov['exact'],
        'coverage_pct': cov['pct'],
        'traceable_fronts': traceable,
        'rejected_groups': len(result['rejected_groups']),
        'runtime_s': round(runtime_s, 3),
        'deterministic': deterministic,
    }


def run(context, selector):
    t0 = time.perf_counter()
    result = detect_repeats(context, selector=selector)
    runtime_s = time.perf_counter() - t0
    again = detect_repeats(context, selector=selector)
    deterministic = (json.dumps(result, sort_keys=True) == json.dumps(again, sort_keys=True))
    return result, measure(context, result, runtime_s, deterministic)


def group_rows(context, result):
    """One readable row per group: name, parent/scope, fronts, activities, sequence."""
    rows = []
    for g in sorted(result['groups'],
                    key=lambda g: (-g['activity_count'], -g['front_count'], g['label'])):
        branches = sorted(_group_branches(context, g))
        rows.append({
            'label': g['label'],
            'wbs_parent': g.get('wbs_parent_id'),
            'discipline': g.get('discipline'),
            'branches': branches,
            'fronts': g['front_count'],
            'activities': g['activity_count'],
            'seq_len': len(g['typical_sequence']),
            'confidence': round(g.get('confidence') or 0.0, 3),
            'front_labels': [fr['unit_label'] for fr in g['fronts']][:12],
        })
    return rows


# ── fixture truths (the permanent gate) ──────────────────────────────────────
def _one_group(gr, fronts, seq_len=None):
    if len(gr) != 1:
        return False, 'expected exactly 1 group, got %d' % len(gr)
    g = gr[0]
    if g['fronts'] != fronts:
        return False, 'expected %d fronts, got %d' % (fronts, g['fronts'])
    if seq_len is not None and g['seq_len'] != seq_len:
        return False, 'expected %d-step sequence, got %d' % (seq_len, g['seq_len'])
    return True, 'ok'


def truth_road(m, rows):
    ok, why = _one_group(rows, 12, 7)
    return ok and m['grouped_share'] == 1.0 and m['duplicate_labels'] == 0, why


def truth_tower(m, rows):
    # 25 typical-floor fronts as ONE group; the podium (7 activities) stays out of it.
    floors = [r for r in rows if r['fronts'] == 25]
    if len(floors) != 1:
        return False, 'expected one 25-front floor group, got %d' % len(floors)
    if floors[0]['seq_len'] != 6:
        return False, 'floor sequence should be 6 steps, got %d' % floors[0]['seq_len']
    # podium must not be merged into the floor group (floor group holds exactly 25*6=150)
    if floors[0]['activities'] != 150:
        return False, 'floor group holds %d activities, expected 150 (podium merged in?)' % floors[0]['activities']
    return True, 'ok'


def truth_opaque(m, rows):
    # Honest: either no groups, or exactly the real 8-front / 5-step structure.
    if m['n_groups'] == 0:
        return True, 'honest: no reliable fronts claimed'
    ok, why = _one_group(rows, 8, 5)
    return ok, 'invented fronts from numbering' if not ok else 'found the real 8 fronts'


def truth_phase_vs_trade(m, rows):
    # Three worlds preserved: 14 construction building-fronts, plus Engineering (8) and
    # Procurement (10) as their own scopes. The coarse phase code must not win with 0 fronts.
    con = [r for r in rows if r['fronts'] == 14]
    eng = [r for r in rows if r['fronts'] == 8]
    prc = [r for r in rows if r['fronts'] == 10]
    if not con:
        return False, 'no 14-front construction group (phase code likely won with 0 fronts)'
    missing = [w for w, hit in [('Engineering', eng), ('Procurement', prc)] if not hit]
    if missing:
        return False, 'construction found, but missing world(s): ' + ', '.join(missing)
    return True, 'three worlds preserved'


def truth_no_repetition(m, rows):
    return m['n_groups'] == 0 and m['singleton_share'] == 1.0, \
        'expected 0 groups / all singletons, got %d groups' % m['n_groups']


FIXTURES = [
    ('road',           lambda: F.road(12),                truth_road),
    ('tower',          lambda: F.tower(25, podium=True),  truth_tower),
    ('opaque',         lambda: F.opaque(8, 5),            truth_opaque),
    ('phase_vs_trade', lambda: F.phase_vs_trade(14),      truth_phase_vs_trade),
    ('no_repetition',  lambda: F.no_repetition(40),       truth_no_repetition),
]

_COLS = [
    ('axis', 'axis'), ('n_groups', 'grps'), ('grouped_share', 'grp%'),
    ('singleton_share', 'sng%'), ('median_fronts_per_group', 'med_fr'),
    ('median_acts_per_front', 'med_a/f'), ('duplicate_labels', 'dupL'),
    ('duplicate_front_signatures', 'dupF'), ('fragmented_parent_scopes', 'frag'),
    ('max_branch_span', 'span'), ('runtime_s', 'secs'), ('deterministic', 'det'),
]


def _fmt(v):
    if isinstance(v, float):
        return '%.3f' % v
    if isinstance(v, bool):
        return 'Y' if v else 'N'
    return str(v)


def print_fixture_scorecard():
    print('\n' + '=' * 78)
    print('FIXTURE ACCEPTANCE GATE  (known planning truth -> PASS/FAIL)')
    print('=' * 78)
    header = '%-16s %-6s ' % ('fixture', 'sel') + ' '.join('%7s' % lbl for _, lbl in _COLS)
    for name, build, truth in FIXTURES:
        data = build()
        context = build_context(data)
        print('\n' + '-' * 78)
        print(header)
        for sel_name, sel in SELECTORS.items():
            result, m = run(context, sel)
            rows = group_rows(context, result)
            cells = ' '.join('%7s' % _fmt(m[k]) for k, _ in _COLS)
            ok, why = truth(m, rows)
            print('%-16s %-6s ' % (name if sel_name == 'shape' else '', sel_name) + cells)
            print('%-16s %-6s   %s  %s' % ('', '', 'PASS' if ok else 'FAIL', why))


def print_real_scorecard():
    for label, path in REAL_FILES.items():
        p = Path(path)
        if not p.exists():
            print('\n[skip] %s — file not found: %s' % (label, path))
            continue
        print('\n' + '=' * 78)
        print('REAL BASELINE: %s' % label)
        print('  %s' % path)
        print('=' * 78)
        t0 = time.perf_counter()
        data = parse_file(str(p))
        context = build_context(data)
        parse_s = time.perf_counter() - t0
        print('  parsed in %.2fs — %d activities, %d steps'
              % (parse_s, len(data.activities), len(context.steps)))
        for sel_name, sel in SELECTORS.items():
            result, m = run(context, sel)
            print('\n  --- selector: %s ---' % sel_name)
            for k, _ in _COLS:
                print('    %-28s %s' % (k, _fmt(m[k])))
            print('    %-28s %s' % ('world_branches', m['world_branches']))
            print('    %-28s %s' % ('disciplines', m['disciplines']))
            print('    groups (group-by-group):')
            print('      %-34s %-10s %-8s %5s %6s %4s' %
                  ('label', 'parent', 'disc', 'fr', 'acts', 'seq'))
            for r in group_rows(context, result):
                print('      %-34s %-10s %-8s %5d %6d %4d' %
                      (str(r['label'])[:34], str(r['wbs_parent'])[:10],
                       str(r['discipline'])[:8], r['fronts'], r['activities'], r['seq_len']))


def main(argv):
    print_fixture_scorecard()
    if '--fixtures' not in argv:
        print_real_scorecard()


if __name__ == '__main__':
    main(sys.argv[1:])
