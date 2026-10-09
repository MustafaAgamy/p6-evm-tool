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
= Baseline Finish − Expected Finish in calendar days (−late / +early), matching
overview.js `wbsDelay`. Never raises on empty/missing data: a 'No data' sheet is
returned instead.
"""
from datetime import datetime, date

# Column order mirrors overview.js WBS_COLS (all columns, as the print table shows them).
_HEADERS = ['WBS', 'Baseline Start', 'Baseline Finish', 'Expected Start',
            'Expected Finish', 'Planned %', 'Actual %', 'Delay (Calendar days)']
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
        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d-%b.%Y', '%d-%b-%Y', '%d-%b-%y', '%m/%d/%Y'):
            try:
                return datetime.strptime(s[:10] if fmt == '%Y-%m-%d' else s, fmt).date()
            except ValueError:
                continue
    return None


def _fmt_date(iso):
    """ISO → '09 Feb 2026' (matches the screen's fmtShort en-GB day/short-month/year)."""
    d = _parse_date(iso)
    return d.strftime('%d-%b.%Y') if d else '—'


def _delay_days(node):
    """Delay (Calendar days) = Baseline Finish - Expected Finish, the two dates on the row, in
    calendar days (negative = later than the baseline) - the same figure as the screen."""
    ef = _parse_date(node.get('finish'))
    bf = _parse_date(node.get('baseline_finish'))
    if ef is None or bf is None:
        return None
    return (bf - ef).days


def _num(v):
    """Keep a percent numeric for the cell (header carries the % meaning); None → '—'."""
    return v if isinstance(v, (int, float)) else '—'


def _has_pct(node):
    """A WBS with no cost-loaded activity carries no Planned % / Actual % (owner comment 63).
    Rows stored before the flag existed keep whatever they hold."""
    return 'cost_loaded' not in node or (node.get('cost_loaded') or 0) > 0 or node.get('planned') is not None


def _pct(node, key):
    """Planned % / Actual % of a WBS: the cost-loaded % when it carries cost, else the COUNT-BASED % of
    its activities (planned = baseline finish on/before the cut-off, actual = started)."""
    if 'cost_loaded' in node and not (node.get('cost_loaded') or 0) > 0 and node.get(key) is None:
        return _num(node.get('planned_count_pct' if key == 'planned' else 'actual_count_pct'))
    return _num(node.get(key))


def _d(iso, actual):
    t = _fmt_date(iso)
    return (t + ' A') if (actual and t and t != '—') else t


def _row(node, base_depth):
    """One table row mirroring the on-screen WBS row, name indented by relative depth."""
    rel = max(0, (node.get('depth') or 0) - base_depth)
    name = _INDENT * rel + str(node.get('name') or '(WBS)')
    delay = _delay_days(node)
    return [
        name,
        _fmt_date(node.get('baseline_start')),
        _fmt_date(node.get('baseline_finish')),
        _d(node.get('start'), node.get('start_actual')),
        _d(node.get('finish'), node.get('finish_actual')),
        _pct(node, 'planned'),
        _pct(node, 'actual'),
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
    if not _has_pct(root):                              # no cost: the count-based %
        pl, ac = root.get('planned_count_pct'), root.get('actual_count_pct')
    pl_s = f'{pl:.1f}%' if isinstance(pl, (int, float)) else '—'
    ac_s = f'{ac:.1f}%' if isinstance(ac, (int, float)) else '—'
    n = f'{acts} activities' if acts is not None else 'activities —'
    return f'{n} · overall {pl_s} planned · {ac_s} actual · Delay (Calendar days) = Baseline Finish − Expected Finish (negative = late)'


# columns measured against the baseline — '· approx' when the update's own Planned dates stand in
_BL_HEADERS = {'Baseline Start', 'Baseline Finish', 'Planned %', 'Delay (Calendar days)'}


def _block(title, subset, approx=False, buckets=None, unit='month', cutoff=None):
    """One WBS table; with `buckets` its Gantt is drawn in cells to the right - an amber cell
    for every month a summary WBS runs, blue for a WBS that holds the activities, the Actual %
    part of each bar in dark blue."""
    from p6_evm.xlsx_writer import gantt_header, gantt_cells, BAR_BLUE, BAR_AMBER, BAR_BLUE_DONE
    base = subset[0].get('depth') or 0 if subset else 0
    headers = [f'{h} · approx' if approx and h in _BL_HEADERS else h for h in _HEADERS]
    rows = [_row(n, base) for n in subset]
    if buckets:
        headers = headers + gantt_header(buckets, unit, cutoff)
        rows = [r + gantt_cells(n.get('start'), n.get('finish'), buckets, BAR_BLUE if n.get('leaf') else BAR_AMBER,
                                n.get('actual') if _has_pct(n) else 0, BAR_BLUE_DONE)
                for r, n in zip(rows, subset)]
    return {'title': title, 'note': _branch_note(subset), 'headers': headers, 'rows': rows}


def wbs_excel(report):
    """(report dict the client holds) → `sheets` list for write_sections_xlsx.

    One sheet 'WBS' stacks the indented WBS table — one titled block per selectable
    main branch (as the segmented control offers them), or the whole tree as a single
    block when there are no distinct mains. Empty/missing data → a 'No data' sheet.
    """
    report = report or {}
    nodes = report.get('wbs_summary') or []
    mains = report.get('wbs_main') or []
    approx = bool(report.get('baseline_approx'))

    if not nodes:
        return [{'name': 'WBS',
                 'blocks': [{'title': 'WBS Summary', 'headers': _HEADERS,
                             'rows': [['No data', '—', '—', '—', '—', '—', '—', '—']]}],
                 'col_widths': _COL_WIDTHS}]

    cutoff = report.get('data_date')
    cut = _fmt_date(cutoff) if cutoff else ''
    widths = dict(_COL_WIDTHS)
    # the WBS made of milestones: reported by their milestone chart only, and not listed in the overview
    ms_wbs = set((((report.get('uncosted') or {}).get('summary') or {}).get('excluded_wbs')) or [])
    blocks, ov_rows = [], []
    # One block per main branch (the segmented control's tabs). Emit only mains that
    # actually resolve to a slice; fall back to the whole tree if none do.
    for m in mains:
        sub = _subset(nodes, m.get('id'))
        if not sub:
            continue
        ms_only = m.get('name') in ms_wbs
        # every WBS has its OWN month scale, opening on its first month (as the report prints it)
        buckets, unit = _month_buckets([n.get(k) for n in sub for k in ('start', 'finish', 'baseline_start', 'baseline_finish')] + [cutoff])
        for i in range(len(buckets)):
            widths[len(_HEADERS) + i] = 8
        blocks.extend(_cost_blocks(nodes, m, cut))
        blocks.extend(_uncosted_blocks(report.get('uncosted'), m.get('name'), cut))
        blocks.extend(_milestone_blocks(report.get('milestones'), m, cutoff, cut))
        if not ms_only:
            blocks.append(_block(f"WBS Summary — {m.get('name') or '(WBS)'}", sub, approx, buckets, unit, cutoff))
            root = sub[0]
            by_cost = _has_pct(root)
            ov_rows.append([m.get('name') or '(WBS)', root.get('count') or root.get('activities') or '—',
                            _pct_text(root.get('planned') if by_cost else root.get('planned_count_pct')),
                            _pct_text(root.get('actual') if by_cost else root.get('actual_count_pct')),
                            'by cost' if by_cost else 'by count of activities'])
    if ov_rows:
        ct = f' till {cut}' if cut else ''
        blocks.insert(0, {'title': 'WBS overview',
                          'note': (f'Cut-off date (data date): {cut or "—"}. A beside a date = Actual date. Planned % / Actual % of a WBS '
                                   'with no cost are counted by number of activities (see its Execution dashboard).'),
                          'headers': ['Main WBS', 'Activities', f'Planned %{ct}' + (' · approx' if approx else ''), f'Actual %{ct}', 'Basis'],
                          'rows': ov_rows})
    if not blocks:
        # No distinct mains (single flat branch) → the full pre-order tree, one block.
        buckets, unit = _month_buckets([n.get(k) for n in nodes for k in ('start', 'finish', 'baseline_start', 'baseline_finish')] + [cutoff])
        for i in range(len(buckets)):
            widths[len(_HEADERS) + i] = 8
        blocks.append(_block('WBS Summary', nodes, approx, buckets, unit, cutoff))

    pname = str(report.get('project_name') or '').strip()     # the name on the report (the planner's own, else P6's)
    if pname and blocks:
        blocks[0] = dict(blocks[0], note=('Project: %s · %s' % (pname, blocks[0].get('note') or '')).rstrip(' ·'))
    return [{'name': 'WBS', 'blocks': blocks, 'col_widths': widths}]


def _pct_text(v):
    return f'{v:.1f}%' if isinstance(v, (int, float)) else '—'


def _month_buckets(dates):
    """One time column per MONTH, from the first month of the given ISO dates to the last - every
    month is there and named, as the report's month scale writes them."""
    ds = [d for d in (_parse_date(x) for x in dates) if d]
    if not ds:
        return [], 'month'
    lo, hi = min(ds), max(ds)
    out, cur = [], date(lo.year, lo.month, 1)
    while cur <= hi and len(out) < 240:
        out.append(cur)
        cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
    return out, 'month'


_MS_HEADERS = ['Act. ID', 'Milestone', 'Status', 'Variance', 'Planned (baseline) date', 'Expected / Actual date']


def _milestone_blocks(milestones, m, cutoff, cut=''):
    """MILESTONE PROGRESS of one main WBS, as its chart in the report: a row per milestone with its
    status, variance, planned (baseline) and expected / actual dates, and the months between the two
    dates filled in the month columns (red = slipped, blue = early / on time, dark blue = completed)."""
    from p6_evm.xlsx_writer import gantt_header, gantt_cells, BAR_BLUE, BAR_RED, BAR_BLUE_DONE
    acts = [a for a in (milestones or [])
            if str(a.get('wbs_top_id')) == str(m.get('id')) or a.get('wbs_top') == m.get('name')]
    if not acts:
        return []
    dd = _parse_date(cutoff)
    data = []
    for a in acts:
        bl = _parse_date(a.get('baseline_finish') or a.get('planned_finish'))
        done = bool(a.get('finish_actual'))
        ex = _parse_date(a.get('finish') or a.get('planned_finish'))   # expected = current P6 Finish
        diff = (ex - bl).days if bl and ex else None
        data.append((a, bl, ex, done, diff))
    n_done = sum(1 for x in data if x[3])
    due = sum(1 for x in data if dd and x[1] and x[1] <= dd)
    buckets, unit = _month_buckets([d for x in data for d in (x[1], x[2])] + [dd])
    rows = []
    for a, bl, ex, done, diff in data:
        status = 'Completed' if done else ('Not Completed' if (dd and bl and bl <= dd) else 'Not Yet Due')
        var = '—' if diff is None else ('On time' if abs(diff) <= 1 else f'{diff:+d}d')
        lo, hi = (min(bl, ex), max(bl, ex)) if bl and ex else (bl or ex, bl or ex)
        style = BAR_BLUE_DONE if done else (BAR_RED if (diff or 0) > 1 else BAR_BLUE)
        rows.append([a.get('id') or '', a.get('name') or '', status, var,
                     bl.strftime('%d-%b.%Y') if bl else '—',
                     (ex.strftime('%d-%b.%Y') + (' A' if done else '')) if ex else '—']
                    + gantt_cells(lo, hi, buckets, style))
    return [{'title': f"Milestone Progress - {m.get('name')}",
             'note': (f'{len(data)} milestones · {n_done} completed · {due} planned till {cut or "the cut-off date"} · '
                      f'{max(0, due - n_done)} behind plan (planned but not completed). Planned = baseline finish date; Expected / Actual = '
                      'current finish in P6; Variance = days slipped (+) or early (-); A beside a date = Actual date.'),
             'headers': _MS_HEADERS + gantt_header(buckets, unit, cutoff), 'rows': rows}]


def _uc_groups(t):
    tot = t.get('total') or {}
    return [g for g in (('Submittals', 'st', 'sdue', 'sd'), ('Approvals', 'at', 'adue', 'ad'), ('Other activities', 'ot', 'odue', 'os')) if tot.get(g[1])]


def _uc_head(t, cut=''):
    ct = f' ({cut})' if cut else ''
    cols = [t.get('first') or 'Stage']
    for g in _uc_groups(t):
        cols += [f'{g[0]} - Total', f'{g[0]} - Planned till cut-off date{ct}', f'{g[0]} - Actual till cut-off date{ct}']
    return cols + [f'Planned %{" till " + cut if cut else ""}', f'Actual %{" till " + cut if cut else ""}', 'Status']


def _uc_row(r, t):
    row = [r['label']]
    for g in _uc_groups(t):
        row += [r.get(g[1]) or '—', (r.get(g[2]) if r.get(g[1]) else '—'), (r.get(g[3]) if r.get(g[1]) else '—')]
    row += [f"{r['planned_pct']:.1f}%" if r.get('planned_pct') is not None else '—',
            f"{r['actual_pct']:.1f}%" if r.get('actual_pct') is not None else '—',
            f"{r['behind']} behind" if r['behind'] else 'On plan']
    return row


def _cost_blocks(nodes, m, cut=''):
    """The EXECUTION DASHBOARD of a main WBS that is (almost) all cost loaded (95%+): its Planned % / Actual %
    are the cost-loaded %, budget weighted - not counted by number of activities."""
    i0 = next((i for i, n in enumerate(nodes) if str(n.get('id')) == str(m.get('id'))), -1)
    if i0 < 0:
        return []
    root = nodes[i0]
    all_n = root.get('count') or root.get('activities') or 0
    if not all_n or (root.get('cost_loaded') or 0) / all_n < 0.95:
        return []
    ct = f' till {cut}' if cut else ''
    pc = lambda v: f'{v:.1f}%' if isinstance(v, (int, float)) else '—'
    rows = [[root.get('name'), all_n, root.get('cost_loaded'), pc(root.get('planned')), pc(root.get('actual'))]]
    for j in range(i0 + 1, len(nodes)):
        if (nodes[j].get('depth') or 0) <= (root.get('depth') or 0):
            break
        if nodes[j].get('depth') == (root.get('depth') or 0) + 1:
            k = nodes[j]
            rows.append(['    ' + str(k.get('name')), k.get('count') or k.get('activities'), k.get('cost_loaded'),
                         pc(k.get('planned')) if k.get('cost_loaded') else '—', pc(k.get('actual')) if k.get('cost_loaded') else '—'])
    return [{'title': f"Execution dashboard - {m.get('name')} Progress Planned VS Actual",
             'note': ('COST-LOADED PROGRESS - weighted by the budget of each activity (P6 cost): Planned % = Planned value / budget of the cost-loaded activities; '
                      'Actual % = Earned value / budget. This WBS has ' + f"{100.0 * (root.get('cost_loaded') or 0) / all_n:.1f}" + '% of its activities cost loaded, so it is not counted by number of activities.'),
             'headers': ['WBS', 'Activities', 'Cost loaded', f'Planned %{ct}', f'Actual %{ct}'], 'rows': rows}]


def _uncosted_blocks(u, branch, cut=''):
    """The EXECUTION DASHBOARD of ONE main WBS (E1-log style: a row per stage, Submittals / Approvals /
    other activities counted apart, a Total row at the end) - in front of that WBS's table."""
    tabs = [t for t in ((u or {}).get('tables') or []) if not branch or branch in (t.get('branches') or [])]
    return [{'title': f"Execution dashboard - {branch} Progress Planned VS Actual - {t['title']}",
             'note': 'COUNT-BASED PROGRESS - every activity counts as one (no cost weighting). Planned till cut-off date = activities whose baseline finish is on or before the cut-off date; Actual till cut-off date = number of activities till the cut-off date that are in progress or completed (E1 rule); milestone activities excluded',
             'headers': _uc_head(t, cut),
             'rows': [_uc_row(r, t) for r in t['rows']] + [_uc_row(t['total'], t)]} for t in tabs]


# WBS name column wide (it carries the indentation); dates/percent/delay comfortable.
_COL_WIDTHS = {0: 46, 1: 15, 2: 15, 3: 15, 4: 15, 5: 30, 6: 30, 7: 12}
