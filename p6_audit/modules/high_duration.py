"""High Duration module (V2).

Flags the activities whose planned (original) duration exceeds a day threshold - exactly what
P6 lists with the filter 'Original Duration is greater than <limit>d' and the WBS under Construction
(every activity type). Long tasks are
hard to track and mask progress — break them up or add progress steps.

SCOPE (review decision 2026-10-11): the limit is a construction rule, so the EVALUATION (score,
band, Summary) is always the activities under the Construction WBS. As an additional option the
planner may pick any other top-level WBS (config ``audit.high_duration_wbs`` / ``rescope``) to see
its count and its over-limit activities - the score does not move. Every top-level WBS's own count is kept (``mgmt['wbs']``), and the
over-limit activities of the WBS not counted too (``mgmt['not_counted']``), so a new pick is
answered from the stored result — no schedule file is read again.

Days = planned hours / the schedule's working day (ScheduleGraph.day_hours).
Score = 100 − High Duration % (over-limit activities / task activities in the Construction WBS).
"""
from p6_audit.findings import content_id, bump_severity
from p6_audit.scoring import linear_score, uniform_grade

MODULE = 'high_duration'
NAME = 'High Duration'

RECOMMENDATION = ('Break into shorter, trackable activities, or add progress steps '
                  'if it is genuinely one continuous quantity-driven job')

_ORDER = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
_TYPE_NAMES = {'Task': 'Task Dependent', 'ResourceDependent': 'Resource Dependent', 'LOE': 'Level of Effort',
               'WBSSummary': 'WBS Summary', 'StartMilestone': 'Start Milestone', 'FinishMilestone': 'Finish Milestone'}


def run_high_duration(graph, config):
    audit = config.get('audit', {})
    threshold = audit.get('duration_threshold_days', 44)
    # Ibrahim's rule (2026-10-12), exactly the P6 filter: 'Original Duration is greater than
    # <limit>d' AND the WBS is under Construction - every activity P6 lists, whatever its type.
    real = list(graph.activities.items())
    n_task = sum(1 for _o, a in real if a.get('task_type') == 'Task')
    key_of = graph.scope_group  # the major WBS - or the path down to its Construction node

    def over_limit(act):
        return (act.get('planned_duration') or 0) / graph.day_hours(act) > threshold
    # P6's filter 'Original Duration is greater than <limit>d' lists EVERY activity type - counted
    # per major WBS beside the Task Dependent count, so the report reconciles with that filter
    p6 = {r['wbs']: r for r in graph.p6_wbs_rows(key=key_of, p6_over=lambda _o, a: over_limit(a))}
    constr = {key_of(oid) for oid in graph.activities if graph.is_construction(oid)}

    per = {}                    # WBS -> [activities, over the limit, of which Task Dependent]
    findings = []
    max_days = 0.0
    for oid, act in real:
        branch = key_of(oid)
        row = per.setdefault(branch, [0, 0, 0])
        row[0] += 1
        duration_days = (act.get('planned_duration') or 0) / graph.day_hours(act)
        if duration_days > max_days:
            max_days = duration_days
        if duration_days <= threshold:
            continue
        row[1] += 1
        row[2] += 1 if act.get('task_type') == 'Task' else 0
        severity = bump_severity('Medium') if act.get('is_critical') else 'Medium'
        findings.append({
            'finding_id':     content_id('HIGHDUR', act['id'], 'long'),
            'activity_id':    act['id'],
            'activity_name':  act.get('name', ''),
            'wbs_path':       graph.wbs_path(oid),
            'wbs_branch':     branch,
            'activity_type':  _TYPE_NAMES.get(act.get('task_type'), act.get('task_type') or ''),
            'duration_days':  round(duration_days, 1),
            'severity':       severity,
            'recommendation': RECOMMENDATION,
            'is_critical':    bool(act.get('is_critical')),
        })
    findings.sort(key=lambda f: (_ORDER.get(f['severity'], 9), -f['duration_days']))

    # P6's filter 'Original Duration > threshold' also lists Level of Effort / WBS Summary
    # activities, which span other work and are not checked here - counted so the report can
    # reconcile with that filter (review tip 4)
    span_over = sum(1 for oid, act in graph.activities.items() if graph.is_span_activity(oid)
                    and (act.get('planned_duration') or 0) / graph.day_hours(act) > threshold)

    wbs = [{'wbs': b, 'activities': n, 'over': o, 'task_over': t,
            'pct': round(100.0 * o / n, 1) if n else 0.0, 'is_construction': b in constr,
            'p6_activities': (p6.get(b) or {}).get('activities', n),     # the same counts, taken by
            'p6_over': (p6.get(b) or {}).get('p6_over', o)}              # the shared per-WBS counter
           for b, (n, o, t) in per.items()]
    wbs.sort(key=lambda r: (not r['is_construction'], -r['p6_activities'], r['wbs']))

    module = {
        'module': MODULE,
        'name': NAME,
        'kpis': {
            'threshold':            threshold,
            'all_activities':       len(graph.activities),  # every activity type, as P6 lists them
            'all_task_activities':  n_task,                # Task Dependent, every WBS
            'all_over_threshold':   len(findings),         # P6's filter, whole schedule, every type
            'all_task_over':        sum(r[2] for r in per.values()),
            'p6_over_threshold':    sum(r['p6_over'] for r in p6.values()),   # P6's filter, every type
            'span_over_threshold':  span_over,             # LOE / WBS Summary over the limit (not counted)
            'max_duration':         round(max_days, 1) if real else 0,
            'hours_basis':          dict(graph.hours_basis),
        },
        'findings': findings,
        'wbs_summary': [],
        'mgmt': {'wbs': wbs, 'not_counted': []},
    }
    return rescope(module, audit.get('high_duration_wbs'))


def rescope(module, picked=None):
    """The module with the picked top-level WBS SHOWN (names as in ``mgmt['wbs']``).

    The EVALUATION never moves: score, grade, pct and the ``total_activities`` / ``over_threshold``
    / ``high_pct`` figures are always the Construction WBS (every WBS when the schedule names no
    construction WBS). The pick is an additional view: ``findings`` and the ``view_*`` figures list
    the picked WBS; None / empty / unknown names -> the view is the evaluated WBS too.
    Pure arithmetic over the stored result."""
    m = dict(module)
    mgmt = dict(m.get('mgmt') or {})
    if 'wbs' not in mgmt:       # imported before the WBS scope existed: nothing to re-count
        return m
    rows = [dict(r) for r in (mgmt.get('wbs') or [])]
    names = [r['wbs'] for r in rows]
    constr = [r['wbs'] for r in rows if r.get('is_construction')]
    evaluated = set(constr or names)                 # what the score is calculated on - always
    chosen = [n for n in names if n in set(picked or [])]
    view = set(chosen) or evaluated                  # what is listed - the planner's pick

    def figures(scope):
        total = sum(r['activities'] for r in rows if r['wbs'] in scope)
        over = sum(r['over'] for r in rows if r['wbs'] in scope)
        return total, over, (round(100.0 * over / total, 1) if total else 0.0)

    def label(scope):
        if constr and scope == set(constr):
            return 'Construction only'
        if scope == set(names):
            return 'All WBS'
        return ', '.join(n for n in names if n in scope)

    everything = list(m.get('findings') or []) + list(mgmt.get('not_counted') or [])
    everything.sort(key=lambda f: (_ORDER.get(f.get('severity'), 9), -(f.get('duration_days') or 0)))
    for r in rows:
        r['evaluated'] = r['wbs'] in evaluated       # in the score
        r['counted'] = r['wbs'] in view              # shown / listed
    total, over, pct = figures(evaluated)
    v_total, v_over, v_pct = figures(view)

    k = dict(m.get('kpis') or {})
    k.update({
        'total_activities': total,                 # activities EVALUATED (the Construction WBS)
        'over_threshold':   over,
        'high_pct':         pct,
        'scope_wbs':        [n for n in names if n in evaluated],
        'scope_label':      label(evaluated),
        # P6's own figures for the evaluated WBS: every activity under it, and what the filter
        # 'Original Duration > limit' lists there (every activity type)
        'scope_p6_activities': sum(r.get('p6_activities', r['activities']) for r in rows if r['wbs'] in evaluated),
        'scope_p6_over':       sum(r.get('p6_over', r['over']) for r in rows if r['wbs'] in evaluated),
        'scope_task_over':     sum(r.get('task_over', 0) for r in rows if r['wbs'] in evaluated),
        'scope_fallback':   not constr,            # no construction WBS named -> every WBS
        'view_wbs':         [n for n in names if n in view],
        'view_label':       label(view),
        'view_default':     view == evaluated,
        'view_activities':  v_total,
        'view_over':        v_over,
        'view_pct':         v_pct,
    })
    mgmt['wbs'] = rows
    mgmt['not_counted'] = [f for f in everything if f.get('wbs_branch') not in view]
    score = linear_score(pct)
    m.update({'kpis': k, 'findings': [f for f in everything if f.get('wbs_branch') in view],
              'mgmt': mgmt, 'pct': pct, 'score': score, 'grade': uniform_grade(score)})
    return m
