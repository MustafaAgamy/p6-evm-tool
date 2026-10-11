"""Whole-day Durations — Review & Resolve.

The planner accepts the suggested whole number of days (or types another) for an activity whose
duration is a decimal; this module

  1. **re-validates** — puts the accepted durations on an in-memory copy of the activities and
     re-runs the SAME whole-day check (the source of truth), so the Decimal % and the score on
     screen are the engine's own figures; and

  2. **writes them to a copy of the imported XER** — Original Duration, and Remaining Duration of
     an activity that has not started, in hours on the activity's own calendar. Dates are never
     touched: P6 reschedules on F9.

A started activity is never changed automatically (its remaining duration is the planner's
judgement) — its fix is returned in ``held`` and the finding stays open.
"""
import types

from p6_evm.parser import parse_file
from p6_audit.graph import ScheduleGraph
from p6_audit.presentation import build_presentation
from p6_audit.modules.whole_day import run_whole_day

HELD_MESSAGE = 'Activity has started — set its duration in P6'


def _started(act):
    s = (act.get('status') or '').strip().lower().replace(' ', '').replace('_', '')
    if s in ('inprogress', 'completed', 'active', 'complete'):
        return True
    if s == 'notstarted':
        return False
    return bool(act.get('actual_start')) or (act.get('percent_complete') or 0) > 0


def _day_hours(data, act):
    cal = (getattr(data, 'calendars', {}) or {}).get(act.get('calendar_id'))
    return cal.day_hours if (cal and getattr(cal, 'day_hours', None)) else 8.0


def _norm(accepted):
    """Accepted fixes → {activity code: (new_days, finding_id)}; the last one for a code wins.
    Anything that is not a positive number of days is dropped."""
    out = {}
    for op in accepted or []:
        code = op.get('activity_id')
        try:
            days = float(op.get('new_days'))
        except (TypeError, ValueError):
            continue
        if code and days > 0:
            out[code] = (days, op.get('finding_id') or '')
    return out


def plan(data, accepted):
    """Split the accepted fixes into what is applied and what is held back.
    Returns (hours_by_code, held_finding_ids) — hours on each activity's own calendar."""
    want = _norm(accepted)
    hours, held = {}, set()
    for act in data.activities.values():
        code = act.get('id')
        if code not in want:
            continue
        days, fid = want[code]
        if _started(act):
            held.add(fid)
            continue
        hours[code] = days * _day_hours(data, act)
    return hours, held


def revalidate(data, config, accepted):
    """Re-run the whole-day check with the accepted durations in place. Nothing is written."""
    hours, held = plan(data, accepted)
    acts = {}
    for oid, a in data.activities.items():
        if a.get('id') in hours:
            a = dict(a)
            a['planned_duration'] = hours[a['id']]
        acts[oid] = a
    shim = types.SimpleNamespace(
        activities=acts, relationships=data.relationships,
        calendars=getattr(data, 'calendars', {}) or {},
        project=getattr(data, 'project', None))
    fresh = run_whole_day(ScheduleGraph(shim), config)
    # P6's own activity totals beside the check, as on import (a fix never changes them)
    _g = ScheduleGraph(data)
    fresh['p6_counts'] = {'total': len(_g.p6_all()), 'remaining': len(_g.p6_remaining())}
    still = {f['activity_id'] for f in fresh['findings']}
    resolved = sorted({fid for code, (_, fid) in _norm(accepted).items()
                       if fid and code in hours and code not in still})
    return {
        'findings': fresh['findings'],
        'resolved': resolved,
        'held': sorted(h for h in held if h),
        'kpis': fresh['kpis'],
        'score': fresh.get('score'), 'grade': fresh.get('grade'), 'pct': fresh.get('pct'),
        'presentation': build_presentation(fresh),
    }


def revalidate_from_path(path, config, accepted):
    return revalidate(parse_file(path), config, accepted)


def _fmt_hours(v):
    v = round(float(v or 0.0), 4)
    return str(int(v)) if v == int(v) else repr(v)


def write_corrected(source_path, accepted, out_path, **_):
    """Write the accepted whole-day durations into a copy of the imported XER (TASK table:
    target_drtn_hr_cnt, and remain_drtn_hr_cnt of a not-started activity). Every other table and
    column is preserved verbatim. Returns {'applied': activities changed, 'out_path'}."""
    if not source_path.lower().endswith('.xer'):
        raise ValueError('Whole-day duration fixes are written to an XER file only.')
    hours, _held = plan(parse_file(source_path), accepted)
    from p6_audit.modules.oos_resolve import read_xer_keeping_encoding
    text, encoding, newline = read_xer_keeping_encoding(source_path)
    lines = [ln.rstrip('\r') for ln in text.split('\n')]
    out, cur, fields, done = [], None, [], set()
    for ln in lines:
        parts = ln.split('\t')
        tag = parts[0]
        if tag == '%T':
            cur, fields = (parts[1] if len(parts) > 1 else None), []
        elif tag == '%F':
            fields = parts[1:]
        elif tag == '%R' and cur == 'TASK' and hours:
            vals = parts[1:]
            row = dict(zip(fields, vals))
            code = row.get('task_code')
            if code in hours and 'target_drtn_hr_cnt' in fields:
                h = _fmt_hours(hours[code])
                vals[fields.index('target_drtn_hr_cnt')] = h
                if 'remain_drtn_hr_cnt' in fields and (row.get('status_code') or '') == 'TK_NotStart':
                    vals[fields.index('remain_drtn_hr_cnt')] = h
                done.add(code)
                ln = '%R\t' + '\t'.join(vals)
        out.append(ln)
    with open(out_path, 'w', encoding=encoding, newline='') as fh:
        fh.write(newline.join(out))
    return {'applied': len(done), 'out_path': out_path}
