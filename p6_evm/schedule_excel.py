"""Schedule (Gantt) Excel exporter.

Turns the parse `result` the CLIENT holds into the `sheets` structure consumed by
`p6_evm.xlsx_writer.write_sections_xlsx`, so the workbook MIRRORS the on-screen
Schedule (Gantt) view (ui/modules/gantt.js) rather than a flat dump.

The Gantt view has no PDF today — this Excel is its first export. On screen it draws
one time-scaled bar per activity from `result.activities`, grouped by top-level WBS,
groups ordered by their earliest start, activities within a group ordered by start.
The workbook reproduces that layout: one 'Schedule' sheet whose stacked titled tables
are the WBS groups, each listing its activities in the same order.

`result.activities` is the SLIM, JSON-safe activity list `_handle_parse()` attaches
(NOT the heavy `records`). Each item is:
    {id, name, wbs, wbs_top, start, finish, pct, critical, milestone}
  - `start` / `finish` are ISO strings (only rows with both dates are kept)
  - `pct` is a whole-percent int (0-100)
  - `critical` is True when total float <= 0 (the view has no raw float field)
  - `milestone` is True for Start/Finish milestone activities

Nothing is computed here — it only presents what the parse already resolved. Never
raises on empty/missing data: a 'No data' block is returned instead.
"""
from datetime import datetime

_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _fmt_date(iso):
    """ISO/date → '09 Feb 2026' (mirrors the screen's fmtDate en-GB day/short-month/year)."""
    if not iso:
        return '—'
    if hasattr(iso, 'strftime'):
        return iso.strftime('%d %b %Y')
    s = str(iso).strip()
    parsed = None
    try:
        parsed = datetime.fromisoformat(s.replace('Z', '').replace('T', ' ').strip())
    except ValueError:
        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d-%b-%Y', '%d-%b-%y', '%m/%d/%Y'):
            try:
                parsed = datetime.strptime(s[:10] if fmt == '%Y-%m-%d' else s, fmt)
                break
            except ValueError:
                continue
    return parsed.strftime('%d %b %Y') if parsed else s[:11]


_HEADERS = ['Activity ID', 'Activity Name', 'WBS', 'Start', 'Finish',
            '% Complete', 'Critical', 'Type']


def _row(a):
    """One activity → a table row, mirroring the on-screen bar's data. `% Complete`
    stays NUMERIC; dates are formatted like the screen; critical/type read as labels."""
    return [
        a.get('id') or '',
        a.get('name') or '',
        a.get('wbs') or '',
        _fmt_date(a.get('start')),
        _fmt_date(a.get('finish')),
        a.get('pct') if isinstance(a.get('pct'), (int, float)) else 0,
        'Yes' if a.get('critical') else 'No',
        'Milestone' if a.get('milestone') else 'Activity',
    ]


def _start_ms(a):
    """Sort key = the activity's start (ISO strings sort chronologically); undated last."""
    return str(a.get('start') or '~')


def schedule_excel(result):
    """(parse result the client holds) → `sheets` list for write_sections_xlsx.

    One 'Schedule' sheet. Its first block is a summary (activity count + data date);
    then one titled block per top-level WBS group — groups ordered by earliest start,
    activities within a group ordered by start — exactly as gantt.js lays them out.
    Empty/missing activities → a single 'No data' block (never raises).
    """
    result = result or {}
    acts = result.get('activities') or []

    if not acts:
        note = ('No activity timeline is available. Re-import this schedule to build the '
                'Gantt — a re-opened project loads from the database, which stores rolled-up '
                'metrics rather than per-activity dates.') if result.get('activity_count') else \
               'Import a P6 schedule and open Schedule (Gantt) first.'
        return [{'name': 'Schedule',
                 'blocks': [{'title': 'Schedule (Gantt)', 'note': note,
                             'headers': _HEADERS, 'rows': [['No data', '', '', '', '', '', '', '']]}],
                 'col_widths': {0: 18, 1: 44, 2: 40, 3: 14, 4: 14, 5: 12, 6: 10, 7: 12}}]

    # Group by top-level WBS (matches gantt.js: groups[a.wbs_top || 'Ungrouped']).
    groups = {}
    for a in acts:
        groups.setdefault(a.get('wbs_top') or 'Ungrouped', []).append(a)
    # Groups ordered by earliest start; activities within a group ordered by start.
    order = sorted(groups, key=lambda g: min(_start_ms(x) for x in groups[g]))

    crit = sum(1 for a in acts if a.get('critical'))
    ms = sum(1 for a in acts if a.get('milestone'))
    summary = {
        'title': 'Schedule (Gantt)',
        'note': ('Current-schedule bars (planned start → finish) with % complete; critical '
                 'activities (total float ≤ 0) flagged; milestones typed. Grouped by top-level WBS.'),
        'headers': ['Metric', 'Value'],
        'rows': [
            ['Activities', len(acts)],
            ['Critical activities', crit],
            ['Milestones', ms],
            ['WBS groups', len(order)],
            ['Data date', _fmt_date(result.get('data_date'))],
            ['Project', result.get('project_name') or 'Schedule'],
        ],
    }

    blocks = [summary]
    for g in order:
        rows = [_row(a) for a in sorted(groups[g], key=_start_ms)]
        blocks.append({
            'title': g,
            'note': f'{len(rows)} activit{"y" if len(rows) == 1 else "ies"}',
            'headers': _HEADERS,
            'rows': rows,
        })

    return [{'name': 'Schedule', 'blocks': blocks,
             'col_widths': {0: 18, 1: 44, 2: 40, 3: 14, 4: 14, 5: 12, 6: 10, 7: 12}}]
