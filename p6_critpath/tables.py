"""Every-milestone finish comparison and float migration for the Critical Path Analyzer.

milestones_table — one row per finish milestone across the loaded schedules: each
schedule's forecast finish, the slip vs baseline and vs last period, the milestone's
CPLI, and how many work fronts on its driving path are critical / near-critical.

float_migration — how activities moved between float bands from the comparison base
(previous, else baseline) to the current update: the early-warning of a coming slip.
"""
from p6_critpath.analysis import (
    _forecast_finish, _ref_calendar, _wd_between, _iso, _baseline_finish, cpli,
    _MILESTONES, NEAR_THRESHOLD,
)


def _band(tf, near=NEAR_THRESHOLD):
    if tf is None:
        return None
    if tf <= 0:
        return 'crit'
    if tf < near:
        return 'near'
    return 'safe'


def float_migration(base_data, curr_data, near=NEAR_THRESHOLD):
    """Band moves from base → current, matched by activity code. Counts the four moves the
    dashboard shows, and keeps the ids for drill-down."""
    def bands(data):
        out = {}
        for a in data.activities.values():
            if a.get('task_type') in _MILESTONES:
                continue
            tf = a.get('total_float_days')
            if tf is None:
                continue
            out[a.get('id')] = _band(tf, near)
        return out

    pb, cb = bands(base_data), bands(curr_data)
    counts = {'near_to_crit': 0, 'safe_to_near': 0, 'crit_to_recovered': 0, 'held_crit': 0}
    rows = []
    for code, cur in cb.items():
        prev = pb.get(code)
        if prev is None:
            continue
        kind = None
        if prev == 'near' and cur == 'crit':
            kind = 'near_to_crit'
        elif prev == 'safe' and cur == 'near':
            kind = 'safe_to_near'
        elif prev == 'crit' and cur != 'crit':
            kind = 'crit_to_recovered'
        elif prev == 'crit' and cur == 'crit':
            kind = 'held_crit'
        if kind:
            counts[kind] += 1
            rows.append({'id': code, 'from': prev, 'to': cur, 'kind': kind})
    return {'counts': counts, 'rows': rows}


def _finish_ms(data, code):
    return next((a for a in data.activities.values()
                 if a.get('id') == code and a.get('task_type') == 'FinishMilestone'), None)


def milestones_table(schedules, near=NEAR_THRESHOLD):
    """One row per finish milestone (by code), across every loaded schedule."""
    from p6_critpath.paths import path_boxes, _governing_finish_ms

    roles = [r for r in ('baseline', 'previous', 'current') if r in schedules]
    curr, prev = schedules.get('current'), schedules.get('previous')

    codes, gov = {}, set()
    for data in schedules.values():
        g = _governing_finish_ms(data)
        if g:
            gov.add(g.get('id'))
        for a in data.activities.values():
            if a.get('task_type') == 'FinishMilestone' and a.get('id'):
                codes.setdefault(a.get('id'), a.get('name') or a.get('id'))

    rows = []
    for code, name in codes.items():
        finishes = {}
        for role in roles:
            a = _finish_ms(schedules[role], code)
            finishes[role] = _iso(_forecast_finish(a)) if a else None

        var_bl = var_pd = cpli_v = crit_f = near_f = None
        ca = _finish_ms(curr, code) if curr else None
        if ca:
            data_date = (getattr(curr, 'project', None) or {}).get('data_date')
            cal = _ref_calendar(curr, ca)
            ff = _forecast_finish(ca)
            var_bl = _wd_between(cal, _baseline_finish(curr, ca), ff)
            length = _wd_between(cal, data_date, ff)
            if length is not None and length < 0:
                length = 0
            cpli_v = cpli(length, ca.get('total_float_days'))
            if prev:
                pa = _finish_ms(prev, code)
                if pa:
                    var_pd = _wd_between(cal, _forecast_finish(pa), ff)
            pb = path_boxes(curr, code)
            crit_f = sum(1 for b in pb['boxes'] if b.get('driver_tf') is not None and b['driver_tf'] <= 0)
            near_f = sum(1 for b in pb['boxes'] if b.get('driver_tf') is not None and 0 < b['driver_tf'] < near)

        rows.append({
            'id': code, 'name': name, 'is_governing': code in gov, 'finishes': finishes,
            'var_vs_baseline_d': var_bl, 'var_this_period_d': var_pd, 'cpli': cpli_v,
            'crit_fronts': crit_f, 'near_fronts': near_f,
        })
    rows.sort(key=lambda r: (not r['is_governing'], r['name']))
    return rows
