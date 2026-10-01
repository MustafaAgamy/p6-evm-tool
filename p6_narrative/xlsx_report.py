"""Excel export of the Baseline Narrative Report (owner comment 29 — "Excel must include ALL the
data of a feature, including features with many sub-features").

The Narrative's Excel used to be a short plain-English status summary and carried none of the
report's sections. This builds the workbook FROM THE REPORT ITSELF — the same document model the
screen, the PDF and Word are drawn from (``p6_narrative.report.build_report(...).to_dict()``):
one sheet per section, every table with all its rows, every chart as the numbers behind it.

``narrative_sheets(doc)`` → the ``sheets`` list for ``p6_evm.xlsx_writer.write_sections_xlsx``.
Nothing is computed here; a section with nothing to show says so (never a missing sheet).
"""

_EMPTY = 'No data in the schedule for this section.'


def _s(v):
    return '' if v is None else str(v)


def _block(title, headers, rows, note=None):
    rows = [list(r) for r in (rows or [])]
    if not rows:
        rows = [[_EMPTY] + [''] * (len(headers) - 1)]
    b = {'title': title, 'headers': list(headers), 'rows': rows}
    if note:
        b['note'] = note
    return b


def _text_block(title, paragraphs, note=None):
    paras = [p for p in (paragraphs or []) if p]
    return _block(title, ['Text'], [[p] for p in paras], note)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


# ── one builder per section kind ────────────────────────────────────────────────

def _overview(p, sec):
    out = [_text_block('Overview', p.get('paragraphs'))]
    bd = p.get('breakdown') or []
    rows = [[_s(x.get('world')), x.get('count')] for x in bd]
    if p.get('total') is not None:
        rows.append(['Total', p.get('total')])
    out.append(_block('Baseline composition — activities by major scope', ['Scope', 'Activities'], rows))
    return out


def _image(p, sec):
    return [_text_block('Project layout', [p.get('placeholder') or
                                           ('A project layout drawing is attached in the report.' if p.get('image') else _EMPTY)])]


def _keyvals(p, sec):
    return [_block('Project brief', ['Item', 'Value'], [[_s(r.get('k')), _s(r.get('v'))] for r in (p.get('rows') or [])])]


def _ms_table(p, sec):
    cols = p.get('columns') or ['Milestone', 'Date']
    return [_block(sec.get('title') or 'Milestones', cols, [[_s(c) for c in r] for r in (p.get('rows') or [])])]


def _value_bars(p, sec):
    unit = p.get('unit') or ''
    rows = [[_s(r.get('name')), _num(r.get('amount')), _num(r.get('pct'))] for r in (p.get('rows') or [])]
    if p.get('total') is not None:
        rows.append(['Total contract value', _num(p.get('total')), 100.0 if rows else ''])
    return [_block('Contract value by type of work', ['Type of work', 'Amount' + (f' ({unit})' if unit else ''), 'Share (%)'], rows)]


def _scope(p, sec):
    out = []
    if p.get('narrative'):
        out.append(_text_block('Scope of work', [p['narrative']]))
    out.append(_block('Share of contract value by discipline', ['Discipline', 'Cost', 'Share (%)'],
                      [[_s(d.get('name')), _num(d.get('cost')), _num(d.get('pct'))] for d in (p.get('disciplines') or [])]))
    flat = []

    def walk(nodes, depth, trail):
        for n in nodes or []:
            name = _s(n.get('name'))
            flat.append([depth + 1, ' > '.join(trail + [name]), name, _num(n.get('cost')), _num(n.get('pct')),
                         n.get('count') if n.get('count') is not None else '', _num(n.get('each')) if n.get('each') is not None else ''])
            walk(n.get('children'), depth + 1, trail + [name])
    walk(p.get('cascade'), 0, [])
    codes = ' › '.join(_s(c) for c in (p.get('codes') or []))
    out.append(_block('Detailed cost-weighted breakdown', ['Level', 'Path', 'Name', 'Cost', 'Share (%)', 'Count', 'Each'],
                      flat, note=('By activity code: ' + codes) if codes else None))
    return out


_DASH = [('Total calendar days', 'total_calendar_days'), ('Working days', 'total_working_days'),
         ('Non-working days', 'total_nonworking_days'), ('Holidays', 'total_holidays'),
         ('Average working days per month', 'avg_working_days_per_month'),
         ('Average working hours per day', 'avg_working_hours_per_day'), ('Normal working hours', 'normal_hours')]


def _calendars(p, sec):
    if p.get('view') != 'calendars':                      # a generic table section
        return [_block(sec.get('title') or 'Table', p.get('columns') or ['Value'],
                       [[_s(c) for c in r] for r in (p.get('rows') or [])])]
    head = p.get('header') or {}
    dash = p.get('dashboard') or {}
    out = [_block('Executive dashboard', ['Item', 'Value'],
                  [['Calendars assigned to activities', head.get('calendar_count')], ['Activities', head.get('activity_count')]]
                  + [[lab, dash.get(k)] for lab, k in _DASH if dash.get(k) is not None])]
    for c in (p.get('calendars') or []):
        rows = [[_s(m.get('label')), m.get('working_days'), m.get('nonworking_days')] for m in (c.get('monthly') or [])]
        rows.append(['Total working days', c.get('working_days'), ''])
        out.append(_block(f"Calendar timeline — {_s(c.get('name'))}", ['Month', 'Working days', 'Non-working days'], rows,
                          note=f"{c.get('activity_count', 0)} activities use this calendar"))
    out.append(_block('Holidays', ['Date', 'Description'],
                      [[_s(h.get('date')), _s(h.get('description'))] for h in (p.get('holidays') or [])]))
    out.append(_block('Working hours profile', ['Calendar', 'Hours', 'Week'],
                      [[_s(h.get('name')), _s(h.get('hours')), _s(h.get('sub'))] for h in (p.get('hours_profiles') or [])]))
    return out


def _wbs(p, sec):
    ov = p.get('overview') or {}
    out = [_block('WBS overview — the main branches', ['Project', 'Main WBS branch'],
                  [[_s(ov.get('name')), _s(c.get('name'))] for c in (ov.get('children') or [])])]
    rows = []
    for b in (p.get('branches') or []):
        cols = b.get('columns') or []
        if not cols:
            rows.append([_s(b.get('name')), '', '', ''])
        for col in cols:
            l2 = _s(col[0]) if col else ''
            l3s = (col[1] if len(col) > 1 else []) or []
            if not l3s:
                rows.append([_s(b.get('name')), l2, '', ''])
            for e in l3s:
                l3 = _s(e[0]) if e else ''
                l4s = (e[1] if len(e) > 1 else []) or []
                if not l4s:
                    rows.append([_s(b.get('name')), l2, l3, ''])
                for l4 in l4s:
                    rows.append([_s(b.get('name')), l2, l3, _s(l4)])
    out.append(_block('WBS breakdown by branch', ['Level 1', 'Level 2', 'Level 3', 'Level 4'], rows,
                      note='Each branch as the report draws it (to Level 4 where it has four or fewer Level-4 nodes, else Level 3).'))
    return out


def _codes(p, sec):
    out = []
    for t in (p.get('tables') or []):
        out.append(_block(f"Activity code — {_s(t.get('dimension'))}", ['Code value', 'Description'],
                          [[_s(r.get('code')), _s(r.get('description'))] for r in (t.get('rows') or [])]))
    return out or [_block('Activity codes', ['Code value', 'Description'], [])]


def _sequence(p, sec):
    out = []
    for i, a in enumerate(p.get('analyses') or [], 1):
        title = _s(a.get('title')) or f'Analysis {i}'
        if a.get('narrative'):
            out.append(_text_block(title, [a['narrative']]))
        if a.get('kind') == 'single':
            out.append(_block(title + ' — steps in order', ['Step', 'Name', 'Activities'],
                              [[n, _s(s.get('name')), s.get('count')] for n, s in enumerate(a.get('steps') or [], 1)]))
        else:
            rows = []
            for g in (a.get('groups') or []):
                for n, s in enumerate(g.get('steps') or [], 1):
                    rows.append([_s(g.get('label')), g.get('count') or 1, n, _s(s.get('name')), s.get('count')])
            out.append(_block(title + ' — steps in order, per group', ['Group', 'Identical groups', 'Step', 'Name', 'Activities'], rows))
            if a.get('no_code'):
                out.append(_block(title + ' — without this coding', ['Name'], [[_s(x)] for x in a['no_code']]))
    return out or [_block('Sequence of work', ['Step', 'Name', 'Activities'], [])]


def _activity_ids(p, sec):
    out = [_text_block('Activity IDs', [p.get('intro')])]
    an = p.get('anatomy') or {}
    if an.get('cols'):
        out.append(_block('ID anatomy', ['Segment', 'Meaning', 'Role'],
                          [[_s(c.get('code')), _s(c.get('meaning')), _s(c.get('role'))] for c in an['cols']],
                          note='Sample ID: ' + _s(an.get('sample'))))
    for b in (p.get('blocks') or []):
        note = ' · '.join(x for x in ('Sample ID: ' + _s(b.get('sample')) if b.get('sample') else '',
                                      _s(b.get('note')), f"{b.get('count')} activities" if b.get('count') is not None else '') if x)
        out.append(_block(_s(b.get('title')), ['Segment', 'Meaning', 'Role'],
                          [[_s(c.get('code')), _s(c.get('meaning')), _s(c.get('role'))] for c in (b.get('cols') or [])], note=note))
    return out


def _resload(p, sec):
    if not p.get('available'):
        return [_text_block('Resource loading', [p.get('intro') or p.get('note') or _EMPTY])]
    out = [_text_block('Resource loading', [p.get('intro')])]
    for g in (p.get('groups') or []):
        title = _s(g.get('title')) or 'Resources'
        rows = [[(_num(c) if i else _s(c)) for i, c in enumerate(r)] for r in (g.get('rows') or [])]
        if g.get('total_label'):
            rows.append(['Total', f"{g.get('total_label')} {_s(g.get('total_unit'))}".strip()])
        out.append(_block(f'{title} — totals by resource', g.get('row_headers') or ['Resource', 'Total'], rows,
                          note=' · '.join(x for x in (_s(g.get('basis_note')), _s(g.get('window'))) if x)))
        for c in (g.get('charts') or []):
            span, vals = c.get('span') or [], c.get('values') or []
            out.append(_block(f"{title} — {_s(c.get('chart_title')) or 'monthly loading'}", ['Month', 'Value'],
                              [[_s(m), _num(v)] for m, v in zip(span, vals)],
                              note=('Peak ' + ' '.join(_s(x) for x in (c.get('peak_val'), c.get('peak_unit'), 'in', c.get('peak_label')) if x))
                              if c.get('peak_val') is not None else None))
    return out


def _materials(p, sec):
    if not p.get('available'):
        return [_text_block('Material resources', [p.get('intro') or p.get('note') or _EMPTY])]
    out = [_text_block('Material resources', [p.get('intro')]),
           _block('Material resources — totals', p.get('table_headers') or ['Material resource', 'Unit', 'Total'],
                  [[(_num(c) if i else _s(c)) for i, c in enumerate(r)] for r in (p.get('table_rows') or [])])]
    for c in (p.get('charts') or []):
        out.append(_block(f"{_s(c.get('name'))} — monthly quantity", ['Month', 'Quantity' + (f" ({c.get('unit')})" if c.get('unit') else '')],
                          [[_s(m), _num(v)] for m, v in zip(c.get('span') or [], c.get('values') or [])],
                          note=f"Total {_s(c.get('total'))} · peak {_s(c.get('peak_val'))} in {_s(c.get('peak_label'))}"))
    return out


def _prodrate(p, sec):
    if not p.get('available'):
        return [_text_block('Productivity rates', [p.get('intro') or p.get('note') or _EMPTY])]
    out = [_text_block('Productivity rates & resources assigned', [p.get('intro'), p.get('method_intro')]),
           _block('How each figure is derived', ['Term', 'Meaning'], [[_s(c) for c in r] for r in (p.get('method') or [])]),
           _block('Planned production rate by quantity of work', p.get('headers') or ['Quantities resource'],
                  [[_s(c) for c in r] for r in (p.get('rows') or [])], note=p.get('no_unit_note'))]
    for b in (p.get('breakdown') or []):
        out.append(_block(f"{_s(b.get('name'))} — activities and resources assigned", b.get('headers') or ['Activity ID'],
                          [[_s(c) for c in r] for r in (b.get('rows') or [])],
                          note=f"{_s(b.get('rate'))} · {b.get('total_wd')} working days · {b.get('nact')} activities"))
    return out


def _volwork(p, sec):
    if not p.get('available'):
        return [_text_block('Volume of work', [p.get('intro') or p.get('note') or _EMPTY])]
    ch = p.get('chart') or {}
    return [_text_block('Volume of work', [p.get('intro'), p.get('caption'), p.get('end_caption')]),
            _block('Summary', p.get('summary_headers') or ['Metric', 'Value'], [[_s(c) for c in r] for r in (p.get('summary_rows') or [])]),
            _block('Monthly and cumulative value of work', ['Month', 'Monthly value', 'Cumulative value'],
                   [[_s(m), _num(v), _num(c)] for m, v, c in zip(ch.get('labels') or [], ch.get('values') or [], ch.get('cum') or [])])]


def _critpath(p, sec):
    if not p.get('available'):
        return [_text_block('Critical path', [p.get('note') or _EMPTY])]
    months = p.get('months') or []
    heads = ['Zone'] + [f"{_s(m.get('label'))} {m.get('y')}" for m in months]
    rows = []
    for z in (p.get('zones') or []):
        cells = z.get('cells') or []
        row = [_s(z.get('label'))]
        for c in cells:
            if c is None:
                row.append('')
            elif isinstance(c, dict):
                row.append(_s(c.get('trade') or c.get('label') or c.get('t') or 'critical'))
            else:
                row.append(_s(c))
        rows.append(row + [''] * (len(heads) - len(row)))
    return [_text_block('Critical path', [p.get('narrative')]),
            _block('Key figures', ['Item', 'Value'], [[_s(k[1]), _s(k[0])] for k in (p.get('kpis') or [])]),
            _block(p.get('subhead') or 'Critical-path sweep — which zone drives the schedule, month by month', heads, rows,
                   note=p.get('note')),
            # the chart's colour key, as the list of trades it shows (a colour means nothing in a cell)
            _block('Trades on the critical path', ['Trade'], [[_s(l[0])] for l in (p.get('legend') or []) if l])]


def _mapsheet(p, sec):
    return [_text_block(sec.get('title') or 'Appendix', [p.get('placeholder') or _EMPTY])]


_BUILDERS = {'overview': _overview, 'image': _image, 'keyvals': _keyvals, 'ms_table': _ms_table,
             'value_bars': _value_bars, 'scope': _scope, 'table': _calendars, 'wbs_tree': _wbs, 'codes': _codes,
             'sequence': _sequence, 'activity_ids': _activity_ids, 'resload': _resload, 'materials': _materials,
             'prodrate': _prodrate, 'volwork': _volwork, 'critpath': _critpath, 'mapsheet': _mapsheet}


def narrative_sheets(doc):
    """Report document (dict) → sheets for write_sections_xlsx: one sheet per section, in the
    report's order, named '<number> <title>'. A section the builder does not know still gets a
    sheet (its note), so the workbook always lists every section of the report."""
    sheets = []
    for sec in (doc or {}).get('sections') or []:
        if not isinstance(sec, dict):
            continue
        p = sec.get('payload') or {}
        fn = _BUILDERS.get(sec.get('kind'))
        try:
            blocks = fn(p, sec) if fn else [_text_block(sec.get('title') or 'Section', [sec.get('note') or _EMPTY])]
        except Exception as exc:                              # one bad section never loses the workbook
            blocks = [_text_block(sec.get('title') or 'Section', ['This section could not be exported: ' + str(exc)[:160]])]
        blocks = [b for b in blocks if b]
        if blocks and sec.get('note') and not blocks[0].get('note'):
            blocks[0]['note'] = sec['note']
        name = f"{_s(sec.get('number')).zfill(2)} {_s(sec.get('title'))}".strip()
        sheets.append({'name': name, 'blocks': blocks})
    if not sheets:
        sheets = [{'name': 'Baseline Narrative', 'blocks': [_text_block('Baseline Narrative', ['Generate the narrative first.'])]}]
    return sheets
