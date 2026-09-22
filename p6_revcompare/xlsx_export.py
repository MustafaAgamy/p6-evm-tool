"""Excel export for the Baseline Revision Comparison (Rev.00 vs Rev.01) — round-4 redesign.

Turns the report dict the client already holds (from ``compare.build_report_from_data``
/ ``/api/revcompare``) into the ``sheets`` structure consumed by the shared
``p6_evm.xlsx_writer.write_sections_xlsx`` — one worksheet per canonical report section,
each a stack of titled tables that MIRROR the on-screen tabs, the PDF ``data-sec`` sections
and the report-contents picker (same ten section keys throughout — the approved interactive
prototype ``mockups/baseline-revision-interactive-v2.html`` / ``ui/modules/revcompare.js``
``RC_TABS`` / ``p6_revcompare/exporters.py`` ``render_html``):

    summary   → Executive Summary   (bottom line · revision snapshot · comparison ledger ·
                schedule-quality signals · scope BY ACTIVITY CODE — no Building column)
    findings  → Key Findings        (finish-slip driver bridge + its contribution breakdown ·
                the "Logic & Sequence Changes" — every changed relationship as rows carrying
                a column per activity-code dimension · key findings list)
    critical  → Critical Path & Float (Rev.00/Rev.01 driving chains · membership change ·
                total-float band shift · negative-float register)
    register  → Change Register      (DURATION changed only — no Calendar / TF-After columns;
                Before → After → Variance → % change, filterable by activity code)
    ms        → Milestones           (Activity ID + Before → After → Variance — no Type column)
    cal       → Calendar             (one row per calendar: Rev.00 pattern · Rev.01 pattern ·
                activities + the per-activity reassignment summary)
    cost      → Cost & Resources     (planned-value S-curve · budget by activity code ·
                the itemised Cost changed table)
    resource  → Resources            (the Resource-changed assignment table — moved out of Cost)
    manpower  → Manpower             (man-hours by trade totals Rev.00 vs Rev.01 + the monthly
                man-hours-by-trade matrix behind the stacked combo chart)
    scope     → Scope & Structure    (WBS comparison Rev.00 / Rev.01 · largest date shifts)

The old combined "Milestones, Constraints & Calendars" sheet is split into separate
Milestones and Calendar sheets, and the Constraint table is REMOVED entirely (round-4
comment 6). Manpower is its own sheet (comments 11/12) and no longer trails Cost.

Nothing here computes a number — it only presents what ``build_report_from_data`` produced.
Money / value / man-hour cells are formatted through one shared thousands + 2-decimal
formatter (``_money`` — 124563 → "124,563.00"); counts (activities, days, float) stay plain
integers. Every table degrades to a single "No data" row when its source is empty (via
``_rows_or_none``), so the export never crashes on a sparse or partial report. Neutral
throughout: change detected, not judged.
"""

# severity code (as stored on register rows / findings) -> on-screen badge label
_SEV_LABEL = {'crit': 'Critical', 'hi': 'High', 'med': 'Review', 'low': 'Info'}
_KIND_LABEL = {'delayed': 'Delayed', 'advanced': 'Advanced', 'unchanged': 'Unchanged',
               'new': 'New', 'removed': 'Removed', 'idchange': 'ID changed'}
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


def _money(v, dash='—'):
    """Shared money / value / man-hour DISPLAY formatter — thousands separators and two
    decimals (124563 → "124,563.00"). Emitted as a string on purpose (a formatted display
    cell, not a number the writer needs for arithmetic); non-numeric passes through / dashes
    (round-4 comment 9)."""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return f"{v:,.2f}"
    return dash if v is None else str(v)


def _money_sgn(v, dash='—'):
    """Signed money / value delta, thousands + 2dp: +150,000.00 / -6,000.00 / 0.00."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return dash if v is None else str(v)
    return f"{'+' if v > 0 else ''}{v:,.2f}"


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


def _pct_change(before, variance):
    """Signed % duration change from a numeric before + variance (+40% / -33%); em-dash
    when either is non-numeric (added / removed rows) or before is zero."""
    if (isinstance(before, (int, float)) and not isinstance(before, bool) and before
            and isinstance(variance, (int, float)) and not isinstance(variance, bool)):
        return _sgn(round(variance / before * 100), '%')
    return '—'


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

    # Scope change — by activity code (the activity-code analysis; no Building column, comment 1)
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

    # Itemised added / removed — the trailing dimension-value column ("Main WBS") is dropped
    # (change 1) and the full-path column keeps only its "WBS Path" header; the WBS field
    # already carries the full path.
    itemised = ([[_txt(a.get('id')), _txt(a.get('name')), 'Added',
                  _txt(a.get('wbs'), '—')] for a in (codes.get('added') or [])]
                + [[_txt(a.get('id')), _txt(a.get('name')), 'Removed',
                    _txt(a.get('wbs'), '—')] for a in (codes.get('removed') or [])])
    blocks.append({'title': 'Scope changes — activities added / removed',
                   'headers': ['Activity ID', 'Activity Name', 'Change', 'WBS Path'],
                   'rows': _rows_or_none(itemised, 4, 'No activities added or removed.')})

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
    # paper). The on-screen WBS-breadcrumb boxes reduce here to the predecessor / successor
    # names + IDs and the code columns.
    dims = _logic_dims(report)
    lg_headers = list(dims) + ['Predecessor ID', 'Predecessor Name', 'Successor ID',
                               'Successor Name', 'Link Before', 'Link After', 'Change',
                               'Replacement predecessor', 'On CP?', 'Lead?']
    # Map each successor to the NEW predecessor links it gained, so a removed link names its
    # replacement (comment 1) — mirrors the screen/PDF.
    reg = report.get('logic_register') or []
    added_by_succ = {}
    for r in reg:
        if 'added' in str(r.get('change') or '').lower():
            added_by_succ.setdefault(r.get('succ_id'), []).append(r)
    lg = []
    for r in reg:
        rc = r.get('codes') or {}
        change = str(r.get('change') or '')
        low = change.lower()
        # Comment 1 — spell out "not linked in Rev.00" / "link removed" rather than a bare dash.
        before_txt = 'not linked in Rev.00' if 'added' in low else _txt(r.get('before'), '—')
        after_txt = 'link removed' if 'removed' in low else _txt(r.get('after'), '—')
        repl_txt = '—'
        if 'removed' in low:
            repl = [a for a in added_by_succ.get(r.get('succ_id'), []) if a.get('pred_id') != r.get('pred_id')]
            repl_txt = ('; '.join(f"{_txt(a.get('pred_name'))} ({_txt(a.get('after'))})" for a in repl)
                        if repl else 'open end — no replacement link added')
        lg.append([_txt(rc.get(d), '—') for d in dims]
                  + [_txt(r.get('pred_id')), _txt(r.get('pred_name')), _txt(r.get('succ_id')),
                     _txt(r.get('succ_name')), before_txt, after_txt,
                     _txt(r.get('change')), repl_txt, _onoff(r.get('on_cp')), _flag(r.get('is_lead'), 'Lead')])
    blocks.append({'title': 'Logic & Sequence Changes — every changed relationship (by activity code)',
                   'note': 'Before → After per predecessor→successor link, grouped/filterable by activity code; '
                           'an added link reads "not linked in Rev.00", a removed link reads "link removed" and '
                           'names its replacement predecessor; "On CP?" flags links touching the revised critical '
                           'path, leads (negative lags) flagged.',
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

def _pct_display(d):
    """% duration change for a duration row — prefer the report-supplied ``pct`` (the engine's
    own value), falling back to the before/variance derivation for older payloads."""
    p = d.get('pct')
    if isinstance(p, (int, float)) and not isinstance(p, bool):
        return _sgn(round(p), '%')
    return _pct_change(d.get('before'), d.get('variance'))


def _dur_note(d):
    """Neutral Note cell for a duration row: an ADDED activity (Rev.00 before is the em-dash
    placeholder) is tagged "New activity" so the reader knows the row is a new activity, not a
    duration change (change 3); a >±200% swing is flagged for justification. Both can show."""
    parts = []
    if d.get('before') == '—':
        parts.append('New activity')
    if d.get('big_variance'):
        parts.append('Needs justification (>±200%)')
    return ' · '.join(parts)


def _register_blocks(report):
    # Only the Duration changed table lives in the register now — Calendar / TF-After columns
    # removed (comment 3); a % change column added; milestone / calendar to their own sheets,
    # logic to Key Findings, cost / resource to Cost & Resources. A neutral "Note" column flags
    # a >±200% swing for justification (usually the activity/relationship type changed) and tags
    # a newly ADDED activity — never calls the change wrong.
    dur = [[_txt(d.get('id')), _txt(d.get('name')), _txt(d.get('wbs'), '—'),
            _num(d.get('before')), _num(d.get('after')), _num(d.get('variance')),
            _pct_display(d),
            _dur_note(d)]
           for d in (report.get('duration_table') or [])]
    return [{'title': 'Duration changed — working days',
             'note': 'Every activity whose planned duration moved. Filter by activity code on screen '
                     '(Discipline / Building / WBS); % change is the variance over the Rev.00 duration. '
                     'A >±200% swing is flagged for justification — usually the activity type or '
                     'relationship type changed, not an error.',
             'headers': ['Activity ID', 'Activity Name', 'WBS', 'Before', 'After', 'Variance',
                         '% change', 'Note'],
             'rows': _rows_or_none(dur, 8, 'No duration changes on matched activities.')}]


# ── 5 · ms — Milestones ──────────────────────────────────────────────────────────

def _ms_blocks(report):
    """Milestone changes as their own sheet — Activity ID + Before → After → Variance (the Type
    column is removed, change 4). Lists only actual changes (matches the PDF / screen), never
    unchanged milestones."""
    ms = []
    for m in (report.get('milestones') or []):
        cd = m.get('change_days')
        kind = m.get('kind')
        if kind == 'unchanged':
            continue
        if kind == 'new':
            change = 'Added'
        elif kind == 'removed':
            change = 'Removed'
        elif kind == 'idchange':
            # The engine folds the removed+added duplicate into one row (id "OLD → NEW",
            # both dates carried); a neutral "ID changed" tag, plus the day shift if the
            # engine measured one.
            change = f"ID changed ({_sgn(cd, ' d')})" if cd is not None else 'ID changed'
        elif cd is not None:
            change = _sgn(cd, ' d')
        else:
            change = _KIND_LABEL.get(kind, _txt(kind))
        ms.append([_txt(m.get('id'), '—'), _txt(m.get('name')),
                   _txt(m.get('rev0'), '—'), _txt(m.get('rev1'), '—'), change])
    return [{'title': 'Milestone changed — Activity ID · Before → After',
             'note': 'Finish milestones whose date moved, plus milestones added / removed between the '
                     'revisions.',
             'headers': ['Activity ID', 'Milestone', 'Before', 'After', 'Variance'],
             'rows': _rows_or_none(ms, 5, 'No finish-milestone changes between the revisions.')}]


# ── 6 · cal — Calendar ───────────────────────────────────────────────────────────

def _pattern_str(p):
    """A calendar working pattern for display: "N d/wk · H h/day · HPW h/wk" (change 5).
    Em-dash when the calendar is absent in that revision."""
    if not p:
        return '—'
    days, hours, hpw = p.get('days'), p.get('hours'), p.get('hpw')
    parts = []
    parts.append(f"{_num(days)} d/wk")
    parts.append(f"{_num(hours)} h/day")
    parts.append(f"{_num(hpw)} h/wk")
    return ' · '.join(parts)


def _cal_blocks(report):
    """Calendar changes as their own sheet — one row per calendar with its Rev.00 / Rev.01
    working pattern (change 5), plus the per-activity reassignment summary. The Constraint
    table is gone entirely."""
    cc = report.get('calendar_changes') or {}

    # One row per calendar: name · Rev.00 pattern · Rev.01 pattern · activities.
    patt = [[_txt(p.get('name')), _pattern_str(p.get('rev0')), _pattern_str(p.get('rev1')),
             _num(p.get('activities'))] for p in (cc.get('patterns') or [])]
    blocks = [{'title': 'Calendars — Rev.00 → Rev.01 working pattern',
               'note': 'One row per calendar: its working pattern (days/week · hours/day · hours/week) '
                       'in each revision, and how many activities use it.',
               'headers': ['Calendar', 'Rev.00 pattern', 'Rev.01 pattern', 'Activities'],
               'rows': _rows_or_none(patt, 4, 'No calendars found.')}]

    # Reassignment summary — activities that switched from one calendar to another.
    reassign = []
    for g in (cc.get('reassignments') or []):
        fw, tw = g.get('from_wd'), g.get('to_wd')
        change = _sgn(tw - fw, ' d/wk') if isinstance(fw, (int, float)) and isinstance(tw, (int, float)) else '—'
        reassign.append([_txt(g.get('from')), _txt(g.get('to')),
                         _num(fw), _num(tw), change, _num(g.get('count'))])
    blocks.append({'title': 'Working days per week — Rev.00 → Rev.01 (activities reassigned)',
                   'note': 'A calendar switched to a longer week shortens durations on paper without changing the '
                           'work — a paper acceleration to confirm. Days/week before → after per reassignment group.',
                   'headers': ['From calendar', 'To calendar', 'Days/week before', 'Days/week after',
                               'Days/week change', 'Activities'],
                   'rows': _rows_or_none(reassign, 6, 'No calendar assignment changes.')})

    # Mon→Sun working / non-working day grid, Rev.00 vs Rev.01, changed days flagged (comment 2).
    grid_rows = []
    for p in (cc.get('patterns') or []):
        g0, g1 = p.get('rev0_grid'), p.get('rev1_grid')
        if not (g0 or g1):
            continue
        changed = set(p.get('changed_days') or [])

        def state_cells(grid):
            return ['Work' if d.get('working') else 'Off' for d in (grid or [])]
        # Spell out the direction of the flip (now non-working / working), like the screen & PDF.
        if changed:
            becomes_nw = any((not d.get('working')) and d.get('day') in changed for d in (g1 or []))
            chg_txt = f"{', '.join(changed)} now {'non-working' if becomes_nw else 'working'}"
        else:
            chg_txt = '—'
        if g0:
            grid_rows.append([_txt(p.get('name')), 'Rev.00'] + state_cells(g0) + [chg_txt])
        if g1:
            grid_rows.append([_txt(p.get('name')), 'Rev.01'] + state_cells(g1) + [chg_txt])
    if grid_rows:
        blocks.append({'title': 'Calendar working-day grid — Mon→Sun (Rev.00 vs Rev.01)',
                       'note': 'Each calendar\'s Mon→Sun working (Work) / non-working (Off) pattern before and '
                               'after; the "Changed days" column lists any day whose working state flipped.',
                       'headers': ['Calendar', 'Revision', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun',
                                   'Changed days'],
                       'rows': grid_rows})

    # The specific calendar exception dates that CHANGED between the revisions (round-14): only a
    # date whose working/non-working state flipped, or whose hours changed (e.g. 6h/day → 8h/day).
    # Identical ('unchanged') dates are dropped — the reader only wants what moved.
    exc_rows = []
    counts = []
    for p in (cc.get('patterns') or []):
        for e in (p.get('date_exceptions') or []):
            if e.get('change') == 'unchanged':
                continue
            exc_rows.append([_txt(p.get('name')), _txt(e.get('date')), _txt(e.get('rev0')),
                             _txt(e.get('rev1')), _txt(e.get('change'))])
        nc = p.get('nonworking_count') or {}
        if nc.get('rev0') is not None or nc.get('rev1') is not None:
            counts.append(f"{p.get('name')}: {_num(nc.get('rev0') or 0)} non-working date(s) in Rev.00 · "
                          f"{_num(nc.get('rev1') or 0)} in Rev.01")
    count_note = (' Per-revision non-working dates — ' + ' · '.join(counts) + '.') if counts else ''
    if exc_rows:
        blocks.append({'title': 'Calendar exception changes — Rev.00 vs Rev.01',
                       'note': 'Only the specific dates that CHANGED between the revisions — a non-working ⇄ working '
                               'flip or an hours change (e.g. 6h/day → 8h/day). Identical dates are not listed.'
                               + count_note,
                       'headers': ['Calendar', 'Date', 'Rev.00', 'Rev.01', 'Change'],
                       'rows': exc_rows})
    elif counts:
        # Calendars were compared but no specific exception date changed (parity with screen/PDF).
        blocks.append({'title': 'Calendar exception changes — Rev.00 vs Rev.01',
                       'note': 'No specific exception date changed between the revisions — the exception dates '
                               '(holidays / reduced-hours days) are identical on both calendars.' + count_note,
                       'headers': ['Calendar', 'Date', 'Rev.00', 'Rev.01', 'Change'],
                       'rows': [['No changed exception dates', '', '', '', '']]})

    # Assigned activities — by calendar & activity code (round-14): which activities use each
    # calendar and at which activity code, taken from the revision the calendar exists in.
    asg_rows = []
    for p in (cc.get('patterns') or []):
        by_dim = ((p.get('assigned') or {}).get('by_dim')) or {}
        for dim, vals in by_dim.items():
            for v in (vals or []):
                asg_rows.append([_txt(p.get('name')), _txt(dim), _txt(v.get('value')), _num(v.get('count'))])
    if asg_rows:
        blocks.append({'title': 'Assigned activities — by calendar & activity code',
                       'note': 'Which activities use each calendar, grouped by activity code (from the revision the '
                               'calendar exists in — Rev.01 for added/renamed/modified, Rev.00 for removed).',
                       'headers': ['Calendar', 'Activity code (dimension)', 'Value', 'Activities'],
                       'rows': asg_rows})
    return blocks


# ── 7 · cost — Cost & Resources ──────────────────────────────────────────────────

def _itemised_cost_blocks(report):
    """The itemised per-activity Cost changed table + total budget — returned to Cost &
    Resources (change 6); the by-WBS roll-up sheet is gone (``cost_by_wbs`` stays in the
    engine but is no longer rendered)."""
    rc = report.get('resource_changes') or {}
    changes = rc.get('activity_cost_changes') or []
    cost = []
    for c in changes:
        # Money from the numeric *_num fields so every row matches the Total's 2dp format (comment 4).
        rev0 = c.get('rev0_num') if c.get('rev0_num') is not None else c.get('rev0')
        rev1 = c.get('rev1_num') if c.get('rev1_num') is not None else c.get('rev1')
        cost.append([_txt(c.get('code')), _txt(c.get('name')), _money(rev0),
                     _money(rev1), _money_sgn(c.get('delta'))])
    # Total of the CHANGED activities (comment 4) — the sum of the rows above, matching the screen
    # and the variance pie's Δ (not the whole-project budget). Prefer the raw *_num ints; fall back
    # to parsing the formatted rev0/rev1 (which may be money strings or plain numbers).
    def _cnum(c, num_key, str_key):
        v = c.get(num_key)
        if v is None:
            v = c.get(str_key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
        try:
            return float(str(v).replace(',', '').replace('%', '').strip() or 0)
        except (ValueError, TypeError):
            return 0.0
    if rc.get('cost_available') and changes:
        s0 = sum(_cnum(c, 'rev0_num', 'rev0') for c in changes)
        s1 = sum(_cnum(c, 'rev1_num', 'rev1') for c in changes)
        cost.append(['—', 'Total — changed activities', _money(s0), _money(s1), _money_sgn(s1 - s0)])
    return [{'title': 'Cost changed — budget total cost',
             'note': 'Informational — a cost change is not itself a schedule impact.',
             'headers': ['Activity ID', 'Activity Name', 'Before', 'After', 'Variance'],
             'rows': _rows_or_none(cost, 5, 'No per-activity budget changes.')}]


def _cost_blocks(report):
    c = report.get('curves') or {}
    rc = report.get('resource_changes') or {}
    cost_av = c.get('cost_available') or rc.get('cost_available')
    res_av = c.get('resource_available') or rc.get('resource_available')
    has_value = bool(c.get('value_monthly') or c.get('budget_by_dim'))
    if not (cost_av or res_av) and not has_value:
        return [{'title': 'Cost & Resources',
                 'note': 'Neither revision carries resource loading or cost — reported as not applicable.',
                 'headers': ['Cost & resources'], 'rows': [['Not applicable']]}]

    blocks = []
    # Planned value — monthly + cumulative merged by month (money formatted, comment 9)
    cum = {r.get('month'): r for r in (c.get('value_cumulative') or [])}
    pv = []
    for r in (c.get('value_monthly') or []):
        mth = r.get('month')
        cr = cum.get(mth) or {}
        pv.append([_txt(mth), _money(r.get('rev0')), _money(r.get('rev1')), _money_sgn(r.get('var')),
                   _money(cr.get('rev0')), _money(cr.get('rev1')), _money_sgn(cr.get('var'))])
    vao = c.get('value_after_orig_finish')
    note = None
    if isinstance(vao, (int, float)) and vao:
        note = (f"{_money(vao)} of planned value falls after the original governing finish — "
                f"extended-works exposure (prolongation, prelims, plant hire).")
    if c.get('value_monthly'):
        blocks.append({'title': 'Planned value of work — monthly & cumulative', 'note': note,
                       'headers': ['Month', 'Rev.00 monthly', 'Rev.01 monthly', 'Var',
                                   'Rev.00 cum', 'Rev.01 cum', 'Cum Var'],
                       'rows': _rows_or_none(pv, 7, 'No time-phased planned value available.')})

    # Budget by dimension — where the money moved (money formatted, comment 10)
    for dim, rows in (c.get('budget_by_dim') or {}).items():
        sub = [[_txt(x.get('category')), _money(x.get('rev0')), _money(x.get('rev1')), _money_sgn(x.get('var'))]
               for x in (rows or [])]
        blocks.append({'title': f'Budget by {dim} — where the money moved',
                       'headers': [dim, 'Before', 'After', 'Variance'],
                       'rows': _rows_or_none(sub, 4, 'No budget movement for this dimension.')})
    if not (c.get('budget_by_dim')) and cost_av:
        blocks.append({'title': 'Budget by dimension — where the money moved',
                       'headers': ['Dimension', 'Before', 'After', 'Variance'],
                       'rows': [['No budget breakdown available.', '', '', '']]})

    # Cost variance share by activity code (comment 4 — the on-screen pie in tabular form): for
    # each code dimension present on the changed activities, the share of the total |Δ cost|.
    cc = rc.get('activity_cost_changes') or []
    dims_present = []
    for x in cc:
        for k in (x.get('codes') or {}):
            if k not in dims_present:
                dims_present.append(k)
    for dim in dims_present:
        by_val = {}
        for x in cc:
            v = (x.get('codes') or {}).get(dim)
            if v in (None, ''):
                continue
            by_val[v] = by_val.get(v, 0) + abs(x.get('delta') or 0)
        tot = sum(by_val.values())
        if tot <= 0:
            continue
        share = [[_txt(k), _money(v), f"{round(v / tot * 100)}%"]
                 for k, v in sorted(by_val.items(), key=lambda kv: -kv[1])]
        share.append(['Total', _money(tot), '100%'])
        blocks.append({'title': f'Cost variance share by {dim}',
                       'note': 'Share of the total cost change carried by each activity-code value '
                               '(the on-screen pie) — |variance| per code value.',
                       'headers': [dim, 'Cost variance (|Δ|)', 'Share'],
                       'rows': share})

    # Cost reconciliation — where the budget sits (comment 3): the changed-activity total is only
    # part of the whole budget; this accounts for every currency unit (Changed + Unchanged + New
    # scope − Removed scope = Budget total). The final 'total' bucket is just another row.
    recon = rc.get('cost_reconciliation') or []
    if recon:
        # A zero side (New scope has rev0=0, Removed scope has rev1=0) prints '—', matching screen/PDF.
        recon_rows = [[_txt(b.get('label')), _txt(b.get('note')),
                       _money(b.get('rev0')) if b.get('rev0') else '—',
                       _money(b.get('rev1')) if b.get('rev1') else '—',
                       _money_sgn(b.get('delta'))] for b in recon]
        blocks.append({'title': 'Cost reconciliation — where the budget sits',
                       'note': 'The changed-activity total is only part of the whole budget; this accounts for '
                               'every currency unit — Changed + Unchanged + New scope − Removed scope = Budget '
                               'total. Answers "where does the remaining budget go".',
                       'headers': ['Bucket', 'What it is', 'Rev.00', 'Rev.01', 'Variance'],
                       'rows': recon_rows})

    # Itemised Cost changed table — returned to Cost & Resources (change 6). The by-WBS
    # roll-up sheet is removed; the Resource-changed table now has its own Resources sheet.
    blocks.extend(_itemised_cost_blocks(report))
    return blocks


# ── 7b · resource — Resources ─────────────────────────────────────────────────────

_RES_KIND_LABEL = {'added': 'Added', 'removed': 'Removed', 'increased': 'Increased',
                   'decreased': 'Reduced', 'unchanged': 'Unchanged'}


def _resource_blocks(report):
    """Resources — before vs after, at a glance (comments 5 & 6). The lead table is one row per
    resource from ``resource_changes.resource_totals``: id · type · assigned units Before → After ·
    variance · activities · Added / Removed / Increased / Reduced tag, with the added/removed/re-
    sized summary in the note. The raw per-activity assignment list is kept below as detail."""
    rc = report.get('resource_changes') or {}
    totals = rc.get('resource_totals') or []
    asg = rc.get('assignment_changes') or []

    rows = []
    for t in totals:
        v = t.get('var')
        if v is None:
            v = (t.get('rev1') or 0) - (t.get('rev0') or 0)
        rows.append([_txt(t.get('id'), '—'), _txt(t.get('name')), _txt(t.get('type'), '—'),
                     _num(t.get('rev0'), '—') if t.get('rev0') else '—',
                     _num(t.get('rev1'), '—') if t.get('rev1') else '—',
                     _sgn(v), _num(t.get('activities'), '0'),
                     _RES_KIND_LABEL.get(t.get('kind'), _txt(t.get('kind')))])

    sm = rc.get('summary') or {}
    n_add = sm.get('res_added', sum(1 for t in totals if t.get('kind') == 'added'))
    n_rem = sm.get('res_removed', sum(1 for t in totals if t.get('kind') == 'removed'))
    n_chg = sm.get('res_resized', sum(1 for t in totals if t.get('kind') in ('increased', 'decreased')))
    summary_note = (f'{n_add} added · {n_rem} removed · {n_chg} re-sized. One row per resource — assigned '
                    'units before → after, variance, activities it is on, and a clear change tag.')
    blocks = [{'title': 'Resource comparison — before vs after, per resource (Rev.00 → Rev.01)',
               'note': summary_note,
               'headers': ['Resource ID', 'Resource', 'Type', 'Rev.00 (units)', 'Rev.01 (units)',
                           'Variance', 'Activities', 'Change'],
               'rows': _rows_or_none(rows, 8, 'No resource changes between the revisions.')}]

    # Per-activity assignment detail — the individual changes behind the by-resource view above.
    detail = [[_txt(a.get('code')), _txt(a.get('name')), _txt(a.get('resource')),
               _ASG_KIND.get(a.get('kind'), _txt(a.get('kind'))), _txt(a.get('rev0'), '—'),
               _txt(a.get('rev1'), '—')] for a in asg]
    blocks.append({'title': 'Per-activity assignment detail',
                   'note': 'The individual assignment changes (added / removed / units / rate) behind the '
                           'by-resource comparison above.',
                   'headers': ['Activity ID', 'Activity Name', 'Resource', 'Change', 'Before', 'After'],
                   'rows': _rows_or_none(detail, 6, 'No resource-assignment changes.')})
    return blocks


# ── 8 · manpower — Manpower ──────────────────────────────────────────────────────

def _manpower_blocks(report):
    """Manpower as its own sheet (comments 11/12) — the man-hours-by-trade totals and the
    monthly man-hours-by-trade matrix that the stacked combo chart is drawn from. No tables
    below beyond what the chart carries."""
    c = report.get('curves') or {}
    res_av = c.get('resource_available')
    trade = c.get('manhours_by_trade') or []
    monthly_trade = c.get('manpower_by_trade') or []
    months = c.get('months') or []
    if not (res_av or trade or monthly_trade):
        return [{'title': 'Manpower',
                 'note': 'Neither revision carries resource man-hours — reported as not applicable.',
                 'headers': ['Manpower'], 'rows': [['Not applicable']]}]

    # Total man-hours + peak-on-site KPIs (round-14 / comment 5) — total planned man-hours in
    # each revision (from P6 planned units) and their % change, then the busiest month on site.
    peak = c.get('peak') or {}
    mt0 = c.get('manhours_total') or {}
    pct = mt0.get('pct')
    mh0, mh1 = mt0.get('rev0'), mt0.get('rev1')
    kpi_rows = [
        ['Total man-hours · Rev.00',
         _num(round(mh0)) if isinstance(mh0, (int, float)) and not isinstance(mh0, bool) else '—',
         'from P6 planned units'],
        ['Total man-hours · Rev.01',
         _num(round(mh1)) if isinstance(mh1, (int, float)) and not isinstance(mh1, bool) else '—',
         'from P6 planned units'],
        ['Change',
         (f"{_sgn(round(pct, 1), '%')}" if isinstance(pct, (int, float)) else '—'), 'Rev.00 → Rev.01'],
        ['Rev.00 peak on site', _num(int(round(peak.get('rev0') or 0))), _txt(peak.get('rev0_month'), '—')],
        ['Rev.01 peak on site', _num(int(round(peak.get('rev1') or 0))), _txt(peak.get('rev1_month'), '—')],
    ]
    blocks_pre = [{'title': 'Manpower on site — total man-hours & peak',
                   'note': 'Total planned man-hours in each revision (from P6 planned units) and the % change, '
                           'plus the peak people on site (busiest month) in each revision.',
                   'headers': ['Metric', 'Value', 'When / basis'],
                   'rows': kpi_rows}]

    # Man-hours by trade — Rev.00 vs Rev.01 totals (money/value formatted, comment 9)
    trows = [[_txt(t.get('resource_id')), _txt(t.get('name')), _money(t.get('rev0')),
              _money(t.get('rev1')), _money_sgn(t.get('var')),
              {'added': 'Added', 'removed': 'Removed', 'changed': 'Changed'}.get(t.get('kind'), _txt(t.get('kind')))]
             for t in trade]
    mt = c.get('manhours_total') or {}
    if trade:
        pct = mt.get('pct')
        pct_s = f" ({_sgn(round(pct, 1), '%')})" if isinstance(pct, (int, float)) else ''
        var = mt.get('var')
        trows.append(['—', 'Total man-hours', _money(mt.get('rev0')), _money(mt.get('rev1')),
                      (f"{_money_sgn(var)}{pct_s}" if var is not None else _money(var)), ''])
    blocks = blocks_pre + [{'title': 'Resource mix — man-hours by trade (Rev.00 vs Rev.01)',
               'note': 'Planned budgeted resource units (man-hours) per trade — the overall labour-mix shift. '
                       'The dashed line on the combo chart is Rev.00\'s monthly total.',
               'headers': ['Resource ID', 'Trade', 'Man-hrs Before', 'After', 'Variance', 'Change'],
               'rows': _rows_or_none(trows, 6, 'No resource man-hours available.')}]

    # People on site per month — Rev.00 vs Rev.01 (comment 4): the paired bars in the redesigned
    # manpower chart. Monthly people-on-site totals in each revision and the signed difference.
    manpower_monthly = c.get('manpower_monthly') or []
    if manpower_monthly:
        mm_rows = []
        for m in manpower_monthly:
            d = round((m.get('rev1') or 0) - (m.get('rev0') or 0))
            mm_rows.append([_txt(m.get('month')), _num(round(m.get('rev0') or 0)),
                            _num(round(m.get('rev1') or 0)), f"{'+' if d > 0 else ''}{d}"])
        blocks.insert(1, {'title': 'People on site per month — Rev.00 vs Rev.01',
                          'note': 'Monthly people-on-site totals in each revision and the difference — the '
                                  'paired bars in the redesigned manpower chart.',
                          'headers': ['Month', 'Rev.00', 'Rev.01', 'Difference'],
                          'rows': mm_rows})

    # Monthly man-hours by trade — the matrix behind the stacked combo chart (Rev.01).
    if monthly_trade and months:
        names = [_txt(t.get('trade')) for t in monthly_trade]
        headers = ['Month'] + names + ['Monthly total']
        rows = []
        for i, mth in enumerate(months):
            per = [(t.get('monthly') or [])[i] if i < len(t.get('monthly') or []) else 0.0
                   for t in monthly_trade]
            tot = sum(v for v in per if isinstance(v, (int, float)))
            rows.append([_txt(mth)] + [_money(v) for v in per] + [_money(tot)])
        # column of trade totals as a footer row
        totals = [t.get('total') for t in monthly_trade]
        grand = sum(v for v in totals if isinstance(v, (int, float)))
        rows.append(['Total'] + [_money(v) for v in totals] + [_money(grand)])
        blocks.append({'title': 'Man-hours by month, by trade — Rev.01 (stacked combo chart)',
                       'note': 'Each month stacked by trade; the monthly total is the label above each bar.',
                       'headers': headers,
                       'rows': _rows_or_none(rows, len(headers), 'No monthly man-hours by trade available.')})
    return blocks


# ── 9 · scope — Scope & Structure ────────────────────────────────────────────────

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
    report section (summary · findings · critical · register · ms · cal · cost · resource ·
    manpower · scope), mirroring the ten redesigned on-screen tabs, the PDF's gated sections
    and the report-contents picker (same section keys throughout)."""
    report = report or {}
    return [
        {'name': 'Executive Summary', 'blocks': _summary_blocks(report),
         'col_widths': {0: 30, 1: 26, 2: 26, 3: 16, 4: 26}},
        {'name': 'Key Findings', 'blocks': _findings_blocks(report),
         'col_widths': {0: 22, 1: 22, 2: 18, 3: 20, 4: 20, 5: 16, 6: 16, 7: 16, 8: 14, 9: 12, 10: 10}},
        {'name': 'Critical Path & Float', 'blocks': _critical_blocks(report),
         'col_widths': {0: 6, 1: 16, 2: 32, 3: 14, 4: 22}},
        {'name': 'Change Register', 'blocks': _register_blocks(report),
         'col_widths': {0: 18, 1: 30, 2: 24, 3: 12, 4: 12, 5: 12, 6: 12, 7: 26}},
        {'name': 'Milestones', 'blocks': _ms_blocks(report),
         'col_widths': {0: 16, 1: 32, 2: 20, 3: 20, 4: 16}},
        {'name': 'Calendar', 'blocks': _cal_blocks(report),
         'col_widths': {0: 24, 1: 26, 2: 26, 3: 12, 4: 16, 5: 16}},
        {'name': 'Cost & Resources', 'blocks': _cost_blocks(report),
         'col_widths': {0: 20, 1: 24, 2: 18, 3: 16, 4: 16, 5: 16, 6: 16}},
        {'name': 'Resources', 'blocks': _resource_blocks(report),
         'col_widths': {0: 24, 1: 16, 2: 16, 3: 16, 4: 14, 5: 44}},
        {'name': 'Manpower', 'blocks': _manpower_blocks(report),
         'col_widths': {0: 16, 1: 22, 2: 16, 3: 16, 4: 16, 5: 14}},
        {'name': 'Scope & Structure', 'blocks': _scope_blocks(report),
         'col_widths': {0: 8, 1: 40, 2: 16, 3: 28, 4: 28, 5: 12}},
    ]
