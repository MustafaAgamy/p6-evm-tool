"""Activity % complete variance + the Option-B period summary.

`activity_progress` lists every non-milestone activity whose % complete moved between
the two updates (biggest gain first), flagging started / finished / reversal.

`period_summary` measures progress against LAST PERIOD'S FORECAST: you were at
actual_prev; the previous update scheduled `period_forecast` more across this window;
so it forecast `forecast_at_now`; you actually reached actual_now. The gap is the
shortfall and `forecast_achievement` = earned / forecast. All %s are 0-100.
"""
from p6_period.scurve import cumulative_pct

_MILESTONES = ('StartMilestone', 'FinishMilestone')


def _pct100(v):
    return round((v or 0.0) * 100, 1)


def _fmt(d):
    return d.strftime('%d-%b-%Y') if d else '—'


def _project_finish(data):
    """Latest forecast finish across the schedule (remaining early, then planned)."""
    fins = []
    for a in getattr(data, 'activities', {}).values():
        f = a.get('remaining_early_finish') or a.get('planned_finish')
        if f:
            fins.append(f)
    return max(fins) if fins else None


def activity_progress(matched, include=None):
    """{'rows': [...], 'counts': {...}} — activities whose % complete changed.

    Row: {activity_id, activity_name, prev_pct, curr_pct, variance, reversal,
    started, finished}. Sorted by variance descending (reversals sink to the end).
    Pure milestones are excluded. If `include` is a set of activity codes (the
    construction/execution activities), engineering/procurement progress is filtered out."""
    rows = []
    counts = {'increased': 0, 'reversed': 0, 'started': 0, 'finished': 0}
    for code in matched.matched_codes:
        if include is not None and code not in include:
            continue
        b = matched.baseline_by_code[code]
        u = matched.update_by_code[code]
        if u.get('task_type') in _MILESTONES or b.get('task_type') in _MILESTONES:
            continue
        prev_pct = _pct100(b.get('percent_complete'))
        curr_pct = _pct100(u.get('percent_complete'))
        variance = round(curr_pct - prev_pct, 1)
        if variance == 0:
            continue
        started = prev_pct == 0.0 and curr_pct > 0.0
        finished = curr_pct >= 100.0 and prev_pct < 100.0
        reversal = variance < 0
        counts['increased'] += 1 if variance > 0 else 0
        counts['reversed'] += 1 if reversal else 0
        counts['started'] += 1 if started else 0
        counts['finished'] += 1 if finished else 0
        rows.append({
            'activity_id': code,
            'activity_name': u.get('name') or b.get('name') or '',
            'prev_pct': prev_pct,
            'curr_pct': curr_pct,
            'variance': variance,
            'reversal': reversal,
            'started': started,
            'finished': finished,
            # activity status for its own column (In Progress / Completed) — from % complete
            'status': 'Completed' if curr_pct >= 100.0 else 'In Progress',
            # activity codes ({dimension: value}) carried so the UI slicer can filter
            'codes': u.get('activity_codes') or {},
        })
    rows.sort(key=lambda r: -r['variance'])
    return {'rows': rows, 'counts': counts}


def progress_by_code(matched, curr, period_earned, include=None):
    """Where this period's progress came from, grouped by each P6 activity code
    (duration-weighted, indicative — scaled to the overall period earned %).
    {code_type: [{'value', 'contribution', 'activity_count'}]} sorted biggest first."""
    types = list(getattr(curr, 'activity_code_types', []) or [])
    if not types or not period_earned:
        return {}
    out = {}
    for t in types:
        by_val, total_w = {}, 0.0
        for code in matched.matched_codes:
            if include is not None and code not in include:
                continue
            b, u = matched.baseline_by_code[code], matched.update_by_code[code]
            if u.get('task_type') in _MILESTONES:
                continue
            var = (u.get('percent_complete') or 0.0) - (b.get('percent_complete') or 0.0)  # 0-1
            if var <= 0:
                continue
            val = (u.get('activity_codes') or {}).get(t)
            if not val:
                continue
            w = ((u.get('planned_duration') or 0.0) or 1.0) * var
            total_w += w
            slot = by_val.setdefault(val, [0.0, 0])
            slot[0] += w
            slot[1] += 1
        if total_w <= 0:
            continue
        rows = [{'value': v, 'contribution': round(period_earned * wc / total_w, 1), 'activity_count': n}
                for v, (wc, n) in by_val.items()]
        rows.sort(key=lambda r: -r['contribution'])
        out[t] = rows
    return out


def period_summary(prev, curr, prev_metrics, curr_metrics):
    """Option-B headline numbers for the dashboard. `*_metrics` are metrics.compute()
    results (reused so the figures match the EVM tab)."""
    dd_prev = (getattr(prev, 'project', {}) or {}).get('data_date')
    dd_now = (getattr(curr, 'project', {}) or {}).get('data_date')
    actual_prev = _pct100((prev_metrics or {}).get('overall_actual_pct'))
    actual_now = _pct100((curr_metrics or {}).get('overall_actual_pct'))

    # The previous update's scheduled progress across THIS window (its own forecast dates).
    period_forecast = 0.0
    if dd_prev and dd_now and dd_now > dd_prev:
        c = cumulative_pct(prev, [dd_prev, dd_now])
        period_forecast = round(c[1] - c[0], 1)

    period_earned = round(actual_now - actual_prev, 1)
    forecast_at_now = round(actual_prev + period_forecast, 1)
    achievement = round(period_earned / period_forecast, 2) if period_forecast > 0 else None
    shortfall = round(forecast_at_now - actual_now, 1)

    delay_prev = (prev_metrics or {}).get('delay_days')
    delay_now = (curr_metrics or {}).get('delay_days')
    delay_change = (delay_now - delay_prev) if (delay_prev is not None and delay_now is not None) else None

    # SPI at each update's own cutoff (data) date — reused from metrics.compute so it
    # matches the EVM tab. Variance = current − previous (SPI is higher-is-better).
    prev_spi = (prev_metrics or {}).get('spi')
    curr_spi = (curr_metrics or {}).get('spi')
    spi_variance = round(curr_spi - prev_spi, 2) if (prev_spi is not None and curr_spi is not None) else None

    fin_prev = _project_finish(prev)
    fin_now = _project_finish(curr)
    finish_slip_days = (fin_now - fin_prev).days if (fin_prev and fin_now) else None

    return {
        'project_name': (getattr(curr, 'project', {}) or {}).get('name') or '',
        'data_date_prev': _fmt(dd_prev),
        'data_date_now': _fmt(dd_now),
        'actual_prev': actual_prev,
        'actual_now': actual_now,
        'period_earned': period_earned,
        'period_forecast': period_forecast,
        'forecast_at_now': forecast_at_now,
        'forecast_achievement': achievement,
        'shortfall_pct': shortfall,
        'delay_prev': delay_prev,
        'delay_now': delay_now,
        'delay_change': delay_change,
        'prev_spi': round(prev_spi, 2) if prev_spi is not None else None,
        'curr_spi': round(curr_spi, 2) if curr_spi is not None else None,
        'spi_variance': spi_variance,
        'forecast_finish_prev': _fmt(fin_prev),
        'forecast_finish_now': _fmt(fin_now),
        'finish_slip_days': finish_slip_days,
    }
