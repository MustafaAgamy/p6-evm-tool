"""Per-discipline Scope-of-Work discussion, derived from the schedule.

Groups the construction activities by discipline (the Type-of-Works / trade code
when the file has one, else the top-level WBS branch — same concept as the sequence
charts), lists each discipline's WBS work-packages, and writes a short factual scope
paragraph from the real counts. Pure logic; generic across any construction project.
"""
from collections import OrderedDict

from p6_narrative.sequence import pick_discipline_dim
from p6_narrative.util import top_wbs_name

_NON_WORK = {'StartMilestone', 'FinishMilestone', 'LOE', 'WBSSummary'}


def scope_blocks(activities, wbs, code_types=None, bac_by_activity=None, discipline_dim=None):
    """Return ``[{discipline, packages, activity_count, cost, paragraph}]`` — one
    block per discipline, ordered by first appearance."""
    if discipline_dim is None:
        discipline_dim = pick_discipline_dim(code_types)
    bac = bac_by_activity or {}
    groups = OrderedDict()
    for act in activities:
        if act.get('task_type') in _NON_WORK:
            continue
        disc = (act.get('activity_codes') or {}).get(discipline_dim) if discipline_dim else None
        disc = disc or top_wbs_name(act.get('wbs_id'), wbs) or 'General'
        grp = groups.setdefault(disc, {'packages': OrderedDict(), 'cost': 0.0, 'count': 0})
        pkg = (wbs.get(act.get('wbs_id')) or {}).get('name') or 'General'
        grp['packages'][pkg] = grp['packages'].get(pkg, 0) + 1
        grp['cost'] += bac.get(act.get('object_id'), 0.0) or 0.0
        grp['count'] += 1

    blocks = []
    for disc, grp in groups.items():
        pkgs = list(grp['packages'].keys())
        blocks.append({
            'discipline': disc,
            'packages': pkgs,
            'activity_count': grp['count'],
            'cost': round(grp['cost'], 2),
            'paragraph': _describe(disc, pkgs, grp['count']),
        })
    return blocks


def _describe(discipline, packages, count):
    if not packages:
        return f"The {discipline} scope comprises {count} scheduled activities."
    shown = ', '.join(packages[:8])
    more = '' if len(packages) <= 8 else f", and {len(packages) - 8} more"
    pkg_word = 'work-package' if len(packages) == 1 else 'work-packages'
    return (f"The {discipline} scope comprises {count} activities across "
            f"{len(packages)} {pkg_word}: {shown}{more}.")
