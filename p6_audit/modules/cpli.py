"""Critical Path / CPLI module (Schedule Health Review).

DCMA Point 13 — the Critical Path Length Index. CPLI measures how realistically
the schedule can still finish on time:

    CPLI = (CPL + TF) / CPL

where CPL is the critical-path length in WORKING days from the data date to
project completion, and TF is the total float on the completion milestone.

  * CPLI = 1.0  → exactly on plan (zero float at the finish).
  * CPLI < 1.0  → the finish is threatened (negative float on the driving path).
  * CPLI > 1.0  → float in hand (capped: the score never exceeds 100).

Per Ibrahim's baseline rule, a healthy baseline must carry total float >= 0 at
the finish milestone (CPLI >= 1.0). Negative float is a re-plan signal, surfaced
here as `baseline_rule_met = False`.

Score is CPLI itself expressed as a percent (capped at 100); the findings list
is the DRIVING PATH — every activity P6 flags critical.
"""
from p6_evm.calendars import signed_working_days
from p6_audit.scoring import uniform_grade

MODULE = 'cpli'
NAME = 'Critical Path / CPLI'

TARGET = 0.95  # DCMA acceptance threshold for CPLI


def _finish_date(act):
    """The activity's forecast finish: remaining early finish, else planned finish."""
    return act.get('remaining_early_finish') or act.get('planned_finish')


def compute_cpli(cpl, tf):
    """Pure ratio (CPL + TF) / CPL. Returns None when CPL is missing or zero."""
    if not cpl:
        return None
    return (cpl + tf) / cpl


def run_cpli(graph, config):
    acts = graph.activities

    # 1) Finish milestone = the activity with the LATEST finish date. Prefer a
    #    real FinishMilestone if any carry a finish; otherwise any dated activity.
    dated = [(oid, a, _finish_date(a)) for oid, a in acts.items()
             if _finish_date(a) is not None]
    fm_only = [t for t in dated if t[1].get('task_type') == 'FinishMilestone']
    pool = fm_only if fm_only else dated

    finish_milestone = None
    finish_date = None
    if pool:
        _, finish_milestone, finish_date = max(pool, key=lambda t: t[2])

    # 2) Total float on the completion milestone (may be None).
    tf = finish_milestone.get('total_float_days') if finish_milestone else None

    # 3) Data date (update cut-off).
    data_date = graph.data_date

    # 4) Critical-path length in working days, defensively.
    cal = graph.calendars.get(finish_milestone.get('calendar_id')) if finish_milestone else None
    if cal and data_date and finish_date:
        cpl = signed_working_days(cal, data_date, finish_date)
    elif data_date and finish_date:
        cpl = (finish_date - data_date).days
    else:
        cpl = None

    # 5) CPLI.
    cpli = compute_cpli(cpl, tf) if (cpl and cpl != 0 and tf is not None) else None

    # 6) Score = CPLI as a percent, capped at 100.
    score = min(100.0, round(cpli * 100, 1)) if cpli is not None else 100.0
    grade = uniform_grade(score)
    pct = round(100 - score, 1)

    # Findings = the DRIVING PATH: one row per critical activity.
    findings = []
    for oid in graph.critical_ids():
        act = acts.get(oid, {})
        findings.append({
            'activity_id':      act.get('id', oid),
            'activity_name':    act.get('name', ''),
            'wbs_path':         graph.wbs_path(oid),
            'total_float_days': act.get('total_float_days'),
            'note':             'On the driving/critical path',
        })
    findings.sort(key=lambda f: str(f['activity_id']))

    return {
        'module': MODULE,
        'name': NAME,
        'kpis': {
            'cpli':                     round(cpli, 2) if cpli is not None else None,
            'critical_path_length_days': cpl,
            'project_total_float_days':  tf,
            'target':                    TARGET,
            'finish_milestone_id':       finish_milestone.get('id') if finish_milestone else None,
        },
        'pct':   pct,
        'score': score,
        'grade': grade,
        'findings': findings,
        'baseline_rule_met': bool(tf is not None and tf >= 0),
    }
