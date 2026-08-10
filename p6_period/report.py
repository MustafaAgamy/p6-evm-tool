"""Assemble the Update-vs-Update report from two consecutive updates + their metrics.

build_report_from_data is pure (takes pre-computed metrics.compute() results, so the
figures match the EVM tab); build_report is a parse+compute convenience for CLI/tests.
Slice 1: dashboard summary + activity % variance + period S-curve. Later slices fold
in critical-path movement, what-moved buckets, the conclusion and the milestone trend.
"""
from p6_compare.model import MatchedSchedules
from p6_period.progress import activity_progress, period_summary
from p6_period.scurve import period_scurve
from p6_period.movement import critical_movement, buckets


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


def _project_conclusion(summary, crit):
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
    return ' '.join(parts)


def build_report_from_data(prev, curr, prev_metrics, curr_metrics, config=None):
    """Report dict for the two updates. `prev`/`curr` are ScheduleData; `*_metrics`
    are metrics.compute() results for each (reused for actual % and delay)."""
    matched = MatchedSchedules(prev, curr)
    summary = period_summary(prev, curr, prev_metrics, curr_metrics)
    progress = activity_progress(matched)
    scurve = period_scurve(prev, curr, summary['actual_prev'], summary['actual_now'])

    dd_now = (getattr(curr, 'project', {}) or {}).get('data_date')
    logic_changed = _logic_changed_codes(matched, curr)
    crit = critical_movement(matched, logic_changed)
    buck = buckets(matched, dd_now, logic_changed)
    conclusion = _conclusion(summary, crit, buck)
    project_conclusion = _project_conclusion(summary, crit)

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
