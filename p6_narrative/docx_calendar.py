"""Word Section-8 (Project Calendars & Holidays) renderer — redesigned.

Draws the four approved sub-blocks of §8 straight from the calendar section payload
emitted by :func:`p6_narrative.report.build_report` (which mirrors the P6 Calendar
Audit and already dropped the Shutdown-Periods / Baseline-Start / Baseline-Finish
fields from its dashboard):

    x.1  Executive Dashboard   — KPI tiles (WITHOUT a Shutdown-Periods tile)
    x.2  Calendar Timeline     — one NATIVE stacked histogram PER assigned calendar
                                 (net-working days green + non-working days red, the
                                 net-working-days value labelled on each bar), the
                                 window running from the data date to baseline completion
    x.3  Holidays              — a Date | Description table (no Days, no Weekday column)
    x.4  Working Hours Profile — one card per calendar's primary hours pattern

Payload shape (``report._calendars``)::

    {view:'calendars',
     header:{calendar_count, activity_count},
     dashboard:{…tiles, no shutdown…},
     calendars:[{name, activity_count, months:[label,…],
                 net_working_days:[int,…], nonworking_days:[int,…]}],
     holidays:[{date, description}],
     hours_profiles:[{name, hours, sub}]}

The composite builders (tiles / data_table / sub-headings) are reused from
:mod:`p6_narrative.docx_writer` (imported lazily so the two modules never form an import
cycle); the histogram is the native chart from :mod:`p6_narrative.docx_native`. Every
block is guarded on the presence of its payload key, so a partial calendar payload
renders whatever it has and never raises.
"""
from p6_narrative import docx_native

# Dashboard KPI tiles — the LIVE Calendar Audit labels, EXCLUDING Shutdown Periods
# (and the date / baseline fields the producer already stripped).
#   (label, dashboard-key, format)  format: None | 'hrs'
_DASH_TILES = [
    ('Total Calendar Days', 'total_calendar_days', None),
    ('Working Days', 'total_working_days', None),
    ('Non-Working Days', 'total_nonworking_days', None),
    ('Holidays', 'total_holidays', None),
    ('Avg Work Days / Month', 'avg_working_days_per_month', None),
    ('Avg Work Hours / Day', 'avg_working_hours_per_day', 'hrs'),
]


def render_calendar(document, payload, chrome=None, number=8):
    """Render Section-``number`` (Project Calendars & Holidays) into ``document`` from the
    calendar ``payload``. ``chrome`` is accepted for signature stability and ignored (the
    histogram is a native Word chart — no browser needed). The four sub-blocks are
    numbered ``number.1 … number.4`` (the caller places the parent heading)."""
    from p6_narrative import docx_writer as W   # lazy → no import cycle

    p = payload or {}
    header = p.get('header') or {}

    cc = header.get('calendar_count')
    ac = header.get('activity_count')
    if cc is not None or ac is not None:
        bits = []
        if cc is not None:
            bits.append('%s calendars assigned to activities' % cc)
        if ac is not None:
            bits.append('%s activities' % W._count(ac))
        W.para(document, ' · '.join(bits), size=11, color=W.GREY, after=4)

    # x.1) Executive Dashboard — KPI tiles (no Shutdown Periods)
    dash = p.get('dashboard') or {}
    tile_items = []
    for label, key, fmt in _DASH_TILES:
        v = dash.get(key)
        if v is None or v == '':
            continue
        v = '%s hrs' % v if fmt == 'hrs' else str(v)
        tile_items.append((label, v))
    if tile_items:
        W._subhead(document, '%s.1' % number, 'Executive Dashboard')
        W.tiles(document, tile_items, per_row=3, big_size=15, fill='F2F5F8',
                border='D7E0EA', height=42)

    # x.2) Calendar Timeline — one native stacked histogram per assigned calendar
    calendars = p.get('calendars') or []
    if calendars:
        W._subhead(document, '%s.2' % number,
                   'Calendar Timeline — net working days per month, per calendar '
                   '(from data date)')
        for cal in calendars:
            name = cal.get('name') or '—'
            acnt = cal.get('activity_count')
            title = name if acnt in (None, '') else '%s — %s activities' % (name, W._count(acnt))
            W.para(document, title, size=10.5, bold=True, color=W.SUBNAVY,
                   before=6, after=2, font=W.CAL)
            months = cal.get('months') or []
            working = cal.get('net_working_days') or []
            nonworking = cal.get('nonworking_days') or []
            if months and docx_native.add_calendar_hist(
                    document, months, working, nonworking) is None:
                # native chart unavailable → an editable monthly table fallback
                W.data_table(document, ['Month', 'Working', 'Non-working'],
                             [[m, w, nw] for m, w, nw in
                              zip(months, working, nonworking)],
                             widths=[2.3, 2.3, 2.3])

    # x.3) Holidays — Date | Description only
    holidays = p.get('holidays') or []
    if holidays:
        W._subhead(document, '%s.3' % number, 'Holidays')
        rows = [[h.get('date') or '', h.get('description') or ''] for h in holidays]
        W.data_table(document, ['Date', 'Description'], rows, widths=[1.8, 5.1])

    # x.4) Working Hours Profile — one card per calendar's primary hours pattern
    hours = p.get('hours_profiles') or []
    if hours:
        W._subhead(document, '%s.4' % number, 'Working Hours Profile')
        items = []
        for hp in hours:
            name = hp.get('name') or '—'
            val = hp.get('sub') or hp.get('hours') or ''
            if hp.get('hours') and hp.get('sub'):
                name = '%s · %s' % (name, hp.get('hours'))
            items.append((name, str(val)))
        W.tiles(document, items, per_row=min(len(items), 4) or 1, big_size=13,
                fill='F2F5F8', border='D7E0EA', height=44, numcolor=W.SUBNAVY)
    return document
