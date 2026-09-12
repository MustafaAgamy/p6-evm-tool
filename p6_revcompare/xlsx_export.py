"""Excel export for the Baseline Revision Comparison (Rev.00 vs Rev.01) — redesign.

Turns the report dict the client already holds (from ``compare.build_report_from_data``
/ ``/api/revcompare``) into the ``sheets`` structure consumed by the shared
``p6_evm.xlsx_writer.write_sections_xlsx`` — one worksheet per canonical report section,
each a stack of titled tables that MIRROR the seven on-screen tabs, the PDF sections and
the report-contents picker (same section keys throughout — the redesigned full report,
``ui/modules/revcompare.js`` ``RC_TABS`` / ``p6_revcompare/exporters.py`` ``render_html``
/ the interactive concept ``mockups/baseline-revision-interactive-concept.html``):

    summary   → Executive Summary  (bottom line · revision snapshot · comparison ledger ·
                credibility / red flags · scope by activity code)
    findings  → Key Findings       (finish-slip driver bridge + its contribution breakdown ·
                the "Logic & Sequence Changes" — every changed relationship as rows carrying
                a column per activity-code dimension · key findings list)
    critical  → Critical Path & Float (Rev.00/Rev.01 driving chains · membership change ·
                total-float band shift · negative-float register)
    register  → Change Register     (DURATION changed only — separate ID / Name columns,
                Before → After → Variance, calendar & float context)
    mcc       → Milestones, Constraints & Calendars (the milestone · constraint · calendar
                tables moved out of the register)
    cost      → Cost & Resources    (planned-value S-curve tables · budget by dimension ·
                value after original finish · manpower histogram · man-hours by trade · plus
                the Cost changed and Resource changed tables moved out of the register)
    scope     → Scope & Structure   (WBS comparison Rev.00 / Rev.01 · largest date shifts)

The "Logic & Sequence Changes" rows REPLACE the old sequence roll-up and the standalone
Logic table — both are gone everywhere. Nothing here computes a number — it only presents
what ``build_report_from_data`` produced. Every table degrades to a single "No data" row
when its source is empty (via ``_rows_or_none``), so the export never crashes on a sparse
or partial report. Neutral throughout: change detected, not judged.
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
    missing becomes an em-dash placeholder."""
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


def _delta(a, b, unit=''):
    """Signed Rev.00 → Rev.01 delta from two numeric per-revision values."""
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return '—'
    return _sgn(b - a, unit)


def _onoff(b):
    return 'Yes' if b else 'No'


def _flag(b, yes='Yes'):
    return yes if b else ''


def _rows_or_none(rows, ncols, msg='No data'):
    """Never emit an empty table — a single placeholder row keeps the sheet valid and
    tells the reader the dimension was genuinely empty (not dropped)."""
    if rows:
        return rows
    return [[msg] + [''] * (ncols - 1)]


# ── 1 · summary — Executive Summary ──────────────────────────────────────────────

def _summary_blocks(report):
    r0, r1 = report.get('rev0') or {}, report.get('rev1') or {}
    s = report.get('summary') or {}
    q = report.get('quality') or {}
    codes = report.get('codes') or {}

    bottom = report.get('bottom_line') or ''
    blocks = [{'title': 'Bottom line', 'headers': ['Neutral one-line summary'],
               'rows': [[bottom]] if bottom else [['No summary available for this comparison.']]}]

    # Revision snapshot — Rev.00 · Original vs Rev.01 · Revised
    def snap(lbl, k, dash='—'):
        return [lbl, _txt(r0.get(k), dash), _txt(r1.get(k), dash)]
    snap_rows = [
        snap('File', 'file'),
        snap('Data date', 'data_date'),
        snap('Governing finish', 'finish'),
        ['Activities', _num(r0.get('activities')), _num(r1.get('activities'))],
        ['Finish slip', '', _sgn(s.get('finish_shift_days'), ' days')],
    ]
    blocks.append({'title': 'Revision snapshot — Rev.00 → Rev.01',
                   'note': 'Baselines only (no actuals) — a like-for-like comparison.',
                   'headers': ['', 'Rev.00 · Original', 'Rev.01 · Revised'], 'rows': snap_rows})

    # Comparison ledger
    ledger = [[_txt(l.get('label')), _num(l.get('rev0')), _num(l.get('rev1')), _num(l.get('delta'))]
              for l in (report.get('ledger') or [])]
    blocks.append({'title': 'Comparison ledger',
                   'headers': ['Measure', 'Rev.00', 'Rev.01', 'Change'],
                   'rows': _rows_or_none(ledger, 4)})

    # Credibility / red flags — from quality
    neg = q.get('negative_float') or {}
    oe = q.get('open_ends') or {}
    ld = q.get('leads') or {}
    tr = q.get('total_rels') or {}
    rpa = q.get('rels_per_act') or {}
    hc = q.get('hard_constraints') or {}
    nc = q.get('near_critical') or {}

    def qrow(lbl, d):
        d = d or {}
        return [lbl, _num(d.get('rev0')), _num(d.get('rev1')), _delta(d.get('rev0'), d.get('rev1'))]
    red = [
        qrow('Negative-float activities', neg),
        qrow('Open ends (dangling)', oe),
        qrow('Hard constraints', hc),
        qrow('Leads (negative lags)', ld),
        qrow('Near-critical activities', nc),
        qrow('Total relationships', tr),
        ['Relationships per activity', _num(rpa.get('rev0')), _num(rpa.get('rev1')),
         _delta(rpa.get('rev0'), rpa.get('rev1'))],
    ]
    blocks.append({'title': 'Schedule-quality signals',
                   'note': 'Signals for planning review, not defects.',
                   'headers': ['Signal', 'Rev.00', 'Rev.01', 'Δ'], 'rows': red})

    # Scope change — by activity code
    sbc = codes.get('scope_by_code') or {}
    for dim, rows in sbc.items():
        table = [[_txt(c.get('category')), _num(c.get('added')), _num(c.get('removed'))]
                 for c in (rows or [])]
        blocks.append({'title': f'Scope change — by {dim}',
                       'headers': ['Category', 'Added', 'Removed'],
                       'rows': _rows_or_none(table, 3, 'No scope changes for this dimension.')})
    if not sbc:
        blocks.append({'title': 'Scope change — by activity code',
                       'headers': ['Category', 'Added', 'Removed'],
                       'rows': [['No activity-code scope changes.', '', '']]})

    # Itemised added / removed
    itemised = ([[_txt(a.get('id')), _txt(a.get('name')), 'Added', _txt(a.get('building'), '—'),
                  _txt(a.get('wbs'), '—'), _txt(a.get('scope'), '—')] for a in (codes.get('added') or [])]
                + [[_txt(a.get('id')), _txt(a.get('name')), 'Removed', _txt(a.get('building'), '—'),
                    _txt(a.get('wbs'), '—'), _txt(a.get('scope'), '—')] for a in (codes.get('removed') or [])])
    blocks.append({'title': 'Scope changes — activities added / removed',
                   'headers': ['Activity ID', 'Activity Name', 'Change', 'Building', 'WBS (under)', 'Scope'],
                   'rows': _rows_or_none(itemised, 6, 'No activities added or removed.')})

    recoded = [[_txt(c.get('id')), _txt(c.get('name')), _txt(c.get('code_type')),
                _txt(c.get('before'), '—'), _txt(c.get('after'), '—')] for c in (codes.get('recoded') or [])]
    blocks.append({'title': 'Re-coded activities — code value changed',
                   'headers': ['Activity ID', 'Activity Name', 'Code type', 'Before', 'After'],
                   'rows': _rows_or_none(recoded, 5, 'No activity-code value changes on matched activities.')})
    return blocks


# ── 2 · findings — Key Findings ──────────────────────────────────────────────────

def _logic_dims(report):
    """Ordered activity-code dimensions to spread across columns for the logic changes —
    the report's own dimensions (``codes.dimensions``), the synthetic ``WBS`` branch, and
    any extra dimension keys that only appear on the logic rows themselves. Always at least
    one column so the code context is never dropped."""
    codes = report.get('codes') or {}
    out = []
    for d in (codes.get('dimensions') or []):
        if d and d not in out:
            out.append(d)
    if 'WBS' not in out:
        out.append('WBS')
    for r in (report.get('logic_register') or []):
        for k in (r.get('codes') or {}):
            if k not in out:
                out.append(k)
    return out or ['Activity code']


def _findings_blocks(report):
    slip = report.get('slip') or {}
    total = slip.get('total_wd')
    # Finish-slip contribution breakdown — one row per cause with its day count and meaning
    # (the on-screen colour swatch is visual only; the sheet carries cause · +N d · detail).
    contrib = [[_txt(c.get('cause')), _num(c.get('wd')), _txt(c.get('detail'))]
               for c in (slip.get('contributions') or [])]
    if contrib and total is not None:
        contrib.append(['Total finish slip', _num(total), f"{_txt(slip.get('rev0_finish'), '—')} → "
                        f"{_txt(slip.get('rev1_finish'), '—')}"])
    slip_title = f"What drove the {_sgn(total, ' working days')} — finish-slip bridge" if total is not None \
        else 'Finish-slip bridge'
    blocks = [{'title': slip_title,
               'note': 'Neutral attribution along the driving path — this attributes the slip, it does not judge it. '
                       'Each row is a cause, the working days it added, and what it means.',
               'headers': ['Cause', 'Working days', 'Detail'],
               'rows': _rows_or_none(contrib, 3, 'No finish slip to attribute.')}]

    # Logic & Sequence Changes — every changed relationship as a row, carrying a column per
    # activity-code dimension (so the grouping/filtering the chart offers is preserved on
    # paper). REPLACES the old sequence roll-up AND the standalone Logic table.
    dims = _logic_dims(report)
    lg_headers = list(dims) + ['Predecessor ID', 'Predecessor Name', 'Successor ID',
                               'Successor Name', 'Link Before', 'Link After', 'Change',
                               'On CP?', 'Lead?']
    lg = []
    for r in (report.get('logic_register') or []):
        rc = r.get('codes') or {}
        lg.append([_txt(rc.get(d), '—') for d in dims]
                  + [_txt(r.get('pred_id')), _txt(r.get('pred_name')), _txt(r.get('succ_id')),
                     _txt(r.get('succ_name')), _txt(r.get('before'), '—'), _txt(r.get('after'), '—'),
                     _txt(r.get('change')), _onoff(r.get('on_cp')), _flag(r.get('is_lead'), 'Lead')])
    blocks.append({'title': 'Logic & Sequence Changes — every changed relationship (by activity code)',
                   'note': 'Before → After per predecessor→successor link, grouped/filterable by activity code; '
                           '"On CP?" flags links touching the revised critical path, leads (negative lags) flagged. '
                           'Replaces the old sequence roll-up and logic table.',
                   'headers': lg_headers,
                   'rows': _rows_or_none(lg, len(lg_headers),
                                         'No relationship / logic changes on matched activities.')})

    # Key findings list
    finds = [[_txt(f.get('title')), _txt(f.get('type_label')), _sev(f.get('severity')),
              _txt(f.get('body'))] for f in (report.get('findings') or [])]
    blocks.append({'title': 'Key findings — material changes',
                   'note': 'Each is an observation for planning review, not a verdict.',
                   'headers': ['Finding', 'Type', 'Severity', 'Detail'],
                   'rows': _rows_or_none(finds, 4, 'No material changes detected between the two revisions.')})
    return blocks


# ── 3 · critical — Critical Path & Float ─────────────────────────────────────────

def _critical_blocks(report):
    cp = report.get('critical_path') or {}
    q = report.get('quality') or {}
    lc = cp.get('length_change_wd')
    note = None
    if lc is not None:
        note = (f"Rev.01 critical path is {_sgn(lc, ' working days')} "
                f"{'longer' if lc >= 0 else 'shorter'}.")

    _state = {'enter': 'Entered critical path', 'leave': 'Left critical path'}

    def chain_rows(nodes):
        out = []
        for i, n in enumerate(nodes or [], 1):
            tf = n.get('tf')
            nm = n.get('name')
            if n.get('is_ms'):
                nm = f"{nm} (milestone)"
            out.append([i, _txt(n.get('code')), _txt(nm),
                        _num(round(tf, 1) if isinstance(tf, (int, float)) else tf),
                        _state.get(n.get('state'), '')])
        return out

    membership = ([['Entered critical path', _txt(e.get('code')), _txt(e.get('name'))]
                   for e in (cp.get('entered') or [])]
                  + [['Left critical path', _txt(e.get('code')), _txt(e.get('name'))]
                     for e in (cp.get('left') or [])])

    bands = [[_txt(b.get('band')), _num(b.get('rev0')), _num(b.get('rev1')),
              _delta(b.get('rev0'), b.get('rev1'))] for b in (q.get('float_bands') or [])]

    neg = q.get('negative_float') or {}
    reg = [[_txt(a.get('id')), _txt(a.get('name')),
            _num(a.get('tf')), _txt(a.get('wbs'), '—')] for a in (neg.get('register') or [])]

    return [
        {'title': 'Critical path — Rev.00 driving chain', 'note': note,
         'headers': ['#', 'Activity ID', 'Activity Name', 'Total Float', 'State'],
         'rows': _rows_or_none(chain_rows(cp.get('rev0')), 5, 'No driving path available for Rev.00.')},
        {'title': 'Critical path — Rev.01 driving chain',
         'headers': ['#', 'Activity ID', 'Activity Name', 'Total Float', 'State'],
         'rows': _rows_or_none(chain_rows(cp.get('rev1')), 5, 'No driving path available for Rev.01.')},
        {'title': 'Critical-path membership change',
         'headers': ['Change', 'Activity ID', 'Activity Name'],
         'rows': _rows_or_none(membership, 3, 'No activities entered or left the critical path.')},
        {'title': 'Total-float band shift — Rev.00 vs Rev.01',
         'note': 'Activity counts per total-float band (working days).',
         'headers': ['Total-float band', 'Rev.00', 'Rev.01', 'Δ'],
         'rows': _rows_or_none(bands, 4, 'No float distribution available.')},
        {'title': 'Negative-float register — re-plan trigger',
         'note': 'Activities carrying total float below zero in Rev.01.',
         'headers': ['Activity ID', 'Activity Name', 'Total Float', 'WBS'],
         'rows': _rows_or_none(reg, 4, 'No activities carry negative float in Rev.01.')},
    ]


# ── 4 · register — Change Register (DURATION changed only) ───────────────────────

def _register_blocks(report):
    # Only the Duration changed table lives in the register now — milestone / constraint /
    # calendar moved to Milestones, Constraints & Calendars; logic to Key Findings; cost /
    # resource to Cost & Resources.
    dur = [[_txt(d.get('id')), _txt(d.get('name')), _txt(d.get('wbs'), '—'),
            _num(d.get('before')), _num(d.get('after')), _num(d.get('variance')),
            _txt(d.get('calendar_before'), '—'), _txt(d.get('calendar_after'), '—'),
            _num(d.get('tf_after')), _flag(d.get('calendar_flag'))]
           for d in (report.get('duration_table') or [])]
    return [{'title': 'Duration changed — working days (+ calendar & float context)',
             'note': 'A calendar-flagged row shortened on paper (workweek/hours change), not less work. '
                     'Filter by activity code on screen (Discipline / Building / WBS); every changed row is listed here.',
             'headers': ['Activity ID', 'Activity Name', 'WBS', 'Before', 'After', 'Variance',
                         'Calendar Before', 'Calendar After', 'TF After', 'Calendar flag'],
             'rows': _rows_or_none(dur, 10, 'No duration changes on matched activities.')}]


# ── 5 · mcc — Milestones, Constraints & Calendars ────────────────────────────────

def _mcc_blocks(report):
    """The date-driver tables moved out of the Change Register — rendered exactly as they
    were: milestone changes, primary-constraint changes, and calendar reassignments +
    definition changes."""
    blocks = []

    # Milestone changed
    ms = []
    for m in (report.get('milestones') or []):
        cd = m.get('change_days')
        kind = m.get('kind')
        if kind == 'unchanged':
            continue                       # "Milestone changed" lists only actual changes (matches PDF)
        if kind == 'new':
            change = 'Added'
        elif kind == 'removed':
            change = 'Removed'
        elif cd is not None:
            change = _sgn(cd, ' d')
        else:
            change = _KIND_LABEL.get(kind, _txt(kind))
        ms.append(['—', _txt(m.get('name')), _txt(m.get('rev0'), '—'), _txt(m.get('rev1'), '—'),
                   change, _KIND_LABEL.get(kind, _txt(kind))])
    blocks.append({'title': 'Milestone changed',
                   'headers': ['Activity ID', 'Milestone', 'Before', 'After', 'Change', 'Impact'],
                   'rows': _rows_or_none(ms, 6, 'No finish milestones found in the revisions.')})

    # Constraint changed
    con = [[_txt(c.get('activity_id')), _txt(c.get('name')),
            _txt(c.get('rev0'), '—'), _txt(c.get('rev1'), '—'),
            _CON_KIND.get(c.get('kind'), _txt(c.get('kind'))), _flag(c.get('hard'), 'Hard')]
           for c in (report.get('constraint_changes') or [])]
    blocks.append({'title': 'Constraint changed — a hidden lever on the finish date',
                   'note': 'A hard constraint on the driving path can pin or move the finish independently of logic.',
                   'headers': ['Activity ID', 'Activity Name', 'Constraint Before', 'Constraint After',
                               'Change', 'Hard?'],
                   'rows': _rows_or_none(con, 6, 'No primary-constraint changes.')})

    # Calendar changed — reassignments + definitions
    cc = report.get('calendar_changes') or {}
    reassign = [[_txt(g.get('from')), _txt(g.get('to')),
                 (f"{g.get('from_wd')}-day → {g.get('to_wd')}-day"
                  if g.get('from_wd') is not None and g.get('to_wd') is not None else '—'),
                 _num(g.get('count'))] for g in (cc.get('reassignments') or [])]
    blocks.append({'title': 'Calendar changed — activities reassigned (grouped)',
                   'note': 'A 5→6-day week or hours/day change shortens durations on paper without changing the work.',
                   'headers': ['From', 'To', 'Workweek', 'Activities'],
                   'rows': _rows_or_none(reassign, 4, 'No calendar assignment changes.')})
    caldef = [[_txt(c.get('name')), _txt(c.get('change')), _txt(c.get('detail'))]
              for c in (cc.get('calendars') or [])]
    blocks.append({'title': 'Calendar changed — definition changes',
                   'headers': ['Calendar', 'Change', 'Detail'],
                   'rows': _rows_or_none(caldef, 3, 'No calendar-level changes.')})
    return blocks


# ── 6 · cost — Cost & Resources ──────────────────────────────────────────────────

def _cost_moved_blocks(report):
    """The Cost changed + Resource changed tables moved in from the Change Register."""
    rc = report.get('resource_changes') or {}

    # Cost changed — per-activity budget + total
    cost = []
    for c in (rc.get('activity_cost_changes') or []):
        cost.append([_txt(c.get('code')), _txt(c.get('name')), _txt(c.get('rev0'), '—'),
                     _txt(c.get('rev1'), '—'), _num(c.get('delta'))])
    tb = rc.get('total_budget') or {}
    if rc.get('cost_available'):
        cost.append(['—', 'Total budget', _num(tb.get('rev0')), _num(tb.get('rev1')),
                     _num(tb.get('delta'))])

    # Resource changed — assignments
    asg = [[_txt(a.get('code')), _txt(a.get('name')), _txt(a.get('resource')),
            _ASG_KIND.get(a.get('kind'), _txt(a.get('kind'))), _txt(a.get('rev0'), '—'),
            _txt(a.get('rev1'), '—')] for a in (rc.get('assignment_changes') or [])]

    return [
        {'title': 'Cost changed — budget total cost (moved from the Change Register)',
         'note': 'Informational — a cost change is not itself a schedule impact.',
         'headers': ['Activity ID', 'Activity Name', 'Before', 'After', 'Variance'],
         'rows': _rows_or_none(cost, 5, 'No per-activity budget changes.')},
        {'title': 'Resource changed — assignment before / after (moved from the Change Register)',
         'headers': ['Activity ID', 'Activity Name', 'Resource', 'Change', 'Before', 'After'],
         'rows': _rows_or_none(asg, 6, 'No resource-assignment changes.')},
    ]


def _cost_blocks(report):
    c = report.get('curves') or {}
    rc = report.get('resource_changes') or {}
    cost_av = c.get('cost_available') or rc.get('cost_available')
    res_av = c.get('resource_available') or rc.get('resource_available')
    has_curves = bool(c.get('months') or c.get('budget_by_dim')
                      or c.get('manpower_monthly') or c.get('manhours_by_trade'))
    if not (cost_av or res_av) and not has_curves:
        return [{'title': 'Cost & Resources',
                 'note': 'Neither revision carries resource loading or cost — reported as not applicable.',
                 'headers': ['Cost & resources'], 'rows': [['Not applicable']]}]

    blocks = []
    if not has_curves:
        # Cost / resource data present but no time-phased curves — go straight to the moved tables.
        return _cost_moved_blocks(report)
    # Planned value — monthly + cumulative merged by month
    cum = {r.get('month'): r for r in (c.get('value_cumulative') or [])}
    pv = []
    for r in (c.get('value_monthly') or []):
        mth = r.get('month')
        cr = cum.get(mth) or {}
        pv.append([_txt(mth), _num(r.get('rev0')), _num(r.get('rev1')), _num(r.get('var')),
                   _num(cr.get('rev0')), _num(cr.get('rev1')), _num(cr.get('var'))])
    vao = c.get('value_after_orig_finish')
    note = None
    if isinstance(vao, (int, float)) and vao:
        note = (f"{vao:,.2f} of planned value falls after the original governing finish — "
                f"extended-works exposure (prolongation, prelims, plant hire).")
    blocks.append({'title': 'Planned value of work — monthly & cumulative', 'note': note,
                   'headers': ['Month', 'Rev.00 monthly', 'Rev.01 monthly', 'Var',
                               'Rev.00 cum', 'Rev.01 cum', 'Cum Var'],
                   'rows': _rows_or_none(pv, 7, 'No time-phased planned value available.')})

    # Budget by dimension
    for dim, rows in (c.get('budget_by_dim') or {}).items():
        sub = [[_txt(x.get('category')), _num(x.get('rev0')), _num(x.get('rev1')), _num(x.get('var'))]
               for x in (rows or [])]
        blocks.append({'title': f'Budget by {dim} — where the money moved',
                       'headers': [dim, 'Before', 'After', 'Variance'],
                       'rows': _rows_or_none(sub, 4, 'No budget movement for this dimension.')})
    if not (c.get('budget_by_dim')):
        blocks.append({'title': 'Budget by dimension',
                       'headers': ['Dimension', 'Before', 'After', 'Variance'],
                       'rows': [['No budget breakdown available.', '', '', '']]})

    # Manpower histogram (persons/month) + peak
    peak = c.get('peak') or {}
    peak_note = None
    if peak.get('rev0') or peak.get('rev1'):
        peak_note = (f"Peak — Rev.00 {_num(peak.get('rev0'))} ({_txt(peak.get('rev0_month'), '—')}) · "
                     f"Rev.01 {_num(peak.get('rev1'))} ({_txt(peak.get('rev1_month'), '—')}).")
    mp = [[_txt(m.get('month')), _num(m.get('rev0')), _num(m.get('rev1')),
           _delta(m.get('rev0'), m.get('rev1'))] for m in (c.get('manpower_monthly') or [])]
    blocks.append({'title': 'Manpower histogram — persons / man-hours per month', 'note': peak_note,
                   'headers': ['Month', 'Rev.00', 'Rev.01', 'Δ'],
                   'rows': _rows_or_none(mp, 4, 'No manpower spread available.')})

    # Man-hours by trade + total
    trade = [[_txt(t.get('resource_id')), _txt(t.get('name')), _num(t.get('rev0')),
              _num(t.get('rev1')), _num(t.get('var')),
              {'added': 'Added', 'removed': 'Removed', 'changed': 'Changed'}.get(t.get('kind'), _txt(t.get('kind')))]
             for t in (c.get('manhours_by_trade') or [])]
    mt = c.get('manhours_total') or {}
    if trade:
        pct = mt.get('pct')
        pct_s = f" ({_sgn(round(pct, 1), '%')})" if isinstance(pct, (int, float)) else ''
        trade.append(['—', 'Total man-hours', _num(mt.get('rev0')), _num(mt.get('rev1')),
                      f"{_sgn(mt.get('var'))}{pct_s}" if mt.get('var') is not None else _num(mt.get('var')), ''])
    blocks.append({'title': 'Man-hours by trade — Rev.00 vs Rev.01',
                   'headers': ['Resource ID', 'Trade', 'Man-hrs Before', 'After', 'Variance', 'Change'],
                   'rows': _rows_or_none(trade, 6, 'No resource man-hours available.')})

    # Cost changed + Resource changed — moved in from the Change Register (comment 4).
    blocks.extend(_cost_moved_blocks(report))
    return blocks


# ── 7 · scope — Scope & Structure ────────────────────────────────────────────────

def _scope_blocks(report):
    wv = report.get('wbs_view') or {}

    def wbs_rows(nodes):
        out = []
        for n in (nodes or []):
            lvl = n.get('level')
            indent = '   ' * (lvl if isinstance(lvl, int) else 0)
            out.append([_num(lvl), f"{indent}{_txt(n.get('name'))}", _txt(n.get('state'))])
        return out

    sm = wv.get('summary') or {}
    summary_rows = [
        ['Branches added', _num(sm.get('added'))],
        ['Branches removed', _num(sm.get('removed'))],
        ['Branches moved', _num(sm.get('moved'))],
        ['Activities re-parented', _num(sm.get('reparented'))],
    ]

    ds = [[_txt(d.get('id')), _txt(d.get('name')), _txt(d.get('wbs'), '—'),
           f"{_txt(d.get('start0'), '—')} → {_txt(d.get('start1'), '—')}",
           f"{_txt(d.get('finish0'), '—')} → {_txt(d.get('finish1'), '—')}",
           _num(d.get('shift_wd'))] for d in (report.get('date_shifts') or [])]

    return [
        {'title': 'WBS comparison — Rev.00 (original)',
         'note': 'Primavera colour-grouping in the report; here one row per WBS branch.',
         'headers': ['Level', 'WBS', 'State'],
         'rows': _rows_or_none(wbs_rows(wv.get('rev0')), 3, 'No WBS structure available for Rev.00.')},
        {'title': 'WBS comparison — Rev.01 (revised)',
         'headers': ['Level', 'WBS', 'State'],
         'rows': _rows_or_none(wbs_rows(wv.get('rev1')), 3, 'No WBS structure available for Rev.01.')},
        {'title': 'WBS change summary', 'headers': ['Item', 'Count'], 'rows': summary_rows},
        {'title': 'Largest date shifts — activities whose dates moved',
         'headers': ['Activity ID', 'Activity Name', 'WBS', 'Start (before → after)',
                     'Finish (before → after)', 'Shift (wd)'],
         'rows': _rows_or_none(ds, 6, 'No material activity date shifts.')},
    ]


# ── assembly ────────────────────────────────────────────────────────────────────

def revcompare_excel(report):
    """Return the ``sheets`` list for ``write_sections_xlsx`` — one worksheet per canonical
    report section (summary · findings · critical · register · mcc · cost · scope), mirroring
    the seven redesigned on-screen tabs, the PDF's gated sections and the report-contents
    picker (same section keys throughout)."""
    report = report or {}
    return [
        {'name': 'Executive Summary', 'blocks': _summary_blocks(report),
         'col_widths': {0: 30, 1: 22, 2: 22, 3: 16, 4: 26, 5: 14}},
        {'name': 'Key Findings', 'blocks': _findings_blocks(report),
         'col_widths': {0: 22, 1: 22, 2: 18, 3: 20, 4: 20, 5: 16, 6: 16, 7: 16, 8: 14, 9: 12, 10: 10}},
        {'name': 'Critical Path & Float', 'blocks': _critical_blocks(report),
         'col_widths': {0: 6, 1: 16, 2: 32, 3: 14, 4: 22}},
        {'name': 'Change Register', 'blocks': _register_blocks(report),
         'col_widths': {0: 18, 1: 28, 2: 22, 3: 20, 4: 20, 5: 18, 6: 18, 7: 16, 8: 12, 9: 12}},
        # Excel caps sheet names (the writer trims to 28 chars) — this abbreviation keeps all
        # three subjects (screen tab / PDF / picker use the full "Milestones, Constraints & Calendars").
        {'name': 'Milestones, Constr. & Cals', 'blocks': _mcc_blocks(report),
         'col_widths': {0: 18, 1: 30, 2: 22, 3: 22, 4: 22, 5: 14}},
        {'name': 'Cost & Resources', 'blocks': _cost_blocks(report),
         'col_widths': {0: 20, 1: 20, 2: 16, 3: 14, 4: 14, 5: 14, 6: 14}},
        {'name': 'Scope & Structure', 'blocks': _scope_blocks(report),
         'col_widths': {0: 8, 1: 40, 2: 16, 3: 28, 4: 28, 5: 12}},
    ]
