"""Schedule (Gantt) Excel exporter.

Turns the parse `result` the CLIENT holds into the `sheets` structure consumed by
`p6_evm.xlsx_writer.write_sections_xlsx`, so the workbook MIRRORS the on-screen
Schedule (Gantt) view (ui/modules/gantt.js) rather than a flat dump.

On screen the view draws
one time-scaled bar per activity from `result.activities`, grouped by top-level WBS,
groups ordered by their earliest start, activities within a group ordered by start.
The workbook reproduces that layout: one 'Schedule' sheet whose stacked titled tables
are the WBS groups, each listing its activities in the same order.

`result.activities` is the SLIM, JSON-safe activity list `_handle_parse()` attaches
(NOT the heavy `records`). Each item is:
    {id, name, wbs, wbs_top, wbs_top_id, start, finish, planned_start, planned_finish,
     status, pct, tf, critical, milestone}
  - `start` / `finish` are the CURRENT dates as ISO strings (actual where started /
    finished, remaining early otherwise — p6_evm.schedule_view); only rows with both are kept
  - `wbs` is the WBS path from the top level down; `wbs_top` / `wbs_top_id` the group
  - `pct` is a whole-percent int (0-100); `tf` total float in days (None when unknown)
  - `critical` is True when total float <= 0 and the work is not finished
  - `milestone` is True for Start/Finish milestone activities
A result stored by an older version has no status / tf / planned dates: those cells are
left blank, never guessed.

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
        return iso.strftime('%d-%b.%Y')
    s = str(iso).strip()
    parsed = None
    try:
        parsed = datetime.fromisoformat(s.replace('Z', '').replace('T', ' ').strip())
    except ValueError:
        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d-%b.%Y', '%d-%b-%Y', '%d-%b-%y', '%m/%d/%Y'):
            try:
                parsed = datetime.strptime(s[:10] if fmt == '%Y-%m-%d' else s, fmt)
                break
            except ValueError:
                continue
    return parsed.strftime('%d-%b.%Y') if parsed else s[:11]


_HEADERS = ['Activity ID', 'Activity Name', 'WBS', 'Status', 'Start', 'Finish',
            'Planned Start', 'Planned Finish', '% Complete', 'Total Float (d)', 'Critical', 'Type']
_WIDTHS = {0: 18, 1: 44, 2: 46, 3: 13, 4: 14, 5: 14, 6: 14, 7: 14, 8: 12, 9: 14, 10: 10, 11: 12}
_NOTE = ('Start / Finish are the current dates, as P6 shows them: actual where the work has started '
         'or finished, the remaining early dates for the rest. Critical = total float of zero or '
         'less and not finished (milestones included). Grouped by top-level WBS, earliest first.')


def _row(a):
    """One activity → a table row, mirroring the on-screen bar's data. `% Complete`
    stays NUMERIC; dates are formatted like the screen; critical/type read as labels."""
    return [
        a.get('id') or '',
        a.get('name') or '',
        a.get('wbs') or '',
        a.get('status') or '',
        _fmt_date(a.get('start')),
        _fmt_date(a.get('finish')),
        _fmt_date(a.get('planned_start')) if a.get('planned_start') else '',
        _fmt_date(a.get('planned_finish')) if a.get('planned_finish') else '',
        a.get('pct') if isinstance(a.get('pct'), (int, float)) else 0,
        a.get('tf') if isinstance(a.get('tf'), (int, float)) else '',
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
        note = ('No activity timeline is available. The schedule file of this project is no longer '
                'on this computer, so its Gantt cannot be rebuilt — import the schedule again to '
                'show it.') if result.get('activity_count') else \
               'Import a P6 schedule and open Schedule (Gantt) first.'
        return [{'name': 'Schedule',
                 'blocks': [{'title': 'Schedule (Gantt)', 'note': note,
                             'headers': _HEADERS, 'rows': [['No data'] + [''] * (len(_HEADERS) - 1)]}],
                 'col_widths': _WIDTHS}]

    # Group by top-level WBS, keyed by its id so two WBS with the same name never merge
    # (matches gantt.js ganttGroups: a.wbs_top_id || a.wbs_top || 'Ungrouped').
    groups, names = {}, {}
    for a in acts:
        key = a.get('wbs_top_id') or a.get('wbs_top') or 'Ungrouped'
        groups.setdefault(key, []).append(a)
        names.setdefault(key, a.get('wbs_top') or 'Ungrouped')
    # Groups ordered by earliest start; activities within a group ordered by start.
    order = sorted(groups, key=lambda g: min(_start_ms(x) for x in groups[g]))

    crit = sum(1 for a in acts if a.get('critical'))
    ms = sum(1 for a in acts if a.get('milestone'))
    summary = {
        'title': 'Schedule (Gantt)',
        'note': _NOTE,
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
            'title': names[g],
            'note': f'{len(rows)} activit{"y" if len(rows) == 1 else "ies"}',
            'headers': _HEADERS,
            'rows': rows,
        })

    return [{'name': 'Schedule', 'blocks': blocks, 'col_widths': _WIDTHS}]
