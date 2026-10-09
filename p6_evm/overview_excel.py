"""Project Overview Excel exporter.

Turns the parse result the CLIENT holds (state.currentResult) into the `sheets`
structure consumed by `p6_evm.xlsx_writer.write_sections_xlsx`, so the workbook
MIRRORS the on-screen Project ▸ Overview (ui/modules/overview.js · renderOverview)
as stacked titled tables rather than a flat dump.

The client posts `report` = {
    'result': the compute() result already on screen — carries project_name,
              data_date, activity_count, calendar_count, spi, cpi, delay_days,
              overall_planned_pct, overall_actual_pct, pv, ev, ac,
              expected_finish, baseline_finish, and categories
              {name: {planned_pct, actual_pct, activity_count, overridden, ...}},
    'meta':   {project_name, data_date, source_file, report_date} (optional supplement),
}

Every figure and its formatting mirrors renderOverview (the authoritative display) so
the exported numbers equal exactly what the planner sees. Nothing is computed from
scratch — it only presents what the parse result already resolved (the one exception,
matching the screen, is the Delay fallback = expected_finish − baseline_finish in days
when the schedule carries no milestone-float delay_days). Never raises on empty data.
"""
from datetime import datetime

_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _parse_date(iso):
    """ISO/date-ish string (or datetime) → datetime, or None."""
    if not iso:
        return None
    if hasattr(iso, 'strftime'):
        return iso
    s = str(iso).strip()
    try:
        return datetime.fromisoformat(s.replace('Z', '').replace('T', ' ').strip())
    except ValueError:
        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d-%b.%Y', '%d-%b-%Y', '%d-%b-%y', '%m/%d/%Y'):
            try:
                return datetime.strptime(s[:10] if fmt == '%Y-%m-%d' else s, fmt)
            except ValueError:
                continue
    return None


def _fmt_date(iso):
    """ISO/date → '09 Feb 2026' (matches the screen's fmtDate en-GB day/short-month/year)."""
    d = _parse_date(iso)
    if not d:
        return '—'
    return f'{d.day:02d}-{_MONTHS[d.month - 1]}.{d.year}'


def _pct2(frac):
    """Fraction (0–1) → numeric whole-percent to 2 dp, mirroring renderOverview's pct()."""
    if frac is None:
        return '—'
    try:
        return round(frac * 100, 2)
    except (TypeError, ValueError):
        return '—'


def _round2(x):
    try:
        return round(x, 2)
    except (TypeError, ValueError):
        return x if x is not None else '—'


def _num(x):
    """Numeric passthrough (kept numeric so figures stay computable); '—' when absent."""
    if x is None:
        return '—'
    try:
        return round(x) if isinstance(x, float) and x == int(x) else x
    except (TypeError, ValueError):
        return x


def _delay_days(result):
    """Delay in days, exactly as renderOverview resolves it: result.delay_days, else
    (expected_finish − baseline_finish) in calendar days when both are present."""
    d = result.get('delay_days')
    if d is not None:
        return d
    ef = _parse_date(result.get('expected_finish'))
    bf = _parse_date(result.get('baseline_finish'))
    if ef and bf:
        return (ef - bf).days
    return None


def _spi_status(spi):
    if spi is None:
        return ''
    return 'behind schedule' if spi < 1 else 'ahead / on schedule'


def _summary_block(result, meta):
    """Header chips → a small key/value table (Project · Data date · Activities · Calendars · WBS)."""
    cats = result.get('categories') or {}
    project = result.get('project_name') or meta.get('project_name') or 'Project'
    rows = [
        ['Project', project],
        ['Data date', _fmt_date(result.get('data_date') or meta.get('data_date'))],
        ['Activities', _num(result.get('activity_count'))],
        ['Calendars', _num(result.get('calendar_count'))],
    ]
    cl = result.get('cost_loaded') or None
    if cl:
        rows.append(['Cost-loaded activities', _num(cl.get('activities'))])
    else:
        rows.append(['WBS categories', len(cats)])
    if meta.get('source_file'):
        rows.append(['Source file', meta.get('source_file')])
    if meta.get('report_date'):
        rows.append(['Report date', meta.get('report_date')])
    return {'title': 'Project Summary', 'headers': ['Field', 'Value'], 'rows': rows}


def _kpi_block(result, approx=False):
    """The 10 KPI tiles, in screen order — numbers kept numeric, dates formatted. ``approx``
    (the update's own Planned dates stand in for its baseline) marks the baseline-derived rows
    '· approx', as the screen does."""
    ax = ' · approx' if approx else ''
    # Owner comment 93: Planned %, Actual %, PV, EV and SPI come from the COST-LOADED
    # activities only (budget-weighted, as P6 weights them); no CPI. A schedule with no cost
    # loading keeps its duration-weighted figures.
    cl = result.get('cost_loaded') or None
    src = cl or {'planned_pct': result.get('overall_planned_pct'), 'actual_pct': result.get('overall_actual_pct'),
                 'pv': result.get('pv'), 'ev': result.get('ev'), 'spi': result.get('spi')}
    spi = src.get('spi')
    tag = ''
    delay = _delay_days(result)
    delay_note = '' if delay is None else ('late' if delay > 0 else ('early' if delay < 0 else 'on time'))
    rows = [
        ['SPI · schedule' + ax, _round2(spi) if spi is not None else '—', _spi_status(spi)],
        ['Forecast finish', _fmt_date(result.get('expected_finish')), ''],
        ['Delay' + ax, delay if delay is not None else '—', ('days ' + delay_note).strip() if delay is not None else ''],
        ['Baseline finish' + ax, _fmt_date(result.get('baseline_finish')), ''],
        ['Planned %' + tag + ax, _pct2(src.get('planned_pct')), ''],
        ['Actual %' + tag, _pct2(src.get('actual_pct')), ''],
        ['Planned value' + ax, _num(src.get('pv')), 'EGP'],
        ['Earned value', _num(src.get('ev')), 'EGP'],
    ]
    u = (result.get('uncosted') or {}).get('summary')
    if u:
        rows.append(['Without cost - by count' + ax, '%s%% actual (started) · %s%% planned (due by cut-off)' % (u.get('actual_pct'), u.get('planned_pct')),
                     '%s activities, milestones excluded' % u.get('n')])
    note = ('Taken from the %s cost-loaded activities only (of %s), each weighted by its budget as P6 weights it. '
            'Activities with no cost - Engineering, Procurement - are not included. SPI = Actual %% / Planned %%.'
            % (cl.get('activities'), cl.get('all_activities'))) if cl else \
           'This schedule carries no cost loading, so Planned % and Actual % are weighted by activity duration.'
    return {'title': 'Key Indicators', 'note': note, 'headers': ['Indicator', 'Value', 'Note'], 'rows': rows}


def _zero(v):
    return not (abs(v or 0) >= 0.00005)


def _category_block(result, approx=False, group_key=None, hide_zero=False):
    """Progress by WBS / by a P6 activity code (owner comment 94) for the cost-loaded
    activities — the grouping picked on screen; else one row per WBS category."""
    groups = result.get('progress_groups') or [] if result.get('cost_loaded') else []
    group = next((g for g in groups if g.get('key') == group_key), groups[0] if groups else None)
    if group:
        label = 'WBS' if group.get('key') == 'wbs' else 'Activity code - %s' % group.get('label')
        return {
            'title': 'Progress by %s' % group.get('label'),
            'note': 'Planned vs actual % of the cost-loaded activities, weighted by budget.',
            'headers': [label, 'Activities', 'Planned % · approx' if approx else 'Planned %', 'Actual %', 'Budget'],
            'rows': [[r.get('name'), _num(r.get('activities')), _pct2(r.get('planned_pct')),
                      _pct2(r.get('actual_pct')), _num(r.get('bac'))] for r in group.get('rows') or []
                     if not (hide_zero and _zero(r.get('planned_pct')) and _zero(r.get('actual_pct')))]
                    or [['Every value has Planned 0 % and Actual 0 %.', '', '', '', '']],
        }
    cats = result.get('categories') or {}
    rows = []
    for name, c in cats.items():
        rows.append([
            name,
            _num(c.get('activity_count')),
            _pct2(c.get('planned_pct')),
            _pct2(c.get('actual_pct')),
            'manual override' if c.get('overridden') else '',
        ])
    if not rows:
        rows = [['No categories configured for this schedule.', '—', '—', '—', '']]
    return {
        'title': 'Progress by Category',
        'note': 'Planned vs actual % per WBS category — the same figures the modules and PDF use.',
        'headers': ['WBS Category', 'Activities', 'Planned % · approx' if approx else 'Planned %', 'Actual %', 'Note'],
        'rows': rows,
    }


def overview_excel(report):
    """(report dict the client holds) → `sheets` list for write_sections_xlsx.

    Sheet 'Project Overview' stacks the three overview sections (Project Summary, Key
    Indicators, Progress by Category), mirroring the single-page Overview screen. Never
    raises on empty/missing data: a 'No data' sheet is returned instead.
    """
    report = report or {}
    result = report.get('result') or {}
    meta = report.get('meta') or {}
    approx = bool(report.get('baseline_approx'))

    has_any = bool(result.get('categories')) or result.get('spi') is not None \
        or result.get('pv') is not None or result.get('overall_actual_pct') is not None \
        or result.get('activity_count') is not None
    if not has_any:
        return [{'name': 'Project Overview',
                 'blocks': [{'title': 'Project Overview', 'headers': ['Metric', 'Value'],
                             'rows': [['No data', 'Import a P6 schedule and open Overview first.']]}]}]

    return [{
        'name': 'Project Overview',
        'blocks': [_summary_block(result, meta), _kpi_block(result, approx),
                   _category_block(result, approx, report.get('progress_group'), bool(report.get('hide_zero')))],
        'col_widths': {0: 30, 1: 20, 2: 18, 3: 14, 4: 18},
    }]
