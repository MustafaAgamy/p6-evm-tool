"""Assemble the Update-vs-Update report from two consecutive updates + their metrics.

build_report_from_data is pure (takes pre-computed metrics.compute() results, so the
figures match the EVM tab); build_report is a parse+compute convenience for CLI/tests.
Slice 1: dashboard summary + activity % variance + period S-curve. Later slices fold
in critical-path movement, what-moved buckets, the conclusion and the milestone trend.
"""
from p6_compare.model import MatchedSchedules
from p6_period.progress import activity_progress, period_summary
from p6_period.scurve import period_scurve
from p6_period.movement import critical_movement, buckets, milestone_drift
from p6_period.outlook import schedule_adherence, recovery_outlook, watch_list


def _logic_changed_codes(matched, curr):
    """Activity codes whose relationships/lags changed vs last period, limited to
    construction/execution activities (Ibrahim's rule for the sibling). Best-effort —
    an empty set on any graph error, never fatal."""
    try:
        from p6_audit.graph import ScheduleGraph
        from p6_compare.diff import diff_relationships, driving_pairs
        from p6_compare.report import _construction_codes
        cons = _construction_codes(curr)
        logic = diff_relationships(matched, driving_pairs(ScheduleGraph(curr)))
        return {r['activity_id'] for r in logic['rows'] if r['activity_id'] in cons}
    except Exception:
        return set()


def _sign_pct(v):
    return f'+{v:.1f}%' if v > 0 else f'{v:.1f}%'


def _sign_wd(v):
    return f'+{v}' if v > 0 else f'{v}'


def _conclusion(summary, crit, buck):
    """Auto executive conclusion in the consultant house style."""
    s = summary
    parts = []
    fc, earned, ach = s['period_forecast'], s['period_earned'], s['forecast_achievement']
    if fc and fc > 0:
        kept = f" — keeping {round(ach * 100)}% of its own commitment" if ach is not None else ''
        parts.append(
            f"This period the project earned {_sign_pct(earned)} against the +{fc:.1f}% it forecast "
            f"last period{kept}, reaching {s['actual_now']:.0f}% where the previous update projected "
            f"{s['forecast_at_now']:.0f}%.")
    else:
        parts.append(f"This period the project moved from {s['actual_prev']:.0f}% to "
                     f"{s['actual_now']:.0f}% ({_sign_pct(earned)}).")
    slip = s['finish_slip_days']
    if slip:
        drv = crit['rows'][0] if crit['rows'] else None
        because = f", driven mainly by {drv['activity_id']} ({drv['activity_name']})" if drv else ''
        verb = 'slipped' if slip > 0 else 'pulled in'
        parts.append(f"The forecast completion {verb} {abs(slip)} days to {s['forecast_finish_now']}{because}.")
    if crit['new_critical']:
        n = crit['new_critical']
        parts.append(f"{n} activit{'y' if n == 1 else 'ies'} entered the critical path.")
    if s['delay_change'] and s['delay_now'] is not None:
        parts.append(f"Cumulative delay vs baseline is now {s['delay_now']} working days "
                     f"({_sign_wd(s['delay_change'])} this period).")
    return ' '.join(parts)


def _project_conclusion(summary, crit, recovery=None):
    """Overall project status + outlook — distinct from the this-period conclusion."""
    s = summary
    head = f"Overall the project stands at {s['actual_now']:.0f}% complete, forecasting completion on {s['forecast_finish_now']}"
    if s['delay_now'] is not None:
        head += f" — {s['delay_now']} working days behind the baseline"
    parts = [head + '.']

    bits, worse = [], False
    if s['spi_variance'] is not None and s['curr_spi'] is not None:
        bits.append(f"SPI {s['prev_spi']} → {s['curr_spi']}")
        worse = worse or s['spi_variance'] < 0
    if s['delay_change'] is not None and s['delay_prev'] is not None:
        bits.append(f"delay {s['delay_prev']} → {s['delay_now']} wd")
        worse = worse or s['delay_change'] > 0
    if bits:
        parts.append(f"The trend is {'worsening' if worse else 'holding or improving'} "
                     f"({', '.join(bits)} over the last period).")
    if crit['rows']:
        names = ', '.join(f"{r['activity_id']} ({r['activity_name']})" for r in crit['rows'][:2])
        parts.append(f"The main risk sits on the critical path — {names} — which should be the focus of recovery.")
    if recovery and recovery.get('required_rate') is not None and recovery.get('current_rate') is not None:
        if recovery.get('feasible') is False:
            parts.append(f"At the current rate ({recovery['current_rate']:.1f}%/period) recovery to the "
                         f"baseline is unlikely — it would need about {recovery['required_rate']:.1f}%/period.")
        elif recovery.get('feasible') is True:
            parts.append(f"Recovery to the baseline is still achievable at roughly "
                         f"{recovery['required_rate']:.1f}%/period.")
    return ' '.join(parts)


def _order_by_data_date(prev, curr, prev_metrics, curr_metrics):
    """Always treat the EARLIER data date as 'previous' and the later as 'current',
    whatever order the user loaded them in. If a date is missing, keep the given order."""
    dd_p = (getattr(prev, 'project', {}) or {}).get('data_date')
    dd_c = (getattr(curr, 'project', {}) or {}).get('data_date')
    if dd_p and dd_c and dd_p > dd_c:
        return curr, prev, curr_metrics, prev_metrics
    return prev, curr, prev_metrics, curr_metrics


def _verdict(summary, recovery):
    """Management traffic-light read of the period: {level, headline, detail}. Single
    source of truth — the screen banner and the PDF both read this."""
    s, rec = summary or {}, recovery or {}
    spv, dch, slip, earned = s.get('spi_variance'), s.get('delay_change'), s.get('finish_slip_days'), s.get('period_earned')
    worse = (spv is not None and spv < 0) or (dch is not None and dch > 0) or (slip is not None and slip > 0)
    better = (spv is not None and spv > 0) or (dch is not None and dch < 0) or (slip is not None and slip < 0)
    if rec.get('feasible') is False and (dch or 0) > 0:
        level, head = 'bad', 'Off track — recovery to the baseline is unlikely at the current rate'
    elif worse and not better:
        level, head = 'warn', 'Slipping — the project lost ground this period'
    elif better and not worse:
        level, head = 'good', 'On track — the project gained ground this period'
    else:
        level, head = 'warn', 'Mixed — little net movement this period'
    bits = []
    if earned is not None:
        ach = s.get('forecast_achievement')
        bits.append(f'earned {_sign_pct(earned)}' + (f' ({round(ach * 100)}% of plan)' if ach is not None else ''))
    if spv is not None:
        bits.append(f'SPI {"+" if spv > 0 else ""}{spv}')
    if slip:
        bits.append(f'finish {"slipped" if slip > 0 else "pulled in"} {abs(slip)} d')
    return {'level': level, 'headline': head, 'detail': ('; '.join(bits) + '.' if bits else '')}


def build_report_from_data(prev, curr, prev_metrics, curr_metrics, config=None):
    """Report dict for the two updates. `prev`/`curr` are ScheduleData; `*_metrics`
    are metrics.compute() results for each (reused for actual % and delay).

    The two updates are ordered by data date first — the earlier is 'previous', the
    later 'current' — so the report reads the right way round regardless of load order."""
    prev, curr, prev_metrics, curr_metrics = _order_by_data_date(prev, curr, prev_metrics, curr_metrics)
    matched = MatchedSchedules(prev, curr)
    summary = period_summary(prev, curr, prev_metrics, curr_metrics)
    progress = activity_progress(matched)
    scurve = period_scurve(prev, curr, summary['actual_prev'], summary['actual_now'])

    dd_prev = (getattr(prev, 'project', {}) or {}).get('data_date')
    dd_now = (getattr(curr, 'project', {}) or {}).get('data_date')
    logic_changed = _logic_changed_codes(matched, curr)
    crit = critical_movement(matched, logic_changed)
    buck = buckets(matched, dd_now, logic_changed)
    adherence = schedule_adherence(matched, dd_prev, dd_now)
    recovery = recovery_outlook(prev, curr, summary)
    watch = watch_list(curr)
    milestones = milestone_drift(matched)
    conclusion = _conclusion(summary, crit, buck)
    project_conclusion = _project_conclusion(summary, crit, recovery)

    return {
        'project_name': summary['project_name'],
        'data_date_prev': summary['data_date_prev'],
        'data_date_now': summary['data_date_now'],
        # Guard against mismatched files: near-zero matches means "these don't line up".
        'matched_activities': len(matched.matched_codes),
        'update_activity_count': len(curr.activities),
        # Activity-code dimensions present in the current update — feed the progress slicer.
        'code_types': list(getattr(curr, 'activity_code_types', []) or []),
        'summary': summary,
        'progress': progress,
        'scurve': scurve,
        'critical_movement': crit,
        'buckets': buck,
        'schedule_adherence': adherence,
        'recovery': recovery,
        'watch_list': watch,
        'milestones': milestones,
        'verdict': _verdict(summary, recovery),
        'conclusion': conclusion,
        'project_conclusion': project_conclusion,
    }


def build_report(prev_path, curr_path, config=None):
    """Parse both updates, compute EVM metrics for each (the same way the app does —
    auto-detected categories + WBS classifier, so the figures match the EVM tab), then
    build the report."""
    import json
    from p6_evm.parser import parse_file
    from p6_evm.metrics import compute
    from p6_evm.classify import auto_categories, build_wbs_classifier
    from utils import resource_path
    base = config
    if base is None:
        with open(resource_path('config.json')) as f:
            base = json.load(f)

    def parse_and_compute(path):
        data = parse_file(path)
        cfg = dict(base)
        cfg['categories'] = auto_categories(data)
        return data, compute(data, cfg, classifier=build_wbs_classifier(data))

    prev, prev_m = parse_and_compute(prev_path)
    curr, curr_m = parse_and_compute(curr_path)
    return build_report_from_data(prev, curr, prev_m, curr_m, base)
