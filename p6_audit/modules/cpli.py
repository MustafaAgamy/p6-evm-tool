"""Critical Path / CPLI module (Schedule Health Review).

DCMA Point 13 — the Critical Path Length Index. CPLI measures how realistically
the schedule can still finish on time:

    CPLI = (CPL + TF) / CPL

where CPL is the critical-path length in WORKING days from the data date to
project completion, and TF is the total float on the completion milestone.

  * CPLI = 1.0  → exactly on plan (zero float at the finish).
  * CPLI < 1.0  → the finish is threatened (negative float on the driving path).
  * CPLI > 1.0  → float in hand (capped: the score never exceeds 100).

The score is CPLI as a percent clamped to 0..100, so a deeply negative float
cannot feed a negative score into the weighted roll-up. Where the file does not
give us what CPLI needs — no dated finish, no float on it, or a finish that sits
on/before the data date — the check does not penalise the schedule but reports
`computable = False`, so nothing is presented as healthy on missing data.

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

# Spans, not finish candidates — they run to the project end by construction.
_SUMMARY_TYPES = {'LOE', 'WBSSummary'}


def _finish_date(act):
    """The activity's forecast finish: remaining early finish, else planned finish."""
    return act.get('remaining_early_finish') or act.get('planned_finish')


def _start_date(act):
    """The activity's forecast start: remaining early start, else planned start."""
    return act.get('remaining_early_start') or act.get('planned_start')


def _iso(dt):
    return dt.strftime('%Y-%m-%d') if dt is not None else None


def compute_cpli(cpl, tf):
    """Pure ratio (CPL + TF) / CPL.

    None unless CPL is a real forward span (> 0) and the float is known. A zero
    or negative CPL — the finish sitting on or before the data date — would
    invert the ratio and read back as a perfectly healthy schedule.
    """
    if cpl is None or cpl <= 0 or tf is None:
        return None
    return (cpl + tf) / cpl


def run_cpli(graph, config):
    acts = graph.activities

    # 1) Finish milestone = the activity with the LATEST finish date. Prefer a
    #    real FinishMilestone if any carry a finish; otherwise any dated activity
    #    that is not a summary span — LOE and WBS Summary activities stretch to
    #    the project end by definition and carry no meaningful float.
    dated = [(oid, a, _finish_date(a)) for oid, a in acts.items()
             if _finish_date(a) is not None and a.get('task_type') not in _SUMMARY_TYPES]
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

    # 4) Critical-path length, defensively. Working days on the milestone's own
    #    calendar when the file gives us one — P6 measures float that way, so a
    #    raw date subtraction would not match it. Plain calendar days otherwise;
    #    `cpl_basis` records which, because a calendar-day CPL against a
    #    working-day float understates the slip and must not be read as exact.
    cal = graph.calendars.get(finish_milestone.get('calendar_id')) if finish_milestone else None
    if cal and data_date and finish_date:
        cpl, cpl_basis = signed_working_days(cal, data_date, finish_date), 'working'
    elif data_date and finish_date:
        cpl, cpl_basis = (finish_date - data_date).days, 'calendar'
    else:
        cpl, cpl_basis = None, None

    # 5) CPLI.
    cpli = compute_cpli(cpl, tf)

    # 6) Score = CPLI as a percent, clamped to 0..100 so a deeply negative float
    #    cannot push a negative score into the weighted roll-up. When CPLI is not
    #    computable the check does not penalise the schedule (100), and
    #    `computable` tells the dashboard to say "not computable", not "Excellent".
    computable = cpli is not None
    score = round(max(0.0, min(100.0, cpli * 100)), 1) if computable else 100.0
    grade = uniform_grade(score)
    pct = round(100.0 - score, 1)

    # Findings = the DRIVING PATH: one row per critical activity, carrying its dates
    # so the driving-path timeline can be drawn straight from them.
    findings = []
    for oid in graph.critical_ids():
        act = acts.get(oid, {})
        findings.append({
            'activity_id':      act.get('id', oid),
            'activity_name':    act.get('name', ''),
            'wbs_path':         graph.wbs_path(oid),
            'start':            _iso(_start_date(act)),
            'finish':           _iso(_finish_date(act)),
            'total_float_days': act.get('total_float_days'),
            'note':             'On the driving/critical path',
        })
    # chronological — the timeline reads left to right; id breaks ties
    findings.sort(key=lambda f: (f['start'] or '', f['finish'] or '', str(f['activity_id'])))

    return {
        'module': MODULE,
        'name': NAME,
        'kpis': {
            'cpli':                     round(cpli, 2) if cpli is not None else None,
            'critical_path_length_days': cpl,
            'cpl_basis':                 cpl_basis,      # 'working' | 'calendar' | None
            'computable':                computable,
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
