"""In-chat "professional dashboard" payload — a grounded, one-screen executive read of the
open schedule, assembled ONLY from figures the existing engines already produce.

Nothing here invents a number:
  - the EVM headline (SPI/CPI/PV/EV/AC/variance/delay, overall planned/actual %, categories)
    comes straight from ``metrics.compute()`` (p6_evm/metrics.py);
  - Time Status reuses ``p6_update.analysis.time_status`` (the Update-Analysis engine);
  - the PV−EV gap-by-code reuses ``p6_update.analysis.scope_all`` (cost-weighted scope);
  - the S-curve reuses ``p6_compare.scurve`` (monthly boundaries + cumulative planned %),
    and the earned/forecast curves are spread from the very same cost weights and % complete
    the metrics are built on — so the dashboard can never disagree with the EVM tab.

``build(data, metrics)`` is PURE (a parsed ScheduleData + a metrics.compute() result in, a
plain dict out). ``build_from_snapshot(...)`` mirrors the app's report re-parse pattern
(db.resolve → parse_file → config.json → metrics.compute → build) and is fully guarded.
Money is reported in POUNDS MILLIONS (£M) throughout.
"""
import os
import json
from datetime import datetime, date

from p6_update.analysis import time_status, scope_all
from p6_compare.scurve import _month_boundaries, _project_finish


# ── small helpers ────────────────────────────────────────────────────────────

_MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _as_dt(v):
    if isinstance(v, (datetime, date)):
        return v if isinstance(v, datetime) else datetime(v.year, v.month, v.day)
    if v in (None, ''):
        return None
    try:
        return datetime.fromisoformat(str(v)[:19].replace('Z', ''))
    except Exception:
        return None


def _fmt_day(v):
    """datetime/date/ISO → 'DD Mon YYYY' (e.g. '01 Jul 2024'), or None."""
    d = _as_dt(v)
    return '%02d %s %d' % (d.day, _MON[d.month - 1], d.year) if d else None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _cost_weight(data, act):
    """Activity cost (baseline budget first, else the current cost) — mirrors
    p6_update.analysis._cost_weight so the dashboard weights money the same way."""
    oid = act.get('object_id')
    bl = getattr(data, 'baseline_bac_by_activity', None) or {}
    bac = getattr(data, 'bac_by_activity', None) or {}
    return (bl.get(oid) or bac.get(oid) or 0.0)


def _file_has_cost(data):
    bl = getattr(data, 'baseline_bac_by_activity', None) or {}
    bac = getattr(data, 'bac_by_activity', None) or {}
    return any(v and v > 0 for v in bl.values()) or any(v and v > 0 for v in bac.values())


# ── tone rules (shared by KPIs, gauges and the verdict) ──────────────────────

def _tone_index(v):
    """SPI/CPI tone: good >= 0.98, warn >= 0.9, else bad. None → ''."""
    if v is None:
        return ''
    if v >= 0.98:
        return 'good'
    if v >= 0.9:
        return 'warn'
    return 'bad'


def _tone_delay(days):
    """Delay tone: good <= 0, warn <= 10, else bad. None → ''."""
    if days is None:
        return ''
    if days <= 0:
        return 'good'
    if days <= 10:
        return 'warn'
    return 'bad'


def _tone_complete(actual, planned):
    """% complete tone: good if actual >= planned-1, warn if >= planned-8, else bad."""
    if actual is None or planned is None:
        return ''
    if actual >= planned - 1:
        return 'good'
    if actual >= planned - 8:
        return 'warn'
    return 'bad'


def _verdict(spi, delay):
    """Overall schedule verdict + tone from SPI and delay together."""
    behind = (spi is not None and spi < 0.98) or (delay is not None and delay > 0)
    ahead = (spi is not None and spi >= 1.0) and (delay is None or delay <= 0)
    if ahead and not behind:
        return 'AHEAD', 'good'
    if behind:
        bad = (spi is not None and spi < 0.9) or (delay is not None and delay > 10)
        return 'BEHIND', ('bad' if bad else 'warn')
    return 'ON TRACK', 'good'


# ── the S-curve (grounded — reuses the compare engine, never a made-up shape) ─

def _pct100(frac):
    """A 0..1 fraction from metrics.compute() → a 0..100 percent, or None."""
    try:
        return float(frac) * 100.0 if frac is not None else None
    except (TypeError, ValueError):
        return None


def _anchor_curve(raw, dd_index, anchor, upper=100.0):
    """Monotonically re-map a raw 0..100 cumulative curve so its data-date point equals
    `anchor` (the EVM tab's own PV% / EV%), while 0 stays at the start and `upper` at the
    end. The grounded activity-spread SHAPE is preserved between the anchors; only the level
    is pinned, so the S-curve can never disagree with the SPI / %-complete KPIs on the same
    screen. `None` entries (the earned series past the data date) pass through untouched.
    Returns the raw curve (rounded) when `anchor` is None."""
    if not raw:
        return list(raw)
    if anchor is None:
        return [None if v is None else round(v, 1) for v in raw]
    anchor = max(0.0, min(upper, anchor))
    r_dd = raw[dd_index] if (dd_index < len(raw) and raw[dd_index] is not None) else None
    out = []
    for i, v in enumerate(raw):
        if v is None:
            out.append(None)
        elif i <= dd_index:
            if r_dd and r_dd > 1e-9:
                out.append(round(anchor * v / r_dd, 1))
            elif dd_index > 0:
                out.append(round(anchor * i / dd_index, 1))
            else:
                out.append(round(anchor, 1))
        else:
            gap = (upper - r_dd) if r_dd is not None else upper
            out.append(round(anchor + (upper - anchor) * (v - r_dd) / gap, 1)
                       if gap > 1e-9 else round(upper, 1))
    return out


def _scurve(data, metrics):
    acts = getattr(data, 'activities', {}) or {}
    data_date = _as_dt(metrics.get('data_date')) or _as_dt((getattr(data, 'project', None) or {}).get('data_date'))
    bl = getattr(data, 'baseline_by_id', None) or {}
    proj_fin = _project_finish(data)          # current schedule finish (also the forecast finish)
    bac_total = sum(_cost_weight(data, a) for a in acts.values())
    cost_loaded = bac_total > 0
    empty = {'months': [], 'plan': [], 'earn': [], 'fore': [], 'dd_index': 0,
             'bac_m': round(bac_total / 1e6, 4)}

    # earliest baseline/planned start → latest project/forecast finish
    starts = [b.get('planned_start') for b in bl.values() if b.get('planned_start')]
    for a in acts.values():
        s = a.get('planned_start') or a.get('remaining_early_start') or a.get('actual_start')
        if s:
            starts.append(s)
    dmin = min(starts) if starts else None
    fins = [b.get('planned_finish') for b in bl.values() if b.get('planned_finish')]
    dmax_cands = [d for d in (proj_fin,) if d] + ([max(fins)] if fins else [])
    dmax = max(dmax_cands) if dmax_cands else None
    if not dmin or not dmax or dmax <= dmin or not data_date:
        return empty

    boundaries = _month_boundaries(dmin, dmax)
    if len(boundaries) < 2:
        return empty
    months = [b.strftime('%b %y') for b in boundaries]

    # data-date month index (last boundary on/before the data date)
    dd_index = 0
    for i, b in enumerate(boundaries):
        if b <= data_date:
            dd_index = i
        else:
            break

    # ONE shared population + budget base for BOTH curves, so the visible plan-vs-earn gap is
    # a like-for-like schedule variance (not a duration curve against a cost curve). Cost
    # weight when the file is cost-loaded, else planned-duration weight — the same basis
    # metrics.compute() uses for PV/EV. Every activity carries a planned span (baseline) and
    # an earned span (actuals), built over exactly the same population so nothing drifts.
    use_cost = cost_loaded
    pop = []
    for a in acts.values():
        if a.get('task_type') != 'Task':
            continue
        w = _cost_weight(data, a) if use_cost else ((a.get('planned_duration') or 0.0) or 1.0)
        if w <= 0:
            continue
        b0 = bl.get(a.get('id')) or {}
        ps = (b0.get('planned_start') or a.get('planned_start')
              or a.get('actual_start') or a.get('remaining_early_start'))
        if not ps:                                    # can't place it on the timeline
            continue
        pf = (b0.get('planned_finish') or a.get('planned_finish')
              or a.get('remaining_early_finish') or a.get('actual_finish') or proj_fin or ps)
        es = (b0.get('planned_start') or a.get('actual_start')
              or a.get('planned_start') or a.get('remaining_early_start'))
        ef = (a.get('actual_finish') or a.get('remaining_early_finish')
              or a.get('planned_finish') or b0.get('planned_finish') or proj_fin or es)
        pop.append({'w': w, 'ps': ps, 'pf': pf, 'es': es, 'ef': ef,
                    'pct': a.get('percent_complete') or 0.0})
    denom = sum(p['w'] for p in pop) or 1.0

    def _frac(b, s, e):
        """Fraction (0..1) of a span [s,e] realised at boundary b; a step at s if zero-length."""
        if e <= s:
            return 1.0 if b >= s else 0.0
        if b >= e:
            return 1.0
        if b <= s:
            return 0.0
        return (b - s).total_seconds() / (e - s).total_seconds()

    # raw grounded curve SHAPES from the activity spreads (% of budget). plan spreads full
    # weight over the baseline span (capped at the finish); earn spreads weight×%complete over
    # the actual span up to the data date.
    raw_plan = [100.0 * sum(p['w'] * _frac(b, p['ps'],
                            (min(p['pf'], proj_fin) if proj_fin else p['pf'])) for p in pop) / denom
                for b in boundaries]
    raw_earn = []
    for i, b in enumerate(boundaries):
        if i > dd_index:
            raw_earn.append(None)
            continue
        raw_earn.append(100.0 * sum(p['w'] * p['pct'] * _frac(b, p['es'], min(data_date, p['ef']))
                                    for p in pop) / denom)

    # Anchor each curve's data-date point to the EVM tab's own PV/BAC and EV/BAC so the S-curve
    # can never disagree with the SPI / %-complete KPIs on the same screen (the plan-vs-earn
    # gap at the data date IS the schedule variance, and SPI = EV/PV = earn/plan there).
    plan = _anchor_curve(raw_plan, dd_index, _pct100(metrics.get('overall_planned_pct')))
    earn = _anchor_curve(raw_earn, dd_index, _pct100(metrics.get('overall_actual_pct')))
    earn_at_dd = earn[dd_index] if (dd_index < len(earn) and earn[dd_index] is not None) else 0.0

    # fore — a grounded straight line from (data date, earned) up to 100% at the forecast
    # finish; null before the data-date month, so it continues exactly where 'earn' stops.
    fore = [None] * len(boundaries)
    ff_idx = len(boundaries) - 1
    if proj_fin:
        for i, b in enumerate(boundaries):
            if b >= proj_fin:
                ff_idx = i
                break
    fore[dd_index] = earn_at_dd
    if ff_idx <= dd_index:
        for i in range(dd_index, len(boundaries)):
            fore[i] = 100.0
        fore[dd_index] = earn_at_dd
    else:
        span = ff_idx - dd_index
        for i in range(dd_index + 1, len(boundaries)):
            if i >= ff_idx:
                fore[i] = 100.0
            else:
                fore[i] = round(earn_at_dd + (100.0 - earn_at_dd) * (i - dd_index) / span, 1)

    return {'months': months, 'plan': plan, 'earn': earn, 'fore': fore,
            'dd_index': dd_index, 'bac_m': round(bac_total / 1e6, 4)}


# ── gap by activity-code (PV − EV per code value, £M) ────────────────────────

def _gap_by_code(data):
    scopes = scope_all(data) or {}
    if not scopes:
        return {'total_m': 0.0, 'label': '', 'rows': []}
    # pick the MOST cost-loaded code dimension (largest total budget)
    label = max(scopes, key=lambda t: scopes[t].get('total') or 0.0)
    rows_in = scopes[label].get('rows') or []
    gaps = []
    for r in rows_in:
        bac = _num(r.get('bac')) or 0.0
        planned = _num(r.get('planned')) or 0.0
        actual = _num(r.get('actual')) or 0.0
        gap_m = bac * (planned - actual) / 100.0 / 1e6      # +ve = behind (planned > actual)
        gaps.append({'code': r.get('value'), 'gap_m': round(gap_m, 4)})
    total_m = round(sum(g['gap_m'] for g in gaps), 4)
    gaps.sort(key=lambda g: -abs(g['gap_m']))
    if len(gaps) > 8:
        head, tail = gaps[:8], gaps[8:]
        head.append({'code': 'Other', 'gap_m': round(sum(g['gap_m'] for g in tail), 4)})
        gaps = head
    return {'total_m': total_m, 'label': label, 'rows': gaps}


# ── the public payload ───────────────────────────────────────────────────────

def build(data, metrics):
    """A grounded professional-dashboard payload from a parsed schedule + its metrics.compute
    result. Pure and fully guarded — a partial schedule still returns kpis/disciplines/
    time_status; absent figures come back as None rather than invented."""
    metrics = metrics or {}

    spi = _num(metrics.get('spi'))
    cpi = _num(metrics.get('cpi'))
    pv = _num(metrics.get('pv')) or 0.0
    ev = _num(metrics.get('ev')) or 0.0
    delay = metrics.get('delay_days')
    try:
        delay = int(delay) if delay is not None else None
    except (TypeError, ValueError):
        delay = None
    # compute() returns the overall/category progress as FRACTIONS (0..1); the dashboard shows
    # them as percentages. *100 ties them to the EVM tab: SPI = overall_actual / overall_planned,
    # and in the cost-loaded case oa*100 == EV/BAC*100 and op*100 == PV/BAC*100.
    _op = _num(metrics.get('overall_planned_pct'))
    _oa = _num(metrics.get('overall_actual_pct'))
    op = (_op * 100.0) if _op is not None else None
    oa = (_oa * 100.0) if _oa is not None else None

    cost_loaded = _file_has_cost(data)
    bac_total = sum(_cost_weight(data, a) for a in (getattr(data, 'activities', {}) or {}).values())

    # ── meta ──
    proj = getattr(data, 'project', None) or {}
    project_name = metrics.get('project_name') or proj.get('name') or proj.get('id') or 'Project'
    bl = getattr(data, 'baseline_by_id', None) or {}
    bl_fins = [b.get('planned_finish') for b in bl.values() if b.get('planned_finish')]
    baseline_finish = _fmt_day(max(bl_fins)) if bl_fins else None
    forecast_finish = _fmt_day(_project_finish(data))
    meta = {
        'project': project_name,
        'data_date': _fmt_day(metrics.get('data_date') or proj.get('data_date')) or '—',
        'baseline_finish': baseline_finish,
        'forecast_finish': forecast_finish,
        'cost_loaded': bool(cost_loaded),
        'bac_m': round(bac_total / 1e6, 4),
    }

    # ── health ──
    verdict, vtone = _verdict(spi, delay)
    sv_m = round((ev - pv) / 1e6, 4)          # £M, negative = behind (EV < PV)
    hbits = []
    if oa is not None and op is not None:
        hbits.append('Earned %.1f%% against a planned %.1f%%.' % (oa, op))
    if delay is not None:
        if delay > 0:
            hbits.append('%d working days behind the baseline finish.' % delay)
        elif delay < 0:
            hbits.append('%d working days ahead of the baseline finish.' % abs(delay))
        else:
            hbits.append('On the baseline finish.')
    health = {
        'verdict': verdict,
        'tone': vtone,
        'spi': spi,
        'message': ' '.join(hbits) if hbits else 'Not enough computed data for a verdict.',
        'schedule_variance_m': sv_m,
    }

    # ── kpis (exactly 6, in order) ──
    def _fx(v, dp=2):
        return ('%.*f' % (dp, v)) if v is not None else '—'
    kpis = [
        {'k': 'SPI', 'v': _fx(spi), 'h': 'schedule perf', 't': _tone_index(spi)},
        {'k': 'CPI', 'v': _fx(cpi), 'h': 'cost perf', 't': _tone_index(cpi)},
        {'k': '% complete',
         'v': ('%.1f%%' % oa) if oa is not None else '—',
         'h': ('vs %.1f%% planned' % op) if op is not None else 'vs planned',
         't': _tone_complete(oa, op)},
        {'k': 'Delay',
         'v': ('%+d wd' % delay) if delay is not None else '—',
         'h': 'vs baseline finish', 't': _tone_delay(delay)},
        {'k': 'Earned value', 'v': '£%.1fM' % (ev / 1e6), 'h': 'EV to date', 't': ''},
        {'k': 'Planned value', 'v': '£%.1fM' % (pv / 1e6), 'h': 'PV to date', 't': ''},
    ]

    # ── gauges ──
    gauges = [
        {'label': 'SPI', 'value': spi, 'tone': _tone_index(spi)},
        {'label': 'CPI', 'value': cpi, 'tone': _tone_index(cpi)},
    ]

    # ── time status (reuse the Update-Analysis engine) ──
    try:
        ts = time_status(data, metrics)
    except Exception:
        ts = {}
    time_status_out = {
        'elapsed_pct': _num(ts.get('elapsed_pct')),
        'earned_pct': _num(ts.get('actual_pct')),
        'start': _fmt_day(ts.get('baseline_start')),
        'finish': _fmt_day(ts.get('baseline_finish')),
        'exceeded_days': ts.get('exceeded_days'),
    }

    # ── disciplines (weightiest first, drop 0-weight structural rows, cap 8) ──
    cats = metrics.get('categories') or {}
    disciplines = []
    if isinstance(cats, dict):
        for name, c in cats.items():
            if not isinstance(c, dict):
                continue
            w = _num(c.get('weight')) or 0.0
            if w <= 0:                          # Milestones / Key Dates / Summary → dropped
                continue
            disciplines.append({
                'name': name,
                'planned': round((_num(c.get('planned_pct')) or 0.0) * 100.0, 1),   # fraction → %
                'actual': round((_num(c.get('actual_pct')) or 0.0) * 100.0, 1),
                '_w': w,
            })
    disciplines.sort(key=lambda d: -d['_w'])
    disciplines = [{'name': d['name'], 'planned': d['planned'], 'actual': d['actual']}
                   for d in disciplines[:8]]

    return {
        'ok': True,
        'meta': meta,
        'health': health,
        'kpis': kpis,
        'gauges': gauges,
        'time_status': time_status_out,
        'disciplines': disciplines,
        'gap_by_code': _gap_by_code(data),
        'scurve': _scurve(data, metrics),
    }


def build_from_snapshot(snapshot_id=None, xml_path=None):
    """Resolve the schedule XML (explicit ``xml_path``, else the best path for ``snapshot_id``),
    re-parse it, load config, compute metrics the way the app's report routes do, then return
    ``build(data, metrics)``. Fully guarded — returns ``{'ok': False, 'error': msg}`` on any
    failure or when there is no schedule/metrics."""
    try:
        import db
        from utils import resource_path
        from p6_evm.parser import parse_file
        from p6_evm.metrics import compute
        from p6_evm.classify import auto_categories, build_wbs_classifier

        path = xml_path
        if not path and snapshot_id is not None:
            try:
                path = db.get_snapshot_xml_path(snapshot_id)
            except Exception:
                path = None
        if not path or not os.path.isfile(path):
            return {'ok': False, 'error': 'Schedule not found — re-import it and try again.'}

        with open(resource_path('config.json')) as f:
            base_config = json.load(f)
        data = parse_file(path)
        cfg = dict(base_config)
        cfg['categories'] = auto_categories(data)
        metrics = compute(data, cfg, classifier=build_wbs_classifier(data))
        if not metrics:
            return {'ok': False, 'error': 'No metrics could be computed for this schedule.'}
        return build(data, metrics)
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}
