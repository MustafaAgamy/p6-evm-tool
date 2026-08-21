"""Schedule Intelligence — the five-level repetition hierarchy and the coverage proof.

The next slice consolidates the narrative along this hierarchy, so every level has to be
explicit and addressable in the returned contract — otherwise consolidation loses
information that nobody can get back:

1. **Repeated Activity** — the individual scheduled activity, by ``object_id``.
2. **Activity Family** — the same operation recurring across contexts (every "Plain
   Concrete" pour), with the object_ids that belong to it.
3. **Repeated Work Front** — one physical / logical instance executing a set of families
   (Silo 7, Zone 2, Chainage 3+400), with its object_ids.
4. **Typical Sequence** — the consensus order of operations shared by the fronts of a
   group, with median working-day duration and how many fronts contain each step.
5. **Project-Specific Exception** — anything a front does differently: a missing step, an
   extra step, a duration or cost outlier, a different hand-off, a cycle, a unique
   condition. Every exception carries the object_ids it refers to, so it stays traceable
   to the underlying activities.

Levels 4 and 5 together are the safety property: level 4 removes the repetition, level 5
guarantees nothing was lost in removing it.

:func:`prove_coverage` is the other half of that safety property. It does **not** compute
"covered = grouped + (steps - grouped)", which is 100% by construction and proves nothing.
It counts every placement as a multiset and checks that each step object_id appears in
exactly one front or in the singleton list — reporting any duplicated, missing or foreign
id. :func:`assert_coverage` raises on violation.
"""
from collections import Counter

LEVEL_NAMES = {
    '1': 'repeated_activity',
    '2': 'activity_family',
    '3': 'repeated_work_front',
    '4': 'typical_sequence',
    '5': 'project_specific_exception',
}

LEVEL_KEYS = {
    '1': 'activities',
    '2': 'families',
    '3': 'fronts',
    '4': 'typical_sequences',
    '5': 'exceptions',
}


class DedupIntegrityError(AssertionError):
    """Raised when the coverage proof fails — an engine bug, never bad input."""


def build_hierarchy(context, groups, singletons):
    """Flatten the assembled groups into the five addressable levels.

    Nothing new is computed here: the groups already carry their families, fronts,
    typical sequence and exceptions. This produces the flat, globally addressable index
    of each level (and the level-1 row for every step activity, grouped or not) so a
    consumer can walk the hierarchy from either end.
    """
    activities, families, fronts, sequences, exceptions = {}, [], [], [], []

    for gi, group in enumerate(groups):
        gid = group['group_id']
        fam_of_activity = {}
        for fam in group['families']:
            families.append({
                'family_id': fam['family_id'],
                'group_id': gid,
                'group_index': gi,
                'step': fam['step'],
                'label': fam['label'],
                'activity_ids': list(fam['activity_ids']),
                'activity_count': fam['activity_count'],
                'front_count': fam['front_count'],
                'median_days': fam['median_days'],
            })
            for oid in fam['activity_ids']:
                fam_of_activity[oid] = fam['family_id']
        for front in group['fronts']:
            fronts.append({
                'front_id': front['front_id'],
                'group_id': gid,
                'group_index': gi,
                'label': front['unit_label'],
                'activity_ids': list(front['activity_ids']),
                'family_ids': list(front['family_ids']),
                'activity_count': len(front['activity_ids']),
                'exception_count': len(front['exceptions']),
            })
            for oid, step in zip(front['activity_ids'], front['steps']):
                activities[oid] = {
                    'object_id': oid,
                    'group_id': gid,
                    'group_index': gi,
                    'front_id': front['front_id'],
                    'family_id': fam_of_activity.get(oid),
                    'step': step or None,
                }
        sequences.append({
            'group_id': gid,
            'group_index': gi,
            'label': group['label'],
            'front_count': group['front_count'],
            'steps': list(group['typical_sequence']),
        })
        for exc in group['exceptions']:
            exceptions.append(dict(exc, group_id=gid, group_index=gi))

    for oid in singletons:
        activities[oid] = {
            'object_id': oid, 'group_id': None, 'group_index': None,
            'front_id': None, 'family_id': None, 'step': None,
        }

    families.sort(key=lambda f: (f['group_index'], f['family_id']))
    fronts.sort(key=lambda f: (f['group_index'], f['front_id']))
    exceptions.sort(key=lambda e: (e['group_index'], e['front_id'], e['kind'],
                                   e['detail']))
    return {
        'level_names': dict(LEVEL_NAMES),
        'level_keys': dict(LEVEL_KEYS),
        'activities': activities,
        'families': families,
        'fronts': fronts,
        'typical_sequences': sequences,
        'exceptions': exceptions,
        'counts': {
            'activities': len(activities),
            'families': len(families),
            'fronts': len(fronts),
            'typical_sequences': len(sequences),
            'exceptions': len(exceptions),
        },
    }


def prove_coverage(context, groups, singletons):
    """Verify — not assert by construction — that nothing was lost or double-counted.

    Counts every placement of every object_id across all fronts of all groups plus the
    singleton list, as a multiset, and compares that against the step population:

    ``duplicate_ids``  ids placed more than once (a front overlap, or a group emitted
                       twice) — the failure the circular check could never see.
    ``missing_ids``    step ids that were placed nowhere.
    ``foreign_ids``    placed ids that are not step activities at all (a milestone, LOE
                       or summary activity leaking into a front).
    ``exact``          True only when all three are empty.
    ``pct``            share of the step population placed *at least* once — a measured
                       number, which can be below 100.
    """
    placements = Counter()
    for group in groups:
        for front in group['fronts']:
            placements.update(front['activity_ids'])
    placements.update(singletons)

    steps = set(context.steps)
    placed = set(placements)
    duplicate_ids = sorted(o for o, c in placements.items() if c > 1)
    missing_ids = sorted(steps - placed)
    foreign_ids = sorted(placed - steps)
    in_groups = sum(len(f['activity_ids']) for g in groups for f in g['fronts'])
    n_steps = len(steps)
    hit = len(steps & placed)
    return {
        'method': ('multiset check: every step object_id must appear in exactly one '
                   'front or in singletons'),
        'steps': n_steps,
        'in_groups': in_groups,
        'singletons': len(singletons),
        'placements': sum(placements.values()),
        'distinct_placed': len(placed),
        'duplicate_ids': duplicate_ids,
        'missing_ids': missing_ids,
        'foreign_ids': foreign_ids,
        'exact': not (duplicate_ids or missing_ids or foreign_ids),
        'pct': round(100.0 * hit / n_steps, 2) if n_steps else 100.0,
    }


def assert_coverage(coverage):
    """Raise :class:`DedupIntegrityError` unless the coverage proof is exact."""
    if coverage['exact']:
        return coverage
    raise DedupIntegrityError(
        'coverage proof failed: %d duplicated, %d missing, %d foreign object_ids '
        '(duplicates=%s missing=%s foreign=%s)' % (
            len(coverage['duplicate_ids']), len(coverage['missing_ids']),
            len(coverage['foreign_ids']), coverage['duplicate_ids'][:5],
            coverage['missing_ids'][:5], coverage['foreign_ids'][:5]))
