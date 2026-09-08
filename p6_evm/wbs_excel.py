"""Project ▸ WBS Excel exporter.

Turns the WBS summary the CLIENT already holds (state.currentResult.wbs_summary /
wbs_main) into the `sheets` structure consumed by
`p6_evm.xlsx_writer.write_sections_xlsx`, so the workbook MIRRORS the on-screen
WBS view — one sheet with the indented WBS table, one titled block per selectable
main branch (Engineering / Construction / …), exactly as the segmented control and
the File ▸ Print table (`_wbsPrint`) present them.

The client posts `report` = {
    'wbs_summary': pre-order list of WBS nodes (each rolled up to the activity-bearing
                   level), every node:
        {'id','parent','name','depth','activities',
         'planned','actual',          # weighted %, already 0–100 (or None)
         'start','finish',            # expected (current) ISO dates 'YYYY-MM-DD'
         'baseline_start','baseline_finish',
         'leaf': bool}
    'wbs_main':    [{'id','name'}]    # selectable top-level branches
    'project_name': str,
    'data_date':    ISO date,
}

Nothing is computed from the schedule here — it only re-presents the rolled-up
figures the WBS view already resolved (DB is the read path; no XML re-parse).
Columns mirror ui/modules/overview.js WBS_COLS + the indented WBS name, and Delay
= Expected Finish − Baseline Finish in calendar days (+late / −early), matching
overview.js `wbsDelay`. Never raises on empty/missing data: a 'No data' sheet is
returned instead.
"""
from datetime import datetime, date

# Column order mirrors overview.js WBS_COLS (all columns, as the print table shows them).
_HEADERS = ['WBS', 'Baseline Start', 'Baseline Finish', 'Expected Start',
            'Expected Finish', 'Planned %', 'Actual %', 'Delay (days)']
_INDENT = '    '                                  # 4 spaces per relative level


def _parse_date(iso):
    """ISO/date-ish → date, else None (tolerant of 'YYYY-MM-DD' and full timestamps)."""
    if not iso:
        return None
    if isinstance(iso, datetime):
        return iso.date()
    if isinstance(iso, date):
        return iso
    s = str(iso).strip()
    try:
        return datetime.fromisoformat(s.replace('Z', '').replace('T', ' ').strip()).date()
    except ValueError:
        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d-%b-%Y', '%d-%b-%y', '%m/%d/%Y'):
            try:
                return datetime.strptime(s[:10] if fmt == '%Y-%m-%d' else s, fmt).date()
            except ValueError:
                continue
    return None


def _fmt_date(iso):
    """ISO → '09 Feb 2026' (matches the screen's fmtShort en-GB day/short-month/year)."""
    d = _parse_date(iso)
    return d.strftime('%d %b %Y') if d else '—'


def _delay_days(node):
    """Expected Finish − Baseline Finish in calendar days (+late / −early), or None."""
    ef = _parse_date(node.get('finish'))
    bf = _parse_date(node.get('baseline_finish'))
    if ef is None or bf is None:
        return None
    return (ef - bf).days


def _num(v):
    """Keep a percent numeric for the cell (header carries the % meaning); None → '—'."""
    return v if isinstance(v, (int, float)) else '—'


def _row(node, base_depth):
    """One table row mirroring the on-screen WBS row, name indented by relative depth."""
    rel = max(0, (node.get('depth') or 0) - base_depth)
    name = _INDENT * rel + str(node.get('name') or '(WBS)')
    delay = _delay_days(node)
    return [
        name,
        _fmt_date(node.get('baseline_start')),
        _fmt_date(node.get('baseline_finish')),
        _fmt_date(node.get('start')),
        _fmt_date(node.get('finish')),
        _num(node.get('planned')),
        _num(node.get('actual')),
        delay if delay is not None else '—',
    ]


def _subset(nodes, main_id):
    """Slice the pre-order tree to `main_id` + its descendants (overview.js logic)."""
    start = next((i for i, n in enumerate(nodes) if str(n.get('id')) == str(main_id)), -1)
    if start < 0:
        return []
    base = nodes[start].get('depth') or 0
    out = [nodes[start]]
    for n in nodes[start + 1:]:
        if (n.get('depth') or 0) <= base:
            break
        out.append(n)
    return out


def _branch_note(subset):
    """The chip line above the on-screen table: activities + overall planned/actual %."""
    if not subset:
        return None
    root = subset[0]
    acts = root.get('activities')
    pl, ac = root.get('planned'), root.get('actual')
    pl_s = f'{pl:.1f}%' if isinstance(pl, (int, float)) else '—'
    ac_s = f'{ac:.1f}%' if isinstance(ac, (int, float)) else '—'
    n = f'{acts} activities' if acts is not None else 'activities —'
    return f'{n} · overall {pl_s} planned · {ac_s} actual'


def _block(title, subset):
    base = subset[0].get('depth') or 0 if subset else 0
    return {
        'title': title,
        'note': _branch_note(subset),
        'headers': _HEADERS,
        'rows': [_row(n, base) for n in subset],
    }


def wbs_excel(report):
    """(report dict the client holds) → `sheets` list for write_sections_xlsx.

    One sheet 'WBS' stacks the indented WBS table — one titled block per selectable
    main branch (as the segmented control offers them), or the whole tree as a single
    block when there are no distinct mains. Empty/missing data → a 'No data' sheet.
    """
    report = report or {}
    nodes = report.get('wbs_summary') or []
    mains = report.get('wbs_main') or []

    if not nodes:
        return [{'name': 'WBS',
                 'blocks': [{'title': 'WBS Summary', 'headers': _HEADERS,
                             'rows': [['No data', '—', '—', '—', '—', '—', '—', '—']]}],
                 'col_widths': _COL_WIDTHS}]

    blocks = []
    # One block per main branch (the segmented control's tabs). Emit only mains that
    # actually resolve to a slice; fall back to the whole tree if none do.
    for m in mains:
        sub = _subset(nodes, m.get('id'))
        if sub:
            blocks.append(_block(f"WBS Summary — {m.get('name') or '(WBS)'}", sub))
    if not blocks:
        # No distinct mains (single flat branch) → the full pre-order tree, one block.
        blocks.append(_block('WBS Summary', nodes))

    return [{'name': 'WBS', 'blocks': blocks, 'col_widths': _COL_WIDTHS}]


# WBS name column wide (it carries the indentation); dates/percent/delay comfortable.
_COL_WIDTHS = {0: 46, 1: 15, 2: 15, 3: 15, 4: 15, 5: 11, 6: 11, 7: 12}
