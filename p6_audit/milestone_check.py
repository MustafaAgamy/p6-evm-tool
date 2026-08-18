"""Contract Milestone Check (Schedule Health Review).

The user gives the contract milestone name(s) + contract date(s); this matches each
to a real activity/milestone in the baseline (XER/XML) and evaluates it — scheduled
finish, variance, total float, driving-path membership, and whether a HARD constraint
is masking a slip. Output is evidence-first (Finding / Evidence / Root cause / Impact /
Recommendation), never a bare score. Nothing is invented for an unmatched milestone.

This is user-input-driven, so it is not a MODULE_RUNNER; `evaluate_milestones` is
called with the contract milestones the user entered (persisted per project).
"""
from datetime import datetime

from p6_evm.calendars import signed_working_days

# Constraints that PIN a finish and can therefore hide a downstream slip.
_FINISH_HARD = {'Mandatory Finish', 'Finish On'}
_HARD = {'Mandatory Start', 'Mandatory Finish', 'Start On', 'Finish On'}


def _norm(s):
    """Lower-cased, punctuation-stripped name for tolerant matching."""
    return ' '.join(''.join(ch if (ch.isalnum() or ch == ' ') else ' ' for ch in (s or '').lower()).split())


def _finish(act):
    return act.get('remaining_early_finish') or act.get('planned_finish')


def _parse_date(v):
    if isinstance(v, datetime):
        return v
    if not v:
        return None
    s = str(v)
    for fmt in ('%Y-%m-%d', '%d-%b-%Y', '%d-%b-%y', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(s[:len(fmt) + 4], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s[:19])
    except ValueError:
        return None


def _iso(dt):
    return dt.strftime('%Y-%m-%d') if isinstance(dt, datetime) else None


def _match(graph, name):
    """Best schedule activity for a contract-milestone name. Milestones are preferred,
    then any activity. Exact normalized name wins, then containment. None when there is
    no confident match — the check never guesses a milestone into existence."""
    target = _norm(name)
    if not target:
        return None
    acts = graph.activities
    ms = [(oid, a) for oid, a in acts.items() if 'Milestone' in (a.get('task_type') or '')]
    alla = list(acts.items())
    for pool in (ms, alla):
        for oid, a in pool:
            if _norm(a.get('name')) == target:
                return (oid, a)
    for pool in (ms, alla):
        for oid, a in pool:
            n = _norm(a.get('name'))
            if n and (target in n or n in target):
                return (oid, a)
    return None


def _variance_days(graph, act, contract_date, sched_finish):
    """Working days from the contract date to the scheduled finish (+ = late)."""
    if not (contract_date and sched_finish):
        return None
    cal = graph.calendars.get(act.get('calendar_id')) if getattr(graph, 'calendars', None) else None
    if cal:
        return signed_working_days(cal, contract_date, sched_finish)
    return (sched_finish - contract_date).days


def _evaluate_one(graph, name, contract_date):
    matched = _match(graph, name)
    base = {
        'contract_name': name,
        'contract_date': _iso(contract_date),
        'matched_activity_id': None, 'matched_activity_name': None,
        'scheduled_finish': None, 'variance_days': None, 'total_float_days': None,
        'on_driving_path': None, 'constraint_type': None, 'constraint_date': None,
    }
    if not matched:
        base.update({
            'status': 'Unmatched',
            'finding': f'No schedule activity could be reliably matched to "{name}".',
            'evidence': 'No milestone or activity name matches the contract milestone, and none was picked manually.',
            'root_cause': 'The milestone is missing from the baseline, or it is named differently.',
            'impact': 'The schedule cannot be evaluated against this contractual obligation.',
            'recommendation': 'Pick the matching activity from the schedule, or add the milestone to the baseline. '
                              'Nothing is assessed until it is matched.',
        })
        return base

    oid, act = matched
    sched_finish = _finish(act)
    tf = act.get('total_float_days')
    ctype = act.get('constraint_type') if act.get('constraint_type') in _HARD else None
    cdate = _parse_date(act.get('constraint_date')) if ctype else None
    variance = _variance_days(graph, act, contract_date, sched_finish)
    on_path = bool(act.get('is_critical'))
    finish_hard = ctype in _FINISH_HARD
    # A finish-pinning constraint on/near the contract date while the float is negative
    # means the network really finishes later — the constraint is masking a slip.
    masking = bool(finish_hard and tf is not None and tf < 0)

    base.update({
        'matched_activity_id': act.get('id', oid), 'matched_activity_name': act.get('name', ''),
        'scheduled_finish': _iso(sched_finish), 'variance_days': variance, 'total_float_days': tf,
        'on_driving_path': on_path, 'constraint_type': ctype, 'constraint_date': _iso(cdate),
    })

    late = variance is not None and variance > 0
    v_txt = f'{abs(variance)} working days' if variance is not None else 'an unknown amount'
    if masking:
        base.update({
            'status': 'Masked',
            'finding': 'The milestone shows on the contract date, but only because a hard constraint pins it there.',
            'evidence': f'The activity carries a {ctype} constraint and total float is {tf} d (negative), '
                        f'so the network actually finishes later than the pinned date.',
            'root_cause': 'A hard constraint is holding the milestone on its date while the logic finishes later — '
                          'the constraint is masking a real slip.',
            'impact': 'The baseline looks on-contract but is not; the slip is hidden from the completion date.',
            'recommendation': f'Remove the {ctype} constraint and let the logic drive the date, then recover the slip '
                              'on the driving path. The constraint is not contractually justified as used.',
        })
    elif late:
        base.update({
            'status': 'Late',
            'finding': f'Scheduled {v_txt} after the contract date.',
            'evidence': f'Scheduled finish {_iso(sched_finish)} vs contract {_iso(contract_date)}; '
                        f'total float {tf} d; {"on" if on_path else "off"} the driving path.',
            'root_cause': 'A genuine logic-driven slip — the date is not being masked by a constraint.',
            'impact': f'The milestone is {v_txt} late against the contract.',
            'recommendation': ('Recover the slip on the driving-path activities feeding this milestone, '
                               'or raise a contractual date discussion.'),
        })
    else:
        base.update({
            'status': 'On track',
            'finding': 'Scheduled on or before the contract date.',
            'evidence': f'Scheduled finish {_iso(sched_finish)} vs contract {_iso(contract_date)}; total float {tf} d.',
            'root_cause': 'The milestone meets its contractual date through the network logic.',
            'impact': 'No contractual exposure on this milestone.',
            'recommendation': 'No action needed; keep the driving path protected.',
        })
    return base


def evaluate_milestones(graph, contract_milestones):
    """contract_milestones: [{'name', 'date'}] the user entered. Returns one evaluation
    per milestone (order preserved), each carrying the facts + the evidence-first verdict."""
    out = []
    for cm in contract_milestones or []:
        out.append(_evaluate_one(graph, cm.get('name'), _parse_date(cm.get('date'))))
    return out


def baseline_milestones(graph):
    """The baseline's milestone activities (id · name · finish), offered to the user to
    match a contract milestone against — so the entry screen shows what's really in the
    XER/XML file. Chronological."""
    out = []
    for oid, a in graph.activities.items():
        if 'Milestone' in (a.get('task_type') or ''):
            out.append({'activity_id': a.get('id', oid), 'name': a.get('name', ''),
                        'task_type': a.get('task_type'), 'finish': _iso(_finish(a))})
    out.sort(key=lambda x: (x['finish'] or '9999', x['name'] or ''))
    return out


def _status_counts(evals):
    c = {'On track': 0, 'Late': 0, 'Masked': 0, 'Unmatched': 0}
    for e in evals:
        c[e['status']] = c.get(e['status'], 0) + 1
    return c


def build_milestone_module(hard_module, graph, contract_milestones):
    """Merge the contract-milestone evaluation into the (renamed) Hard Constraints
    module → the **Milestone Check** sub-feature. The hard-constraint score and findings
    stay; the contract-milestone evaluations, the baseline milestone list (for matching)
    and `needs_input` (gate B) are added on top."""
    m = dict(hard_module or {})
    m['module'] = m.get('module', 'hard_constraints')
    m['name'] = NAME
    cms = contract_milestones or []
    evals = evaluate_milestones(graph, cms)
    m['milestones'] = evals
    m['milestone_counts'] = _status_counts(evals)
    m['baseline_milestones'] = baseline_milestones(graph)
    m['needs_input'] = not bool(cms)
    return m


MODULE = 'hard_constraints'   # unchanged internal key (DB continuity); display name below
NAME = 'Milestone Check'
