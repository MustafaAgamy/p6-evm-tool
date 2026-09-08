"""Excel export for the Baseline Revision Comparison (Rev.00 vs Rev.01).

Turns the report dict the client already holds (from ``compare.build_report`` /
``/api/revcompare``) into the ``sheets`` structure consumed by the shared
``p6_evm.xlsx_writer.write_sections_xlsx`` — one worksheet per major report area,
each a stack of titled tables that MIRROR the on-screen tabs and the PDF sections
(``REVCOMPARE_SECTIONS`` in ``ui/modules/revcompare.js`` /
``p6_revcompare/exporters.py`` ``render_html``):

    Executive Summary · Revision Overview · Milestones · Critical Path & Sequence ·
    Logic Changes · Scope & Structure · Resource & Cost · Change Register ·
    Detailed Analysis

Nothing here computes a number — it only presents what ``build_report`` produced.
Every table degrades to a single "No data" row when its source is empty, so the
export never crashes on a sparse or partial report.
"""

# severity code (as stored on register rows / findings) -> on-screen badge label
_SEV_LABEL = {'crit': 'Critical', 'hi': 'High', 'med': 'Review', 'low': 'Info'}
_KIND_LABEL = {'delayed': 'Delayed', 'advanced': 'Advanced', 'unchanged': 'Unchanged',
               'new': 'New', 'removed': 'Removed'}
_CON_KIND = {'added': 'Added', 'removed': 'Removed', 'type': 'Type changed', 'date': 'Date changed'}
_ASG_KIND = {'added': 'Added', 'removed': 'Removed', 'units': 'Units changed', 'rate': 'Rate changed'}


def _sev(code):
    return _SEV_LABEL.get(code, code or '')


def _num(v, dash='—'):
    """Keep genuine numbers numeric (so Excel treats them as numbers); everything
    missing becomes an em dash placeholder."""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return v
    return dash if v is None else v


def _txt(v, dash=''):
    return dash if v is None else str(v)


def _sgn(n, unit=''):
    """Signed count like the KPI tiles: +3, -2, 0 (with an optional trailing unit)."""
    if n is None:
        return '—'
    return f"{'+' if n > 0 else ''}{n}{unit}"


def _rows_or_none(rows, ncols, msg='No data'):
    """Never emit an empty table — a single placeholder row keeps the sheet valid and
    tells the reader the dimension was genuinely empty (not dropped)."""
    if rows:
        return rows
    return [[msg] + [''] * (ncols - 1)]


# ── sections ───────────────────────────────────────────────────────────────────

def _summary_blocks(report):
    s = report.get('summary') or {}
    r1 = report.get('rev1') or {}
    kpis = [
        ['Activities', f"{s.get('activities0', 0)}→{s.get('activities1', 0)}", f"{_sgn(s.get('net'))} net"],
        ['New', _num(s.get('added')), 'added in Rev.01'],
        ['Removed', _num(s.get('removed')), 'not in Rev.01'],
        ['Modified', _num(s.get('modified')), f"+{s.get('id_changes', 0)} ID changes"],
        ['Project duration', _sgn(s.get('duration_change_wd'), ' wd'), 'critical-path length'],
        ['Finish date', _txt(r1.get('finish'), '—'), _sgn(s.get('finish_shift_days'), ' days')],
    ]
    profile = [[_txt(p.get('label')), _num(p.get('count'))] for p in (report.get('profile') or [])]
    ledger = [[_txt(l.get('label')), _num(l.get('rev0')), _num(l.get('rev1')), _num(l.get('delta'))]
              for l in (report.get('ledger') or [])]
    findings = [[_txt(f.get('title')), _txt(f.get('type_label')), _sev(f.get('severity')),
                 _txt(f.get('body'))] for f in (report.get('findings') or [])]
    narrative = report.get('narrative') or ''
    blocks = [
        {'title': 'Summary', 'headers': ['Metric', 'Value', 'Detail'], 'rows': kpis},
        {'title': 'Change profile — by category', 'headers': ['Category', 'Count'],
         'rows': _rows_or_none(profile, 2)},
        {'title': 'Comparison ledger — Rev.00 → Rev.01',
         'headers': ['Item', 'Rev.00', 'Rev.01', 'Change'], 'rows': _rows_or_none(ledger, 4)},
    ]
    if narrative:
        blocks.append({'title': 'Assessment', 'headers': ['Narrative'], 'rows': [[narrative]]})
    blocks.append({'title': 'Key findings — material changes',
                   'note': 'Each is an observation for planning review, not a verdict.',
                   'headers': ['Finding', 'Type', 'Severity', 'Detail'],
                   'rows': _rows_or_none(findings, 4, 'No material changes detected between the two revisions.')})
    return blocks


def _overview_blocks(report):
    r0, r1 = report.get('rev0') or {}, report.get('rev1') or {}

    def row(lbl, k):
        return [lbl, _txt(r0.get(k), '—'), _txt(r1.get(k), '—')]
    rows = [row('File', 'file'), row('Activities', 'activities'),
            row('Data date', 'data_date'), row('Governing finish', 'finish')]
    blocks = [{'title': 'Revision Overview', 'headers': ['', 'Rev.00 · Original', 'Rev.01 · Revised'],
               'rows': rows}]
    warnings = report.get('warnings') or []
    if warnings:
        blocks.append({'title': 'Warnings', 'headers': ['Note'], 'rows': [[w] for w in warnings]})
    return blocks


def _milestone_blocks(report):
    rows = []
    for m in report.get('milestones') or []:
        cd = m.get('change_days')
        change = (f"{'+' if (cd or 0) > 0 else ''}{cd} d") if cd is not None else _KIND_LABEL.get(m.get('kind'), '')
        rows.append([_txt(m.get('name')), _txt(m.get('rev0'), '—'), _txt(m.get('rev1'), '—'),
                     change, _KIND_LABEL.get(m.get('kind'), _txt(m.get('kind')))])
    return [{'title': 'Milestone Comparison',
             'headers': ['Milestone', 'Rev.00', 'Rev.01', 'Change', 'Impact'],
             'rows': _rows_or_none(rows, 5, 'No finish milestones found in the revisions.')}]


def _critpath_blocks(report):
    cp = report.get('critical_path') or {}
    lc = cp.get('length_change_wd')
    note = ''
    if lc is not None:
        note = (f"Rev.01 critical path is {'+' if lc >= 0 else ''}{lc} working days "
                f"{'longer' if lc >= 0 else 'shorter'}.")

    def chain_rows(nodes):
        out = []
        for i, n in enumerate(nodes or [], 1):
            tf = n.get('tf')
            state = {'enter': 'Entered critical path', 'leave': 'Left critical path'}.get(n.get('state'), '')
            out.append([i, _txt(n.get('name')), _num(round(tf, 1) if isinstance(tf, (int, float)) else tf), state])
        return out

    membership = []
    for e in cp.get('entered') or []:
        membership.append(['Entered critical path', _txt(e.get('name'))])
    for e in cp.get('left') or []:
        membership.append(['Left critical path', _txt(e.get('name'))])

    floats = [[f"{_txt(f.get('activity_id'))} {_txt(f.get('name'))}".strip(),
               _num(f.get('rev0_tf')), _num(f.get('rev1_tf')), _num(f.get('delta')), _txt(f.get('movement'))]
              for f in (report.get('float_movement') or [])]

    seq = []
    for sq in report.get('sequence') or []:
        seq.append([_txt(sq.get('a_name')), _txt(sq.get('b_name')),
                    _txt(sq.get('rev0')), _txt(sq.get('rev1')),
                    ' → '.join(_txt(x) for x in (sq.get('chain0') or [])),
                    ' → '.join(_txt(x) for x in (sq.get('chain1') or []))])

    ch0, ch1 = chain_rows(cp.get('rev0')), chain_rows(cp.get('rev1'))
    return [
        {'title': 'Critical Path — Rev.00 driving chain', 'note': note or None,
         'headers': ['#', 'Activity', 'Total float', 'State'], 'rows': _rows_or_none(ch0, 4,
         'No driving path available for Rev.00.')},
        {'title': 'Critical Path — Rev.01 driving chain',
         'headers': ['#', 'Activity', 'Total float', 'State'], 'rows': _rows_or_none(ch1, 4,
         'No driving path available for Rev.01.')},
        {'title': 'Critical path membership change', 'headers': ['Change', 'Activity'],
         'rows': _rows_or_none(membership, 2, 'No activities entered or left the critical path.')},
        {'title': 'Float / criticality movement', 'note': 'Total float, working days.',
         'headers': ['Activity', 'Rev.00 TF', 'Rev.01 TF', 'Δ', 'Movement'],
         'rows': _rows_or_none(floats, 5, 'No material float movement.')},
        {'title': 'Major sequence changes',
         'headers': ['Activity', 'Re-sequenced relative to', 'Was', 'Now', 'Rev.00 order', 'Rev.01 order'],
         'rows': _rows_or_none(seq, 6, 'No execution-order reversals detected from the logic.')},
    ]


def _logic_blocks(report):
    rows = []
    for row in report.get('register') or []:
        if row.get('change_type') != 'logic':
            continue
        rows.append([_txt(row.get('orig_id') or row.get('activity_id')), _txt(row.get('activity_name')),
                     _txt(row.get('rev0')), _txt(row.get('rev1')), _txt(row.get('change')),
                     _sev(row.get('severity'))])
    return [{'title': 'Major Relationship / Logic Changes',
             'headers': ['Activity', 'Name', 'Rev.00', 'Rev.01', 'Change', 'Severity'],
             'rows': _rows_or_none(rows, 6, 'No relationship/logic changes on matched activities.')}]


def _scope_blocks(report):
    s = report.get('summary') or {}
    lg = s.get('logic') or {}
    items = [
        ['New activities', _num(s.get('added'))],
        ['Removed activities', _num(s.get('removed'))],
        ['Identity (ID) changes', _num(s.get('id_changes'))],
        ['Moved between WBS', _num(s.get('moved_wbs'))],
        ['WBS branches +/−/renamed',
         f"{s.get('wbs_added', 0)} / {s.get('wbs_removed', 0)} / {s.get('wbs_renamed', 0)}"],
        ['Relationships added / removed', f"{lg.get('added', 0)} / {lg.get('removed', 0)}"],
        ['Calendar reassignments', _num(s.get('calendar_reassigned'))],
        ['Constraint changes', _num(s.get('constraint_changes'))],
    ]
    w = report.get('wbs_changes') or {}
    wbs = ([['Added', '—', _txt(x.get('path'))] for x in (w.get('added') or [])]
           + [['Removed', _txt(x.get('path')), '—'] for x in (w.get('removed') or [])]
           + [['Renamed', _txt(x.get('from')), _txt(x.get('to'))] for x in (w.get('renamed') or [])])

    cc = report.get('calendar_changes') or {}
    reassign = [[_txt(g.get('from')), _txt(g.get('to')),
                 (f"{g.get('from_wd')}-day → {g.get('to_wd')}-day"
                  if g.get('from_wd') is not None and g.get('to_wd') is not None else '—'),
                 _num(g.get('count'))] for g in (cc.get('reassignments') or [])]
    callevel = [[_txt(c.get('change')), _txt(c.get('name')), _txt(c.get('detail'))]
                for c in (cc.get('calendars') or [])]

    con = [[_txt(c.get('activity_id')), _txt(c.get('name')),
            _CON_KIND.get(c.get('kind'), _txt(c.get('kind'))) + (' · hard' if c.get('hard') else ''),
            _txt(c.get('rev0')), _txt(c.get('rev1'))] for c in (report.get('constraint_changes') or [])]

    return [
        {'title': 'Scope & structure summary', 'headers': ['Item', 'Value'], 'rows': items},
        {'title': 'WBS / scope structure', 'headers': ['Change', 'Rev.00', 'Rev.01'],
         'rows': _rows_or_none(wbs, 3, 'No WBS branches added, removed or renamed.')},
        {'title': 'Calendar reassignments', 'headers': ['From', 'To', 'Workweek', 'Activities'],
         'rows': _rows_or_none(reassign, 4, 'No calendar assignment changes.')},
        {'title': 'Calendar-level changes', 'headers': ['Change', 'Calendar', 'Detail'],
         'rows': _rows_or_none(callevel, 3, 'No calendar-level changes.')},
        {'title': 'Constraint changes', 'headers': ['Activity', 'Name', 'Change', 'Rev.00', 'Rev.01'],
         'rows': _rows_or_none(con, 5, 'No primary-constraint changes.')},
    ]


def _resource_blocks(report):
    rc = report.get('resource_changes') or {}
    if not (rc.get('cost_available') or rc.get('resource_available')):
        return [{'title': 'Resource & Cost Comparison',
                 'note': 'Neither revision carries resource loading or cost — reported as not applicable.',
                 'headers': ['Resource & cost'], 'rows': [['Not applicable']]}]
    tb = rc.get('total_budget') or {}
    bd = tb.get('delta', 0) or 0
    note = (f"Total budget {tb.get('rev0', 0):,} → {tb.get('rev1', 0):,} "
            f"({'+' if bd > 0 else ''}{bd:,}). Informational — a cost/resource change is not a schedule impact.")
    cost = [[_txt(c.get('code')), _txt(c.get('name')), _num(c.get('rev0')), _num(c.get('rev1')),
             _num(c.get('delta'))] for c in (rc.get('activity_cost_changes') or [])]
    asg = [[_txt(a.get('code')), _txt(a.get('resource')),
            _ASG_KIND.get(a.get('kind'), _txt(a.get('kind'))), _txt(a.get('rev0')), _txt(a.get('rev1'))]
           for a in (rc.get('assignment_changes') or [])]
    return [
        {'title': 'Resource & Cost Comparison', 'note': note,
         'headers': ['Budget'], 'rows': [[f"Rev.00 {tb.get('rev0', 0):,} · Rev.01 {tb.get('rev1', 0):,}"]]},
        {'title': 'Budget cost by activity', 'headers': ['Activity', 'Name', 'Rev.00', 'Rev.01', 'Δ'],
         'rows': _rows_or_none(cost, 5, 'No per-activity budget changes.')},
        {'title': 'Resource assignments', 'headers': ['Activity', 'Resource', 'Change', 'Rev.00', 'Rev.01'],
         'rows': _rows_or_none(asg, 5, 'No resource-assignment changes.')},
    ]


def _register_blocks(report):
    rows = []
    for row in report.get('register') or []:
        idt = (row.get('orig_id') or row.get('activity_id') or '')
        idt = idt.replace('MS:', '').replace('SCOPE:', '')
        rows.append([idt, _txt(row.get('activity_name')), _txt(row.get('type_label')),
                     _txt(row.get('rev0'), '—'), _txt(row.get('rev1'), '—'), _txt(row.get('change')),
                     'Material' if row.get('impact') == 'material' else 'Minor',
                     _sev(row.get('severity')), _txt(row.get('status'))])
    return [{'title': 'Detailed Change Register',
             'note': 'Ranked by impact then severity. Severity reflects schedule impact, not a judgement.',
             'headers': ['Activity', 'Name', 'Type', 'Rev.00', 'Rev.01', 'Change', 'Impact', 'Severity', 'Status'],
             'rows': _rows_or_none(rows, 9, 'No material changes detected between the two revisions.')}]


def _detailed_blocks(report):
    blocks = []
    _fields = [('Activity ID', 'id'), ('Name', 'name'), ('WBS', 'wbs'), ('Start', 'start'),
               ('Finish', 'finish'), ('Duration', 'duration'), ('Total float', 'total_float'),
               ('Criticality', 'criticality')]
    for row in report.get('register') or []:
        d = row.get('detail')
        if not d:
            continue
        r0, r1 = d.get('rev0') or {}, d.get('rev1') or {}
        table = [[lbl, _txt(r0.get(k), '—'), _txt(r1.get(k), '—')] for lbl, k in _fields]
        table += [
            ['Change detected', _txt(d.get('detected')), ''],
            ['Why it matters', _txt(d.get('why')), ''],
            ['Potential impact', _txt(d.get('impact')), ''],
            ['Planning review', _txt(d.get('review')), ''],
        ]
        title = f"{_txt(row.get('activity_name'))} — {_txt(row.get('change'))}".strip(' —')
        blocks.append({'title': title or 'Change',
                       'headers': ['Field / Analysis', 'Rev.00 · Original', 'Rev.01 · Revised'],
                       'rows': table, 'col_widths': {0: 20, 1: 46, 2: 46}})
    if not blocks:
        blocks.append({'title': 'Detailed Change Analysis', 'headers': ['Analysis'],
                       'rows': [['No detailed change analysis for this comparison.']]})
    return blocks


# ── assembly ────────────────────────────────────────────────────────────────────

def revcompare_excel(report):
    """Return the ``sheets`` list for ``write_sections_xlsx`` — one worksheet per major
    report area, mirroring the on-screen tabs and the PDF's gated sections."""
    report = report or {}
    _wide = {0: 26, 1: 26, 2: 22, 3: 18, 4: 18, 5: 16, 6: 12, 7: 12, 8: 10}
    return [
        {'name': 'Executive Summary', 'blocks': _summary_blocks(report),
         'col_widths': {0: 30, 1: 20, 2: 46, 3: 14}},
        {'name': 'Revision Overview', 'blocks': _overview_blocks(report),
         'col_widths': {0: 20, 1: 34, 2: 34}},
        {'name': 'Milestones', 'blocks': _milestone_blocks(report),
         'col_widths': {0: 34, 1: 16, 2: 16, 3: 12, 4: 12}},
        {'name': 'Critical Path & Sequence', 'blocks': _critpath_blocks(report),
         'col_widths': {0: 30, 1: 26, 2: 14, 3: 22, 4: 30, 5: 30}},
        {'name': 'Logic Changes', 'blocks': _logic_blocks(report),
         'col_widths': {0: 18, 1: 30, 2: 24, 3: 24, 4: 24, 5: 12}},
        {'name': 'Scope & Structure', 'blocks': _scope_blocks(report),
         'col_widths': {0: 26, 1: 30, 2: 30, 3: 14, 4: 24}},
        {'name': 'Resource & Cost', 'blocks': _resource_blocks(report),
         'col_widths': {0: 20, 1: 30, 2: 16, 3: 16, 4: 14}},
        {'name': 'Change Register', 'blocks': _register_blocks(report), 'col_widths': _wide},
        {'name': 'Detailed Analysis', 'blocks': _detailed_blocks(report),
         'col_widths': {0: 20, 1: 46, 2: 46}},
    ]
