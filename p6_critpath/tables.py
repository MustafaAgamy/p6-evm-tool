"""Every-milestone finish comparison and float migration for the Critical Path Analyzer.

milestones_table — one row per finish milestone across the loaded schedules: each
schedule's forecast finish, the slip vs baseline and vs last period, the milestone's
CPLI, and how many work fronts on its driving path are critical / near-critical.

float_migration — how activities moved between float bands from the comparison base
(previous, else baseline) to the current update: the early-warning of a coming slip.
"""
from p6_critpath.analysis import (
    _forecast_finish, _ref_calendar, _wd_between, _iso, _baseline_finish, cpli,
    _MILESTONES, NEAR_THRESHOLD, p6_done, p6_critical, p6_near,
)


def _d0(d):
    """Normalise a datetime to midnight (day precision) so finish-date variances compare
    calendar days, not sub-day times."""
    from datetime import datetime
    return d.replace(hour=0, minute=0, second=0, microsecond=0) if isinstance(d, datetime) else d


def _work_front(a):
    """(work front, the WBS above it): the WBS the activity sits in, as P6 shows its path."""
    segs = [x.strip() for x in (a.get('wbs_path') or '').split('>') if x.strip()]
    return (segs[-1] if segs else (a.get('wbs_name') or '—'), segs[-2] if len(segs) > 1 else '')


def _band(a, near=NEAR_THRESHOLD):
    """The activity's float band by P6's own filters (Ibrahim, comment 91): 'crit' = P6's Critical
    filter, 'near' = Total Float within 1d - 10d, 'safe' = Total Float greater than 10d.
    Completed activities and activities without float are in no band (P6 lists them in none)."""
    if p6_done(a) or a.get('total_float_days') is None:
        return None
    if p6_critical(a):
        return 'crit'
    if p6_near(a, near):
        return 'near'
    # Safe = P6 'Total Float is greater than 10d'; anything outside the three P6 filters (an LOE
    # with negative float, float between 0 and 1 d) is in no band, so every band ticks in P6
    return 'safe' if a['total_float_days'] > near + 1e-9 else None


_KINDS = ('near_to_crit', 'safe_to_crit', 'safe_to_near', 'crit_to_recovered', 'held_crit')


def float_migration(base_data, curr_data, near=NEAR_THRESHOLD):
    """Band moves from base -> current, matched by activity ID, every activity type P6's filters
    list (milestones included). Counts each move, the critical / near-critical totals on each
    side (so the planner can tick them against P6's filters in both files), and keeps the
    activities for drill-down."""
    fronts_of = {}

    def bands(data, facts, keep_front=False):
        out = {}
        for a in data.activities.values():
            band = _band(a, near)
            if band is None:
                continue
            out[a.get('id')] = band
            facts[a.get('id')] = (a.get('name') or '', a.get('total_float_days'))
            if keep_front:
                fronts_of[a.get('id')] = _work_front(a)
        return out

    pf, cf = {}, {}            # id -> (name, total float) on each side, for the Excel list
    pb, cb = bands(base_data, pf), bands(curr_data, cf, keep_front=True)
    counts = {k: 0 for k in _KINDS}
    rows = []
    for code, cur in cb.items():
        prev = pb.get(code)
        if prev is None:
            continue
        kind = None
        if cur == 'crit':
            kind = {'near': 'near_to_crit', 'safe': 'safe_to_crit', 'crit': 'held_crit'}[prev]
        elif prev == 'safe' and cur == 'near':
            kind = 'safe_to_near'
        elif prev == 'crit':
            kind = 'crit_to_recovered'
        if kind:
            counts[kind] += 1
            rows.append({'id': code, 'from': prev, 'to': cur, 'kind': kind,
                         'name': cf[code][0], 'base_tf': pf[code][1], 'curr_tf': cf[code][1],
                         'front': fronts_of.get(code, ('', ''))[0], 'front_parent': fronts_of.get(code, ('', ''))[1]})
    counts['turned_crit'] = counts['near_to_crit'] + counts['safe_to_crit']
    # one grid: band last period (or 'none' = in no band there) x band now - every open activity
    matrix = {}
    for code, cur in cb.items():
        key = f"{pb.get(code) or 'none'}>{cur}"
        matrix[key] = matrix.get(key, 0) + 1
    # where float was lost: the work front (the WBS the activity sits in) of every activity that
    # turned critical or dropped into near-critical, biggest first
    fr = {}
    for r in rows:
        if r['kind'] not in ('near_to_crit', 'safe_to_crit', 'safe_to_near'):
            continue
        f = fr.setdefault((r['front'], r['front_parent']), {'front': r['front'], 'parent': r['front_parent'],
                                                            'turned_crit': 0, 'safe_to_near': 0})
        f['turned_crit' if r['kind'] != 'safe_to_near' else 'safe_to_near'] += 1
    fronts = sorted(fr.values(), key=lambda f: (-(f['turned_crit'] + f['safe_to_near']), -f['turned_crit'], f['front']))
    lost = [r['base_tf'] - r['curr_tf'] for r in rows if r['kind'] in ('near_to_crit', 'safe_to_crit')
            and r['base_tf'] is not None and r['curr_tf'] is not None]
    float_lost = {'avg': round(sum(lost) / len(lost), 1) if lost else None,
                  'max': round(max(lost), 1) if lost else None}
    totals = {side: {'critical': sum(1 for v in bb.values() if v == 'crit'),
                     'near': sum(1 for v in bb.values() if v == 'near')}
              for side, bb in (('base', pb), ('current', cb))}
    return {'counts': counts, 'rows': rows, 'totals': totals, 'matrix': matrix, 'fronts': fronts,
            'float_lost': float_lost}


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
            # Finish-date variances compare two calendar dates, so normalise to day precision
            # first — otherwise two finishes on the same day but different times can read ±1.
            var_bl = _wd_between(cal, _d0(_baseline_finish(curr, ca)), _d0(ff))
            length = _wd_between(cal, data_date, ff)
            if length is not None and length < 0:
                length = 0
            cpli_v = cpli(length, ca.get('total_float_days'))
            if prev:
                pa = _finish_ms(prev, code)
                if pa:
                    var_pd = _wd_between(cal, _d0(_forecast_finish(pa)), _d0(ff))
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
