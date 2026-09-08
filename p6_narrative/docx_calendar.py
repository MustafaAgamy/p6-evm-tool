"""SLICE D — Word Section-5 (Project Calendars & Holidays) renderer.

Draws the LIVE *P6 Calendar Audit* feature's five pieces into a python-docx
``Document`` from the SLICE A calendar payload (the widened Calendar-Audit
passthrough carried on the narrative's calendar section), EXCLUDING the Baseline
Start / Baseline Finish dates (those are cover meta, not Section-5 content and were
already dropped from the dashboard block by the builder):

    5.1)  Dashboard tiles      — a compact borderless label/value grid
    5.2)  Monthly histogram    — a NATIVE, editable stacked working(green)/non-working
                                 (red) per-month column chart (a real Word chart object,
                                 not a rasterised image); falls back to a monthly stats
                                 table (Month | Working | Non-working | Holidays | Hours)
                                 only if the native chart cannot be built
    5.3)  National holidays     — Date | Weekday | Reason
    5.4)  Working hours         — Profile | Hours | Hours/Day | Days/Week | Note
    5.5)  Comparison & usage    — Calendar | Hrs/Day | Days/Week | Non-working ahead |
                                 Default?  followed by  Calendar | Activities | % | Role

The module consumes B's template furniture (``docx_template``) and the native-chart
builder (``docx_native.add_bar_chart_stacked``); it re-uses the shared numbered
sub-heading + styled-table helpers so the section matches the rest of the report.
Every block is guarded on the presence of its payload key, so a partial calendar
payload renders whatever it has and never raises.
"""
import html as _h
import math
import re

from docx.shared import Pt

from p6_narrative import docx_native, docx_template


# ── local helpers ─────────────────────────────────────────────────────────────
def _esc(x):
    return _h.escape('' if x is None else str(x))


def _num(x):
    return '' if x is None else str(x)


def _days_per_week(sub):
    """Pull the numeric days/week out of an hours-profile ``sub`` string
    (e.g. '5 days/week' -> '5'); pass the string through if no number is found."""
    m = re.search(r'(\d+(?:\.\d+)?)', str(sub or ''))
    return m.group(1) if m else _num(sub)


# Dashboard tiles — the LIVE Calendar Audit labels, EXCLUDING Baseline Start/Finish.
# (label, dashboard-key, format)  format: None | 'date' | 'hrs'
_DASH_TILES = [
    ('Total Calendar Days', 'total_calendar_days', None),
    ('Working Days', 'total_working_days', None),
    ('Non-Working Days', 'total_nonworking_days', None),
    ('Holidays', 'total_holidays', None),
    ('Exceptions', 'total_exceptions', None),
    ('Shutdown Periods', 'shutdown_periods', None),
    ('Avg Working Days / Month', 'avg_working_days_per_month', None),
    ('Avg Working Hours / Day', 'avg_working_hours_per_day', 'hrs'),
    ('Data Date', 'data_date', 'date'),
    ('Forecast Finish', 'project_finish', 'date'),
]


# ── 5.1) dashboard tiles ───────────────────────────────────────────────────────
def _dashboard_tiles(document, dash):
    pairs = []
    for label, key, fmt in _DASH_TILES:
        v = dash.get(key)
        if v is None or v == '':
            continue
        if fmt == 'date':
            v = docx_template.full_date(v)
        elif fmt == 'hrs':
            v = '%s hrs' % v
        pairs.append((label, str(v)))
    if not pairs:
        return None

    per_row = 2                                   # two label/value tiles per row
    nrows = math.ceil(len(pairs) / per_row)
    table = document.add_table(rows=nrows, cols=per_row * 2)
    table.autofit = True
    for idx, (label, val) in enumerate(pairs):
        r, base = divmod(idx, per_row)
        c = base * 2
        lab_cell = table.rows[r].cells[c]
        val_cell = table.rows[r].cells[c + 1]
        lr = lab_cell.paragraphs[0].add_run(label)
        docx_template._set_run_font(lr, 'Calibri', size=8.5, color=docx_template.GREY)
        vr = val_cell.paragraphs[0].add_run(val)
        docx_template._set_run_font(vr, 'Calibri', size=10.5, bold=True,
                                    color=docx_template.NAVY)
    return table


# ── 5.2) monthly histogram (SVG → PNG) with table fallback ─────────────────────
def _monthly_total(m):
    """Total days in the month row (calendar days), from its per-day list when
    present, else working + (holidays/exceptions) as a floor."""
    days = m.get('days') or []
    if days:
        return len(days)
    wd = m.get('working_days', 0) or 0
    return wd + max(m.get('holidays', 0) or 0, m.get('exceptions', 0) or 0)


def _monthly_table(document, months):
    rows = []
    for m in months:
        total = _monthly_total(m)
        wd = m.get('working_days', 0) or 0
        nwd = max(total - wd, 0)
        rows.append([m.get('label'), wd, nwd,
                     m.get('holidays', 0), m.get('working_hours', 0)])
    return docx_template.styled_table(
        document, ['Month', 'Working', 'Non-working', 'Holidays', 'Hours'], rows)


def _monthly(document, months, chrome):
    """NATIVE stacked working(green)/non-working(red) per-month column chart — a real,
    editable Word chart object, NOT a rasterised SVG. Falls back to the monthly stats
    table only if the native chart cannot be built. ``chrome`` is now unused (kept for
    signature stability with the caller)."""
    months = months or []
    cats = [m.get('label') or '' for m in months]
    working = [m.get('working_days', 0) or 0 for m in months]
    nonworking = [max(_monthly_total(m) - (m.get('working_days', 0) or 0), 0)
                  for m in months]
    drawing = docx_native.add_bar_chart_stacked(
        document, cats,
        [{'name': 'Working days', 'values': working, 'color': '22C55E'},
         {'name': 'Non-working days', 'values': nonworking, 'color': 'EF4444'}],
        'Working / non-working days by month')
    if drawing is None:
        _monthly_table(document, months)


# ── 5.3) national holidays ─────────────────────────────────────────────────────
def _holidays(document, rows):
    hr = [[docx_template.full_date(h.get('date')) or h.get('display'),
           h.get('weekday'), h.get('reason') or ''] for h in rows]
    return docx_template.styled_table(document, ['Date', 'Weekday', 'Reason'], hr)


# ── 5.4) working hours ─────────────────────────────────────────────────────────
def _hours(document, profiles):
    rows = [[p.get('name'), p.get('hours'), p.get('hours_per_day'),
             _days_per_week(p.get('sub')), p.get('sub') or ''] for p in profiles]
    return docx_template.styled_table(
        document, ['Profile', 'Hours', 'Hours/Day', 'Days/Week', 'Note'], rows)


# ── 5.5) comparison + usage ────────────────────────────────────────────────────
def _comparison(document, rows):
    cr = [[r.get('name'), r.get('hours_per_day'), r.get('days_per_week'),
           r.get('exceptions'), 'Yes' if r.get('is_default') else 'No'] for r in rows]
    return docx_template.styled_table(
        document, ['Calendar', 'Hours/Day', 'Days/Week', 'Non-working ahead',
                   'Default?'], cr)


def _usage(document, rows):
    ur = [[r.get('name'), r.get('activities'), '%s%%' % _num(r.get('pct')),
           r.get('role')] for r in rows]
    return docx_template.styled_table(
        document, ['Calendar', 'Activities', '%', 'Role'], ur)


# ── entry point ────────────────────────────────────────────────────────────────
def render_calendar(document, payload, chrome, number=5):
    """Render Section-``number`` (Project Calendars & Holidays) into ``document`` from
    the SLICE A calendar ``payload``. ``chrome`` is a Chrome path for chart rasterising
    (None → the monthly histogram falls back to a stats table). The five sub-blocks are
    numbered ``number.1 … number.5`` so they follow the ACTUAL parent section number
    (the caller places the parent heading)."""
    p = payload or {}

    # x.1) Dashboard tiles
    dash = p.get('dashboard')
    if dash:
        docx_template.subheading(document, docx_template.format_number((number, 1)),
                                 'Calendar dashboard')
        _dashboard_tiles(document, dash)

    # x.2) Monthly histogram (or fallback table)
    monthly = p.get('monthly')
    if monthly:
        docx_template.subheading(document, docx_template.format_number((number, 2)),
                                 'Working / non-working days by month')
        _monthly(document, monthly, chrome)

    # x.3) National holidays
    holiday_dates = p.get('holiday_dates')
    if holiday_dates:
        docx_template.subheading(document, docx_template.format_number((number, 3)),
                                 'National holidays')
        _holidays(document, holiday_dates)

    # x.4) Working hours
    hours_profiles = p.get('hours_profiles')
    if hours_profiles:
        docx_template.subheading(document, docx_template.format_number((number, 4)),
                                 'Working hours')
        _hours(document, hours_profiles)

    # x.5) Comparison + usage
    comparison = p.get('comparison')
    usage = p.get('usage')
    if comparison or usage:
        docx_template.subheading(document, docx_template.format_number((number, 5)),
                                 'Calendar comparison & usage')
        if comparison:
            _comparison(document, comparison)
        if usage:
            _usage(document, usage)
    return document
