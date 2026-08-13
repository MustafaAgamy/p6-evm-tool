"""Per-discipline construction sequence charts, derived from the schedule.

Pure logic (no I/O). Same WBS/code grouping concept as the critical-path
comparison: group activities per Type-of-Works / discipline code (fall back to the
top WBS when no such code exists), roll each activity up to its **WBS work-package**
(so "Drilling" and "RFT", both under WBS "Pile", are steps inside the Pile node,
not separate groups), order packages and steps by the scheduled order, and split
into charts of at most ``max_steps`` steps so a long chain continues on the next
chart instead of overflowing one unreadable chart. Nothing is ever dropped.

Generic across any construction project: the disciplines, packages and steps all
come from the imported file.
"""
from collections import OrderedDict
from datetime import datetime

from p6_narrative.util import top_wbs_name

# task types that are not real construction steps
_NON_STEP_TYPES = {'StartMilestone', 'FinishMilestone', 'LOE', 'WBSSummary'}
# substrings that identify a "discipline / type of works" code dimension
_DISCIPLINE_HINTS = ('type of work', 'discipline', 'trade')


def pick_discipline_dim(code_types):
    """Best activity-code dimension to group sequences by, or None.

    Looks for a dimension whose name reads like "type of works" / discipline /
    trade. Generic — whatever the file happens to call it.
    """
    for dim in code_types or []:
        low = (dim or '').lower()
        if any(hint in low for hint in _DISCIPLINE_HINTS):
            return dim
    return None


def _start_key(dt):
    """Sort key that pushes missing dates to the end."""
    return (dt is None, dt or datetime.max)


def build_sequences(activities, wbs, code_types=None, discipline_dim=None, max_steps=15):
    """Return a list of sequence charts (JSON-serialisable dicts).

    Each chart: ``{discipline, chart_index, chart_count, packages, steps_shown,
    steps_total}`` where ``packages`` is ``[{name, steps:[{name, id}]}]``.
    """
    if discipline_dim is None:
        discipline_dim = pick_discipline_dim(code_types)
    steps = [a for a in activities if a.get('task_type') not in _NON_STEP_TYPES]

    def discipline_of(act):
        if discipline_dim:
            val = (act.get('activity_codes') or {}).get(discipline_dim)
            if val:
                return val
        return top_wbs_name(act.get('wbs_id'), wbs) or 'General'

    def package_of(act):
        node = wbs.get(act.get('wbs_id')) or {}
        return node.get('name') or 'General'

    by_discipline = OrderedDict()
    for act in steps:
        by_discipline.setdefault(discipline_of(act), []).append(act)

    charts = []
    for discipline, dacts in by_discipline.items():
        packages = OrderedDict()
        for act in dacts:
            packages.setdefault(package_of(act), []).append(act)

        pkg_list = []
        for name, pacts in packages.items():
            ordered = sorted(pacts, key=lambda a: _start_key(a.get('planned_start')))
            starts = [a['planned_start'] for a in ordered if a.get('planned_start')]
            pkg_list.append({
                'name': name,
                'min_start': min(starts) if starts else None,
                'steps': [{'name': a.get('name'), 'id': a.get('id')} for a in ordered],
            })
        pkg_list.sort(key=lambda p: _start_key(p['min_start']))

        steps_total = sum(len(p['steps']) for p in pkg_list)
        packed = _pack(pkg_list, max_steps)
        count = len(packed)
        for i, cpkgs in enumerate(packed, 1):
            charts.append({
                'discipline': discipline,
                'chart_index': i,
                'chart_count': count,
                'packages': [{'name': p['name'], 'steps': p['steps']} for p in cpkgs],
                'steps_shown': sum(len(p['steps']) for p in cpkgs),
                'steps_total': steps_total,
            })
    return charts


def _pack(pkg_list, max_steps):
    """Greedily pack whole packages into charts of <= max_steps steps.

    A package that alone exceeds max_steps is split across consecutive charts so
    every step still appears.
    """
    charts, cur, cur_n = [], [], 0
    for p in pkg_list:
        n = len(p['steps'])
        if n > max_steps:
            if cur:
                charts.append(cur)
                cur, cur_n = [], 0
            for i in range(0, n, max_steps):
                charts.append([{'name': p['name'], 'steps': p['steps'][i:i + max_steps]}])
            continue
        if cur and cur_n + n > max_steps:
            charts.append(cur)
            cur, cur_n = [], 0
        cur.append(p)
        cur_n += n
    if cur:
        charts.append(cur)
    return charts
