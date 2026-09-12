"""Consultant-grade report for the Baseline Revision Comparison (redesigned).

Renders the report dict (from ``compare.build_report_from_data``) into a single
professional document laid out as the seven approved sections — Executive Summary,
Key Findings, Critical Path & Float, Change Register, Milestones/Constraints/Calendars,
Cost & Resources and Scope & Structure. It matches
``mockups/baseline-revision-interactive-concept.html``.

Every colour is read from the shared ``--rpt-*`` report theme tokens
(``report_theme``) so the on-screen preview and the exported PDF look identical
across all six appearance modes. No colour is ever hard-coded.

The report is strictly neutral — Change detected → Potential impact → Planning
review — and never uses verdict language. Every section guards its own empty
state with a muted "no data / not applicable" line and never crashes on missing
or partial data.
"""
import html as _html
import report_theme


# ── tiny formatting helpers ───────────────────────────────────────────────────

def _e(v):
    return _html.escape(str(v)) if v is not None else ''


def _num(v):
    """Human number: thousands-separated ints, 2dp floats, pass strings through."""
    if v is None or v == '':
        return '—'
    if isinstance(v, bool):
        return _e(v)
    if isinstance(v, (int, float)):
        f = float(v)
        if f.is_integer():
            return f'{int(f):,}'
        return f'{f:,.2f}'
    return _e(v)


def _money_num(v):
    """Parse a money value that may arrive as a formatted string ('420,000') into a float,
    so per-activity cost variance % can be computed without dividing by a string."""
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(',', '').replace('%', '').strip() or 0)
    except (ValueError, TypeError):
        return 0.0


def _sgn(v, unit=''):
    """Signed value with a leading + for positives; '—' for None."""
    if v is None:
        return '—'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return _e(v)
    iv = int(f) if f.is_integer() else round(f, 2)
    return f"{'+' if f > 0 else ''}{iv:,}{unit}" if isinstance(iv, int) else f"{'+' if f > 0 else ''}{iv}{unit}"


def _dcell(v, unit=''):
    """A coloured delta span: +ve = up (adverse), −ve = down (relieved), 0 = muted."""
    if v is None or v == '':
        return '<span class="d zero">—</span>'
    if isinstance(v, str):
        return f'<span class="d">{_e(v)}</span>'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return f'<span class="d">{_e(v)}</span>'
    cls = 'up' if f > 0 else 'down' if f < 0 else 'zero'
    return f'<span class="d {cls}">{_e(_sgn(f, unit))}</span>'


def _muted(msg):
    return f'<p class="mut nodata">{_e(msg)}</p>'


def _card(title, note, body):
    n = f'<span class="n">{_e(note)}</span>' if note else ''
    return f'<div class="card"><h3>{_e(title)} {n}</h3>{body}</div>'


def _secmark(num, title, sub=''):
    s = f'<span class="sub">{_e(sub)}</span>' if sub else ''
    return f'<div class="secmark"><span class="secn">{num}</span><h2>{_e(title)}</h2>{s}</div>'


def _tbl(head_html, body_rows, cls=''):
    """Wrap a table (thead html string, list-or-string of <tr> rows)."""
    body = body_rows if isinstance(body_rows, str) else ''.join(body_rows)
    return (f'<div class="tbl-wrap"><table class="{cls}"><thead>{head_html}</thead>'
            f'<tbody>{body}</tbody></table></div>')


# Slip-bridge cause colours — a CSS-var per index, paired with the matching track class in _CSS
# so the bar fill and the breakdown swatch always share a colour. Tokens only, never hard-coded.
_BRIDGE_COLORS = ['var(--rpt-good)', 'var(--rpt-bad)', 'var(--rpt-series-3)',
                  'var(--rpt-series-4)', 'var(--rpt-series-1)', 'var(--rpt-series-5)']
_BRIDGE_TRACK = ['fa', 'fr', 'f-s3', 'f-s4', 'f-s1', 'f-s5']
# Group colours for the logic-changes chart — one per activity-code value, rotating.
_GROUP_COLORS = ['var(--rpt-series-1)', 'var(--rpt-series-2)', 'var(--rpt-series-3)',
                 'var(--rpt-series-4)', 'var(--rpt-series-5)', 'var(--rpt-series-6)', 'var(--rpt-accent)']


# ══ 1 · EXECUTIVE SUMMARY ══════════════════════════════════════════════════════

def _snapshot(report):
    r0, r1 = report.get('rev0') or {}, report.get('rev1') or {}
    s = report.get('summary') or {}
    slip = s.get('finish_shift_days')
    slip_txt = _sgn(slip, 'd') if slip is not None else '—'

    def col(r, cls, tag):
        finish_cls = 'v hot' if cls == 'r1' and (slip or 0) > 0 else 'v'
        return f'''<div class="snapcol {cls}">
          <div class="snaptag">{_e(tag)}</div>
          <div class="snapfile">{_e(r.get('file') or '—')}</div>
          <div class="kv"><span class="k">Data date</span><span class="v">{_e(r.get('data_date') or '—')}</span></div>
          <div class="kv"><span class="k">Governing finish</span><span class="{finish_cls}">{_e(r.get('finish') or '—')}</span></div>
          <div class="kv"><span class="k">Activities</span><span class="v">{_num(r.get('activities'))}</span></div>
        </div>'''

    body = f'''<div class="snap">
        {col(r0, 'r0', 'Rev.00 · Original')}
        <div class="snapmid"><div class="big">{_e(slip_txt)}</div><div class="l">Finish slip</div></div>
        {col(r1, 'r1', 'Rev.01 · Revised')}
      </div>
      <div class="foot">Like-for-like comparison — both files at baseline (no actuals). Change detected → Potential impact → Planning review.</div>'''
    return _card('Revision snapshot', 'Rev.00 → Rev.01', body)


def _ledger(report):
    led = report.get('ledger') or []
    if not led:
        return _card('Comparison ledger', '', _muted('No comparison ledger available.'))
    rows = ''
    for e in led:
        r0 = e.get('rev0')
        r1 = e.get('rev1')
        dl = e.get('delta')
        # delta cell: numeric → coloured; string → as text; None → em dash
        dcell = _dcell(dl) if isinstance(dl, (int, float)) and not isinstance(dl, bool) else (
            f'<span class="d">{_e(dl)}</span>' if dl not in (None, '') else '<span class="mut">—</span>')
        rows += (f'<tr><td class="lbl">{_e(e.get("label"))}</td>'
                 f'<td class="n mut">{_num(r0)}</td>'
                 f'<td class="n new">{("" if r1 is None else _num(r1))}</td>'
                 f'<td class="n">{dcell}</td></tr>')
    head = '<tr><th>Measure</th><th class="n">Rev.00</th><th class="n">Rev.01</th><th class="n">Change</th></tr>'
    return _card('Comparison ledger', '', _tbl(head, rows))


def _redflags(report):
    q = report.get('quality') or {}
    cal = report.get('calendar_changes') or {}
    ne = q.get('negative_float') or {}
    oe = q.get('open_ends') or {}
    hc = q.get('hard_constraints') or {}
    ld = q.get('leads') or {}
    reass = cal.get('reassignments') or []
    cal_defs = len(cal.get('calendars') or [])
    cal_acts = sum((g.get('count') or 0) for g in reass)

    def row(label, r0, r1):
        return (f'<tr><td class="lbl">{_e(label)}</td><td class="n mut">{_num(r0)}</td>'
                f'<td class="n new">{_num(r1)}</td><td class="n">{_dcell((r1 or 0) - (r0 or 0))}</td></tr>')

    rows = [
        row('Negative-float activities', ne.get('rev0'), ne.get('rev1')),
        row('Open ends (dangling)', oe.get('rev0'), oe.get('rev1')),
        row('Hard constraints', hc.get('rev0'), hc.get('rev1')),
        row('Leads (negative lags)', ld.get('rev0'), ld.get('rev1')),
    ]
    if cal_defs or cal_acts:
        rows.append(
            f'<tr><td class="lbl">Calendars changed</td>'
            f'<td class="n mut" colspan="2" style="text-align:center">{cal_defs} definition(s) · {cal_acts} activities reassigned</td>'
            f'<td class="n"><span class="d up">!</span></td></tr>')
    head = '<tr><th>Signal</th><th class="n">Rev.00</th><th class="n">Rev.01</th><th class="n">Δ</th></tr>'
    body = _tbl(head, rows)
    return f'<div class="card flagcard"><h3 class="flagh">Schedule-quality signals</h3>{body}</div>'


def _scope_codes(report):
    codes = report.get('codes') or {}
    scope_by = codes.get('scope_by_code') or {}
    dims = codes.get('dimensions') or []
    # choose a dimension to chart: prefer a real code dim, else fall back to WBS
    dim = None
    for d in dims:
        if d in scope_by and scope_by[d]:
            dim = d
            break
    if dim is None:
        for d in scope_by:
            if scope_by[d]:
                dim = d
                break

    out = []
    if dim and scope_by.get(dim):
        cats = scope_by[dim]
        mx = max([(c.get('added', 0) + c.get('removed', 0)) for c in cats] + [1])
        bars = ''
        tot_add = tot_rem = 0
        for c in cats:
            a, rm = c.get('added', 0) or 0, c.get('removed', 0) or 0
            tot_add += a
            tot_rem += rm
            wa = round(a / mx * 100)
            wr = round(rm / mx * 100)
            bars += (f'<div class="bar"><div class="barl">{_e(c.get("category"))}</div>'
                     f'<div class="track"><div class="fa" style="width:{wa}%"></div>'
                     f'<div class="fr" style="width:{wr}%"></div></div>'
                     f'<div class="v">{a} / {rm}</div></div>')
        legend = (f'<div class="legend"><span><b class="sw-good"></b>Added ({tot_add})</span>'
                  f'<span><b class="sw-bad"></b>Removed ({tot_rem})</span>'
                  f'<span>by {_e(dim)}</span></div>')
        out.append(f'<div class="sec">Added &amp; removed activities by {_e(dim)}.</div>{bars}{legend}')
    else:
        out.append(_muted('No activity-code breakdown available for scope changes.'))

    added = codes.get('added') or []
    removed = codes.get('removed') or []
    if added or removed:
        rows = ''
        for it in added:
            rows += (f'<tr><td class="mono">{_e(it.get("id"))}</td><td>{_e(it.get("name"))}</td>'
                     f'<td><span class="tag add">Added</span></td>'
                     f'<td class="mut">{_e(it.get("building") or "—")}</td>'
                     f'<td class="mut">{_e(it.get("wbs") or "—")}</td>'
                     f'<td class="mut">{_e(it.get("scope") or "—")}</td></tr>')
        for it in removed:
            rows += (f'<tr><td class="mono">{_e(it.get("id"))}</td><td>{_e(it.get("name"))}</td>'
                     f'<td><span class="tag rem">Removed</span></td>'
                     f'<td class="mut">{_e(it.get("building") or "—")}</td>'
                     f'<td class="mut">{_e(it.get("wbs") or "—")}</td>'
                     f'<td class="mut">{_e(it.get("scope") or "—")}</td></tr>')
        head = ('<tr><th>Activity ID</th><th>Activity Name</th><th>Change</th>'
                '<th>Building</th><th>WBS (under)</th><th>Scope</th></tr>')
        out.append('<div style="margin-top:10px"></div>' + _tbl(head, rows))
    else:
        out.append('<div style="margin-top:8px"></div>' + _muted('No activities added or removed between the revisions.'))
    return _card('Scope change', 'added & removed, by activity code', ''.join(out))


def _sec_summary(report):
    bl = report.get('bottom_line')
    banner = (f'<div class="bottomline"><b>Bottom line:</b> {_e(bl)}</div>' if bl else '')
    return (banner
            + _snapshot(report)
            + '<div class="split">' + _ledger(report) + _redflags(report) + '</div>'
            + _scope_codes(report))


# ══ 2 · KEY FINDINGS ═══════════════════════════════════════════════════════════

def _slip_bridge(report):
    slip = report.get('slip') or {}
    contrib = slip.get('contributions') or []
    total = slip.get('total_wd')
    if not contrib:
        return _card('What drove the finish move', 'finish-slip bridge · neutral attribution',
                     _muted('No finish-slip attribution available (finish unchanged or no driving-path change).'))
    mx = max([abs(c.get('wd') or 0) for c in contrib] + [1])
    rows = ''
    for i, c in enumerate(contrib):
        wd = c.get('wd') or 0
        w = round(abs(wd) / mx * 100)
        cls = _BRIDGE_TRACK[i % len(_BRIDGE_TRACK)]
        rows += (f'<div class="bridge"><div class="brl">{_e(c.get("cause"))}</div>'
                 f'<div class="track"><div class="{cls}" style="width:{w}%"></div></div>'
                 f'<div class="v">{_e(_sgn(wd, " wd"))}</div></div>')
    tot = (f'<div class="bridge total"><div class="brl">Total finish move</div>'
           f'<div class="track"></div><div class="v">{_e(_sgn(total, " wd"))}</div></div>')
    howto = ('<div class="howto"><b>How to read it —</b> each row is a <b>cause</b>; the bar length is the '
             '<b>working days it added</b> to the finish. Bigger bar = bigger driver. The tool only '
             '<b>attributes</b> the move along the Rev.01 driving chain; it never says the change is wrong.</div>')
    # Contribution breakdown — one line per contribution: colour swatch · cause · +N d · meaning.
    breakdown = '<div class="contribs">'
    for i, c in enumerate(contrib):
        col = _BRIDGE_COLORS[i % len(_BRIDGE_COLORS)]
        breakdown += (f'<div class="contrib"><span class="sw" style="background:{col}"></span>'
                      f'<span class="cause">{_e(c.get("cause"))}</span>'
                      f'<span class="wd">{_e(_sgn(c.get("wd") or 0, " d"))}</span>'
                      f'<span class="mean">{_e(c.get("detail") or "")}</span></div>')
    breakdown += '</div>'
    foot = (f'<div class="foot">Rev.00 {_e(slip.get("rev0_finish") or "—")} → '
            f'Rev.01 {_e(slip.get("rev1_finish") or "—")}. Neutral — this attributes the slip, it does not judge the revision.</div>')
    return _card('What drove the finish move', 'finish-slip bridge · neutral attribution',
                 rows + tot + howto + breakdown + foot)


def _pick_logic_dim(report, rows):
    """Choose a grouping dimension for the logic chart: the first ``codes.dimensions`` value
    that actually tags at least one changed relationship, then ``'WBS'``, else ``None``
    (rows carry no activity codes → render ungrouped)."""
    dims = ((report.get('codes') or {}).get('dimensions')) or []
    for d in list(dims) + ['WBS']:
        if any((r.get('codes') or {}).get(d) for r in rows):
            return d
    return None


def _link_class(change):
    return {'Link added': 'added', 'Link removed': 'removed'}.get(change, 'changed')


def _tag_class(change):
    return {'Link added': 'add', 'Link removed': 'rem'}.get(change, 'chg')


def _rel_card(r):
    """One changed relationship as a Rev.00 → Rev.01 mini-diagram (pred —[link]→ succ),
    the changed link highlighted (amber = type/lag, green = added, red = removed)."""
    cls = _link_class(r.get('change'))
    tag = _tag_class(r.get('change'))
    cp = '<span class="cpbadge">on critical path</span>' if r.get('on_cp') else ''
    lead = ' <span class="tag rem">lead</span>' if r.get('is_lead') else ''
    pn, pi = _e(r.get('pred_name')), _e(r.get('pred_id'))
    sn, si = _e(r.get('succ_name')), _e(r.get('succ_id'))
    before, after = _e(r.get('before')), _e(r.get('after'))
    return (
        f'<div class="rel"><div class="reltop"><span class="tag {tag}">{_e(r.get("change"))}</span>{cp}{lead}</div>'
        f'<div class="chain"><span class="rlab">Rev.00</span>'
        f'<span class="node">{pn}<span class="id">{pi}</span></span>'
        f'<span class="link"><span class="lt">{before}</span></span><span class="arw">→</span>'
        f'<span class="node">{sn}<span class="id">{si}</span></span></div>'
        f'<div class="chain"><span class="rlab r1">Rev.01</span>'
        f'<span class="node">{pn}<span class="id">{pi}</span></span>'
        f'<span class="link {cls}"><span class="lt">{after}</span></span><span class="arw">→</span>'
        f'<span class="node">{sn}<span class="id">{si}</span></span></div></div>')


def _logic_changes(report):
    """Logic & Sequence Changes — a compact print form of the interactive chart. Every changed
    relationship (report.logic_register) drawn Rev.00 → Rev.01, grouped by an activity-code
    dimension. Replaces the old sequence roll-up and the standalone logic table."""
    rows = report.get('logic_register') or []
    if not rows:
        return _card('Logic & sequence changes', 'grouped by activity code',
                     _muted('No relationship / logic changes on matched activities.'))
    dim = _pick_logic_dim(report, rows)
    groups, order = {}, []
    for r in rows:
        g = ((r.get('codes') or {}).get(dim) if dim else None) or '(uncoded)'
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(r)
    sub = f'grouped by {_e(dim)}' if dim else 'ungrouped (no activity codes)'
    intro = ('<div class="sec">Every changed predecessor→successor link, drawn Rev.00 → Rev.01. '
             + (f'Grouped by {_e(dim)}; links on the critical path are badged.' if dim
                else 'Links on the critical path are badged.') + '</div>')
    out = [intro]
    for gi, g in enumerate(order):
        rs = groups[g]
        col = _GROUP_COLORS[gi % len(_GROUP_COLORS)]
        out.append(f'<div class="grouphd" style="border-left-color:{col}">'
                   f'<span class="gsw" style="background:{col}"></span>{_e(g)}'
                   f'<span class="ct">{len(rs)} change{"s" if len(rs) != 1 else ""}</span></div>')
        out.extend(_rel_card(r) for r in rs)
    return _card('Logic & sequence changes', sub, ''.join(out))


def _sec_findings(report):
    return _slip_bridge(report) + _logic_changes(report)


# ══ 3 · CRITICAL PATH & FLOAT ══════════════════════════════════════════════════

def _cp_chain(nodes):
    if not nodes:
        return '<div class="mut">No driving path available.</div>'
    parts = []
    for i, n in enumerate(nodes):
        st = n.get('state')
        cls = 'enter' if st == 'enter' else 'leave' if st == 'leave' else ('crit' if (n.get('tf') or 0) <= 0 else '')
        tf = n.get('tf')
        tf_txt = f'<br><span class="ntf">TF {tf}</span>' if tf is not None else ''
        parts.append(f'<span class="node {cls}">{_e(n.get("name"))}{tf_txt}</span>')
        if i < len(nodes) - 1:
            parts.append('<span class="arw">→</span>')
    return '<div class="chain">' + ''.join(parts) + '</div>'


def _critpath(report):
    cp = report.get('critical_path') or {}
    lc = cp.get('length_change_wd')
    note = ''
    if lc is not None:
        note = f'Rev.01 critical path is {_sgn(lc, " wd")} vs Rev.00.'
    entered = cp.get('entered') or []
    left = cp.get('left') or []
    ent_names = ', '.join(e.get('name') for e in entered) or '—'
    left_names = ', '.join(e.get('name') for e in left) or '—'
    body = (f'<div class="sec">{_e(note)}</div>'
            f'<div class="clab">Rev.00 driving chain</div>{_cp_chain(cp.get("rev0"))}'
            f'<div class="clab r1">Rev.01 driving chain</div>{_cp_chain(cp.get("rev1"))}'
            f'<div class="legend"><span><b class="sw-good"></b>Entered CP ({len(entered)}): {_e(ent_names)}</span>'
            f'<span><b class="sw-bad"></b>Left CP ({len(left)}): {_e(left_names)}</span></div>')
    return _card('Driving chain', 'critical path · entered / left', body)


def _float_bands(report):
    q = report.get('quality') or {}
    bands = q.get('float_bands') or []
    if not bands:
        return _card('Total-float band shift', 'Rev.00 vs Rev.01', _muted('No float distribution available.'))
    mx = max([max(b.get('rev0', 0) or 0, b.get('rev1', 0) or 0) for b in bands] + [1])
    rows = ''
    for b in bands:
        r0 = b.get('rev0', 0) or 0
        r1 = b.get('rev1', 0) or 0
        neg = str(b.get('band', '')).startswith('<0')
        lbl_cls = ' style="color:var(--rpt-bad)"' if neg else ''
        rows += (f'<div class="fband"><div class="fbl"{lbl_cls}>{_e(b.get("band"))}</div>'
                 f'<div class="fbtrack"><i class="f0" style="width:{round(r0 / mx * 100)}%"></i></div>'
                 f'<div class="fbtrack"><i class="f1" style="width:{round(r1 / mx * 100)}%"></i></div>'
                 f'<div class="v">{_num(r0)} / {_num(r1)}</div></div>')
    legend = '<div class="legend"><span><b class="sw-r0"></b>Rev.00</span><span><b class="sw-r1"></b>Rev.01</span></div>'
    return _card('Total-float band shift', 'Rev.00 vs Rev.01 · net working days', rows + legend)


def _neg_float(report):
    q = report.get('quality') or {}
    reg = (q.get('negative_float') or {}).get('register') or []
    if not reg:
        return ('<div class="card"><h3>Negative-float register</h3>'
                + _muted('No activities carry negative float in Rev.01.') + '</div>')
    rows = ''
    for a in reg:
        rows += (f'<tr><td class="mono">{_e(a.get("id"))}</td><td>{_e(a.get("name"))}</td>'
                 f'<td class="n"><span class="d up">{_e(_sgn(a.get("tf"), " d"))}</span></td>'
                 f'<td class="mut">{_e(a.get("wbs") or "—")}</td></tr>')
    head = '<tr><th>Activity ID</th><th>Activity Name</th><th class="n">Total Float</th><th>WBS</th></tr>'
    body = _tbl(head, rows)
    return (f'<div class="card flagcard"><h3 class="flagh">Negative-float register '
            f'<span class="n">{len(reg)} activities — re-plan trigger</span></h3>{body}</div>')


def _sec_critical(report):
    return _critpath(report) + '<div class="split">' + _float_bands(report) + _neg_float(report) + '</div>'


# ══ 4 · CHANGE REGISTER ════════════════════════════════════════════════════════

def _reg_duration(report):
    tbl = report.get('duration_table') or []
    if not tbl:
        return _card('Duration changed', 'working days · + calendar & float context',
                     _muted('No activity duration changes.'))
    rows = ''
    for r in tbl:
        before, after, var = r.get('before'), r.get('after'), r.get('variance')
        b_txt = f'{_num(before)} d' if isinstance(before, (int, float)) and not isinstance(before, bool) else _e(before)
        a_txt = f'{_num(after)} d' if isinstance(after, (int, float)) and not isinstance(after, bool) else _e(after)
        if before == '—':
            var_cell = '<span class="tag add">Added</span>'
        elif after == '—':
            var_cell = '<span class="tag rem">Removed</span>'
        else:
            var_cell = _dcell(var, ' d')
        cb, ca = r.get('calendar_before'), r.get('calendar_after')
        if cb == ca:
            cal_cell = f'<span class="mut">{_e(ca)} (same)</span>' if ca and ca != '—' else '<span class="mut">—</span>'
        else:
            cal_cell = f'<span class="tag chg">{_e(cb)}→{_e(ca)}</span>'
        if r.get('calendar_flag'):
            cal_cell += ' <span class="tag chg">cal</span>'
        tf = r.get('tf_after')
        rows += (f'<tr><td class="mono">{_e(r.get("id"))}</td><td>{_e(r.get("name"))}</td>'
                 f'<td class="n">{b_txt}</td><td class="n new">{a_txt}</td>'
                 f'<td class="n">{var_cell}</td><td>{cal_cell}</td>'
                 f'<td class="n">{("" if tf is None else _num(tf) + " d")}</td></tr>')
    head = ('<tr><th>Activity ID</th><th>Activity Name</th><th class="n">Before</th><th class="n">After</th>'
            '<th class="n">Variance</th><th>Calendar</th><th class="n">TF After</th></tr>')
    return _card('Duration changed', 'working days · + calendar & float context', _tbl(head, rows))


def _reg_milestones(report):
    ms = report.get('milestones') or []
    ms = [m for m in ms if m.get('kind') != 'unchanged']
    if not ms:
        return _card('Milestone changed', '', _muted('No milestone changes.'))
    tagcls = {'delayed': 'chg', 'advanced': 'add', 'new': 'add', 'removed': 'rem'}
    rows = ''
    for m in ms:
        chg = m.get('change_days')
        kind = m.get('kind')
        if kind in ('new', 'removed'):
            var_cell = f'<span class="tag {tagcls.get(kind, "chg")}">{kind.capitalize()}</span>'
        else:
            var_cell = _dcell(chg, ' d')
        rows += (f'<tr><td>{_e(m.get("name"))}</td>'
                 f'<td class="n">{_e(m.get("rev0") or "—")}</td>'
                 f'<td class="n new">{_e(m.get("rev1") or "—")}</td>'
                 f'<td class="n">{var_cell}</td></tr>')
    head = '<tr><th>Milestone</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th></tr>'
    return _card('Milestone changed', '', _tbl(head, rows))


def _reg_constraints(report):
    cons = report.get('constraint_changes') or []
    if not cons:
        return _card('Constraint changed', 'a hidden lever on the finish date', _muted('No constraint changes.'))
    _kl = {'added': 'Added', 'removed': 'Removed', 'type': 'Type changed', 'date': 'Date changed'}
    rows = ''
    for c in cons:
        kind = c.get('kind')
        tag = 'add' if kind == 'added' else 'rem' if kind == 'removed' else 'chg'
        hard = ' <span class="tag hard">Hard</span>' if c.get('hard') else ''
        rows += (f'<tr><td class="mono">{_e(c.get("activity_id"))}</td><td>{_e(c.get("name"))}</td>'
                 f'<td class="mut">{_e(c.get("rev0") or "—")}</td><td class="new">{_e(c.get("rev1") or "—")}</td>'
                 f'<td><span class="tag {tag}">{_e(_kl.get(kind, kind))}</span>{hard}</td></tr>')
    head = ('<tr><th>Activity ID</th><th>Activity Name</th><th>Constraint Before</th>'
            '<th>Constraint After</th><th>Change</th></tr>')
    body = _tbl(head, rows)
    foot = ('<div class="callout warn">A hard constraint on the driving path can pin or move the finish '
            'independently of logic — surfaced for review.</div>')
    return _card('Constraint changed', 'a hidden lever on the finish date', body + foot)


def _reg_calendars(report):
    cal = report.get('calendar_changes') or {}
    reass = cal.get('reassignments') or []
    defs = cal.get('calendars') or []
    if not reass and not defs:
        return _card('Calendar changed', 'reassignments & definition changes',
                     _muted('No calendar reassignments or definition changes.'))
    cols = []
    if reass:
        rows = ''
        for g in reass:
            ww = ('—' if g.get('from_wd') is None or g.get('to_wd') is None
                  else f'{g.get("from_wd")}-day → {g.get("to_wd")}-day')
            rows += (f'<tr><td>{_e(g.get("from"))}</td><td class="new">{_e(g.get("to"))}</td>'
                     f'<td>{_e(ww)}</td><td class="n">{_num(g.get("count"))}</td></tr>')
        head = '<tr><th>From</th><th>To</th><th>Workweek</th><th class="n">Activities</th></tr>'
        cols.append(_tbl(head, rows))
    if defs:
        rows = ''
        for d in defs:
            rows += (f'<tr><td>{_e(d.get("name"))}</td><td>{_e(d.get("change"))}</td>'
                     f'<td>{_e(d.get("detail"))}</td></tr>')
        head = '<tr><th>Calendar</th><th>Change</th><th>Detail</th></tr>'
        cols.append(_tbl(head, rows))
    body = '<div class="split">' + ''.join(cols) + '</div>' if len(cols) == 2 else ''.join(cols)
    foot = ('<div class="callout warn">A 5→6-day week or an hours/day change shortens durations on paper '
            'without changing the work — confirm the basis.</div>')
    return _card('Calendar changed', 'reassignments & definition changes', body + foot)


def _reg_resources(report):
    rc = report.get('resource_changes') or {}
    ac = rc.get('assignment_changes') or []
    if not ac:
        return _card('Resource changed', 'assignment before / after',
                     _muted('No resource assignment changes (or no resource loading in either revision).'))
    _kl = {'added': 'Added', 'removed': 'Removed', 'units': 'Units changed', 'rate': 'Rate changed'}
    rows = ''
    for a in ac:
        rows += (f'<tr><td class="mono">{_e(a.get("code"))}</td><td>{_e(a.get("resource"))}</td>'
                 f'<td><span class="tag chg">{_e(_kl.get(a.get("kind"), a.get("kind")))}</span></td>'
                 f'<td class="mut">{_e(a.get("rev0") or "—")}</td><td class="new">{_e(a.get("rev1") or "—")}</td></tr>')
    head = ('<tr><th>Activity ID</th><th>Resource</th><th>Change</th><th class="n">Before</th><th class="n">After</th></tr>')
    return _card('Resource changed', 'assignment before / after · one line per swap', _tbl(head, rows))


def _reg_cost(report):
    rc = report.get('resource_changes') or {}
    if not (rc.get('cost_available')):
        return _card('Cost changed', 'budget total cost · variance',
                     _muted('Neither revision carries cost loading — reported as not applicable.'))
    cc = rc.get('activity_cost_changes') or []
    rows = ''
    for c in cc:
        delta = c.get('delta')
        base = _money_num(c.get('rev0'))   # rev0 arrives as a formatted money string
        var_cell = _dcell(delta)
        pct = (f'{"+" if delta > 0 else ""}{round(delta / base * 100)}%'
               if base and delta is not None else '—')
        rows += (f'<tr><td class="mono">{_e(c.get("code"))}</td><td>{_e(c.get("name"))}</td>'
                 f'<td class="n">{_num(c.get("rev0"))}</td><td class="n new">{_num(c.get("rev1"))}</td>'
                 f'<td class="n">{var_cell}</td><td class="n mut">{_e(pct)}</td></tr>')
    tb = rc.get('total_budget') or {}
    d = tb.get('delta') or 0
    base = tb.get('rev0') or 0
    tpct = (f'{"+" if d > 0 else ""}{round(d / base * 100, 1)}%' if base else '—')
    rows += (f'<tr class="totrow"><td colspan="2">Total budget</td>'
             f'<td class="n">{_num(tb.get("rev0"))}</td><td class="n">{_num(tb.get("rev1"))}</td>'
             f'<td class="n">{_dcell(d)}</td><td class="n">{_e(tpct)}</td></tr>')
    head = ('<tr><th>Activity ID</th><th>Activity Name</th><th class="n">Before</th><th class="n">After</th>'
            '<th class="n">Variance</th><th class="n">%</th></tr>')
    return _card('Cost changed', 'budget total cost · variance % · subtotals', _tbl(head, rows))


def _sec_register(report):
    filt = ('<div class="card filterbar"><b>Change Register</b> — activity-duration changes only · '
            'separate Activity ID / Name columns · Before → After → Variance, with calendar &amp; float context. '
            '<span class="foot" style="margin:0">Logic changes are in <b>Key Findings</b>; milestones, '
            'constraints &amp; calendars have their own section; cost &amp; resource changes are in '
            '<b>Cost &amp; Resources</b>. Added / removed activities are inventoried in the Executive Summary.</span></div>')
    return filt + _reg_duration(report)


# ══ 5 · MILESTONES, CONSTRAINTS & CALENDARS ════════════════════════════════════

def _sec_mcc(report):
    return _reg_milestones(report) + _reg_constraints(report) + _reg_calendars(report)


# ══ 6 · COST & RESOURCES ═══════════════════════════════════════════════════════

def _scurve_svg(report):
    c = report.get('curves') or {}
    months = c.get('months') or []
    vm = c.get('value_monthly') or []
    vc = c.get('value_cumulative') or []
    if not c.get('cost_available') or not months or not vm:
        return _muted('Neither revision carries cost loading — the planned-value S-curve is not applicable.')
    n = len(months)
    W, H = 860, 280
    left, right, top, bot = 52, 30, 20, 40
    plot_w = W - left - right
    plot_h = H - top - bot
    step = plot_w / max(n, 1)
    bw = min(14, step / 3)
    max_m = max([max(m.get('rev0', 0) or 0, m.get('rev1', 0) or 0) for m in vm] + [1])
    # ONE shared cumulative max so the two curves keep their relative height (a bigger total
    # reads taller) — matching the screen; independent maxima would flatten the value gap.
    cum_mx = max([(x.get('rev0', 0) or 0) for x in vc] + [(x.get('rev1', 0) or 0) for x in vc] + [1])
    baseY = top + plot_h

    bars = []
    for i, m in enumerate(vm):
        x = left + i * step + step / 2
        h0 = (m.get('rev0', 0) or 0) / max_m * plot_h
        h1 = (m.get('rev1', 0) or 0) / max_m * plot_h
        bars.append(f'<rect x="{x - bw - 1:.1f}" y="{baseY - h0:.1f}" width="{bw:.1f}" height="{h0:.1f}" fill="var(--rpt-hair-strong)"/>')
        bars.append(f'<rect x="{x + 1:.1f}" y="{baseY - h1:.1f}" width="{bw:.1f}" height="{h1:.1f}" fill="var(--rpt-accent)" opacity="0.9"/>')

    def line(mx, key, stroke, sw):
        if not vc:
            return ''
        pts = []
        for i, x in enumerate(vc):
            px = left + i * step + step / 2
            py = baseY - (x.get(key, 0) or 0) / mx * plot_h
            pts.append(f'{px:.1f},{py:.1f}')
        return f'<polyline points="{" ".join(pts)}" fill="none" stroke="{stroke}" stroke-width="{sw}"/>'

    # original-finish marker: index of last month with rev0 value > 0
    orig_idx = None
    for i, m in enumerate(vm):
        if (m.get('rev0', 0) or 0) > 0:
            orig_idx = i
    orig_line = ''
    if orig_idx is not None:
        ox = left + orig_idx * step + step / 2
        orig_line = (f'<line x1="{ox:.1f}" y1="{top}" x2="{ox:.1f}" y2="{baseY}" stroke="var(--rpt-bad)" stroke-dasharray="4 3"/>'
                     f'<text x="{ox + 4:.1f}" y="{top + 12}" font-size="9" fill="var(--rpt-bad)">orig finish</text>')

    # sparse month labels
    labels = ''
    steplbl = max(1, n // 8)
    for i in range(0, n, steplbl):
        x = left + i * step + step / 2
        labels += f'<text x="{x:.1f}" y="{baseY + 14}" font-size="8" fill="var(--rpt-muted)" text-anchor="middle">{_e(months[i])}</text>'

    svg = (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto;min-width:640px">'
           f'<line x1="{left}" y1="{baseY}" x2="{W - right}" y2="{baseY}" stroke="var(--rpt-chart-axis)"/>'
           f'<line x1="{left}" y1="{top}" x2="{left}" y2="{baseY}" stroke="var(--rpt-chart-axis)"/>'
           + ''.join(bars)
           + line(cum_mx, 'rev0', 'var(--rpt-muted)', '2.2')
           + line(cum_mx, 'rev1', 'var(--rpt-accent)', '2.6')
           + orig_line + labels + '</svg>')
    legend = ('<div class="legend"><span><b class="sw-r0"></b>Rev.00 value/mo</span>'
              '<span><b class="sw-r1"></b>Rev.01 value/mo</span>'
              '<span><b class="sw-muted"></b>Rev.00 cum</span>'
              '<span><b class="sw-r1"></b>Rev.01 cum</span></div>')
    vao = c.get('value_after_orig_finish') or 0
    callout = (f'<div class="callout warn"><b>{_num(vao)} of planned value now falls after the original finish</b> — '
               'extended-works exposure (prolongation, prelims, plant hire).</div>' if vao else '')
    return svg + legend + callout


def _value_tables(report):
    c = report.get('curves') or {}
    vm = c.get('value_monthly') or []
    vc = c.get('value_cumulative') or []
    if not vm:
        return _card('Planned value table', 'monthly & cumulative', _muted('No time-phased planned value available.'))
    cum_by_month = {x.get('month'): x for x in vc}
    rows = ''
    for m in vm:
        cm = cum_by_month.get(m.get('month')) or {}
        rows += (f'<tr><td>{_e(m.get("month"))}</td><td class="n">{_num(m.get("rev0"))}</td>'
                 f'<td class="n new">{_num(m.get("rev1"))}</td><td class="n">{_dcell(m.get("var"))}</td>'
                 f'<td class="n mut">{_num(cm.get("var")) if cm else "—"}</td></tr>')
    head = ('<tr><th>Month</th><th class="n">Rev.00</th><th class="n">Rev.01</th>'
            '<th class="n">Var</th><th class="n">Cum Var</th></tr>')
    return _card('Planned value table', 'monthly & cumulative', _tbl(head, rows))


def _budget_by_dim(report):
    c = report.get('curves') or {}
    bd = c.get('budget_by_dim') or {}
    dim = None
    for d in bd:
        if bd[d]:
            dim = d
            break
    if not dim:
        return _card('Budget by discipline', 'where the money moved', _muted('No budget breakdown available.'))
    rows = ''
    for r in bd[dim]:
        rows += (f'<tr><td>{_e(r.get("category"))}</td><td class="n">{_num(r.get("rev0"))}</td>'
                 f'<td class="n new">{_num(r.get("rev1"))}</td><td class="n">{_dcell(r.get("var"))}</td></tr>')
    head = f'<tr><th>{_e(dim)}</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th></tr>'
    return _card('Budget by discipline', f'by {_e(dim)} · where the money moved', _tbl(head, rows))


def _manpower(report):
    c = report.get('curves') or {}
    mp = c.get('manpower_monthly') or []
    trades = c.get('manhours_by_trade') or []
    if not mp and not trades:
        return _card('Manpower', 'persons/month · man-hours by trade',
                     _muted('Neither revision carries resource units — manpower is not applicable.'))
    out = []
    if mp:
        n = len(mp)
        W, H = 860, 220
        left, top, bot = 52, 20, 30
        plot_w, plot_h = W - left - 30, H - top - bot
        step = plot_w / max(n, 1)
        bw = min(13, step / 3)
        mx = max([max(m.get('rev0', 0) or 0, m.get('rev1', 0) or 0) for m in mp] + [1])
        baseY = top + plot_h
        bars = ''
        for i, m in enumerate(mp):
            x = left + i * step + step / 2
            h0 = (m.get('rev0', 0) or 0) / mx * plot_h
            h1 = (m.get('rev1', 0) or 0) / mx * plot_h
            bars += (f'<rect x="{x - bw - 1:.1f}" y="{baseY - h0:.1f}" width="{bw:.1f}" height="{h0:.1f}" fill="var(--rpt-hair-strong)"/>'
                     f'<rect x="{x + 1:.1f}" y="{baseY - h1:.1f}" width="{bw:.1f}" height="{h1:.1f}" fill="var(--rpt-accent)"/>')
        peak = c.get('peak') or {}
        pk = ''
        if peak.get('rev1'):
            pk = (f'<text x="{left + 4}" y="{top + 10}" font-size="9" fill="var(--rpt-muted)">'
                  f'Rev.00 peak {_num(peak.get("rev0"))} ({_e(peak.get("rev0_month") or "—")}) · '
                  f'Rev.01 peak {_num(peak.get("rev1"))} ({_e(peak.get("rev1_month") or "—")})</text>')
        svg = (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto;min-width:640px">'
               f'<line x1="{left}" y1="{baseY}" x2="{W - 30}" y2="{baseY}" stroke="var(--rpt-chart-axis)"/>'
               f'<line x1="{left}" y1="{top}" x2="{left}" y2="{baseY}" stroke="var(--rpt-chart-axis)"/>'
               + bars + pk + '</svg>')
        legend = ('<div class="legend"><span><b class="sw-r0"></b>Rev.00/mo</span>'
                  '<span><b class="sw-r1"></b>Rev.01/mo</span></div>')
        out.append(svg + legend)
    if trades:
        rows = ''
        for t in trades:
            kind = t.get('kind')
            tag = {'added': 'add', 'removed': 'rem', 'changed': 'chg'}.get(kind, 'chg')
            klbl = {'added': 'Added', 'removed': 'Removed', 'changed': 'Units ↑'}.get(kind, kind)
            rows += (f'<tr><td class="mono">{_e(t.get("resource_id"))}</td><td>{_e(t.get("name"))}</td>'
                     f'<td class="n">{_num(t.get("rev0"))}</td><td class="n new">{_num(t.get("rev1"))}</td>'
                     f'<td class="n">{_dcell(t.get("var"))}</td><td><span class="tag {tag}">{_e(klbl)}</span></td></tr>')
        mt = c.get('manhours_total') or {}
        pct = mt.get('pct')
        pct_txt = f' ({"+" if (mt.get("var") or 0) > 0 else ""}{pct}%)' if pct is not None else ''
        rows += (f'<tr class="totrow"><td colspan="2">Total man-hours</td>'
                 f'<td class="n">{_num(mt.get("rev0"))}</td><td class="n">{_num(mt.get("rev1"))}</td>'
                 f'<td class="n">{_dcell(mt.get("var"))}{_e(pct_txt)}</td><td></td></tr>')
        head = ('<tr><th>Resource ID</th><th>Trade</th><th class="n">Man-hrs Before</th>'
                '<th class="n">After</th><th class="n">Variance</th><th>Change</th></tr>')
        out.append('<div style="margin-top:8px"></div>' + _tbl(head, rows))
    return _card('Manpower histogram', 'persons/month · Rev.00 vs Rev.01 · man-hours by trade', ''.join(out))


def _sec_cost(report):
    scurve = _card('Planned value of work', 'monthly bars + cumulative curves · Rev.00 vs Rev.01', _scurve_svg(report))
    return (scurve
            + '<div class="split">' + _value_tables(report) + _budget_by_dim(report) + '</div>'
            + _manpower(report)
            + _reg_cost(report) + _reg_resources(report))


# ══ 7 · SCOPE & STRUCTURE ══════════════════════════════════════════════════════

def _wbs_view(report):
    wv = report.get('wbs_view') or {}
    r0 = wv.get('rev0') or []
    r1 = wv.get('rev1') or []
    if not r0 and not r1:
        return _card('WBS comparison', 'Primavera colour-grouping', _muted('No WBS structure available.'))

    def bands(nodes):
        out = []
        for nd in nodes:
            lvl = min(int(nd.get('level', 0)), 3) + 1     # 1..4
            state = nd.get('state')
            scls = f' {state}' if state in ('added', 'removed', 'moved') else ''
            badge = (f'<span class="p6badge">{state}</span>' if state in ('added', 'removed', 'moved') else '')
            indent = int(nd.get('level', 0)) * 14
            out.append(f'<div class="p6band p6-l{lvl}{scls}" style="margin-left:{indent}px">'
                       f'{_e(nd.get("name"))}{badge}</div>')
        return ''.join(out) or '<div class="mut">—</div>'

    body = (f'<div class="split"><div><div class="clab">Rev.00 — original WBS</div>{bands(r0)}</div>'
            f'<div><div class="clab r1">Rev.01 — revised WBS</div>{bands(r1)}</div></div>')
    legend = ('<div class="legend"><span><b class="sw-l1"></b>L1</span><span><b class="sw-l2"></b>L2</span>'
              '<span><b class="sw-l3"></b>L3</span><span><b class="sw-l4"></b>L4</span>'
              '<span><b class="sw-good ol"></b>added</span><span><b class="sw-bad ol"></b>removed</span>'
              '<span><b class="sw-warn ol"></b>moved</span></div>')
    sm = wv.get('summary') or {}
    callout = (f'<div class="callout">{sm.get("added", 0)} branch(es) added · {sm.get("removed", 0)} removed · '
               f'{sm.get("moved", 0)} moved · {sm.get("reparented", 0)} activities re-parented.</div>')
    return _card('WBS comparison', 'Primavera colour-grouping · a colour per level', body + legend + callout)


def _date_shifts(report):
    ds = report.get('date_shifts') or []
    if not ds:
        return _card('Largest date shifts', 'activities whose dates moved', _muted('No material date shifts.'))
    rows = ''
    for d in ds:
        sw = d.get('shift_wd')
        if sw is None:
            shift_cell = '<span class="mut">new/removed</span>'
        else:
            shift_cell = _dcell(sw, ' d')
        rows += (f'<tr><td class="mono">{_e(d.get("id"))}</td><td>{_e(d.get("name"))}</td>'
                 f'<td class="mut">{_e(d.get("wbs") or "—")}</td>'
                 f'<td>{_e(d.get("start0") or "—")} → {_e(d.get("start1") or "—")}</td>'
                 f'<td>{_e(d.get("finish0") or "—")} → {_e(d.get("finish1") or "—")}</td>'
                 f'<td class="n">{shift_cell}</td></tr>')
    head = ('<tr><th>Activity ID</th><th>Activity Name</th><th>WBS</th>'
            '<th>Start (before → after)</th><th>Finish (before → after)</th><th class="n">Shift</th></tr>')
    return _card('Largest date shifts', 'activities whose dates moved', _tbl(head, rows))


def _sec_scope(report):
    return _wbs_view(report) + _date_shifts(report)


# ── header + document ──────────────────────────────────────────────────────────

def _header(report, meta):
    r0, r1 = report.get('rev0') or {}, report.get('rev1') or {}
    date = (meta or {}).get('report_date', '')
    bl = report.get('bottom_line')
    banner = ''  # bottom line lives inside the summary section so it follows the picker
    return f'''<div class="rh">
      <div><h1>Baseline Revision Comparison</h1>
        <div class="meta">Rev.00 <b>{_e(r0.get('file') or '—')}</b> &nbsp;→&nbsp; Rev.01 <b>{_e(r1.get('file') or '—')}</b></div></div>
      <div class="rhr"><div class="meta">Planning &amp; schedule review</div><div class="meta">{_e(date)}</div></div>
    </div>{banner}'''


# canonical section order: key, number, title, subtitle, builder, page-break-before
_SECTIONS = [
    ('summary',  1, 'Executive Summary',      '', _sec_summary, False),
    ('findings', 2, 'Key Findings',           'what drove the slip + logic & sequence changes by activity code', _sec_findings, True),
    ('critical', 3, 'Critical Path & Float',  'driving chain, entered/left, float-band shift, negative float', _sec_critical, True),
    ('register', 4, 'Change Register',        'activity-duration changes only · separate ID / Name columns', _sec_register, True),
    ('mcc',      5, 'Milestones, Constraints & Calendars', 'the date-driver changes, moved out of the register', _sec_mcc, True),
    ('cost',     6, 'Cost & Resources',       'S-curve, value, budget, manpower + cost & resource changes', _sec_cost, True),
    ('scope',    7, 'Scope & Structure',      'WBS in Primavera colour-grouping + largest date shifts', _sec_scope, True),
]


def render_html(report, meta=None, sections=None, theme='light'):
    """Render the full seven-section report.

    ``sections`` gates which of the seven canonical keys are emitted:
      * ``None``  → all seven (default)
      * ``[]``    → header only (picker cleared everything)
      * a list of keys → only those, in canonical order.
    Each section is wrapped in ``<section data-sec="KEY">``.
    """
    keys = set(sections) if sections is not None else None
    body = [_header(report, meta)]
    for key, num, title, sub, builder, brk in _SECTIONS:
        if keys is not None and key not in keys:
            continue
        try:
            inner = builder(report)
        except Exception as exc:   # never let one bad section crash the whole report
            inner = _muted(f'This section could not be rendered ({type(exc).__name__}).')
        cls = ' class="pagebreak"' if brk else ''
        body.append(f'<section data-sec="{key}"{cls}>{_secmark(num, title, sub)}{inner}</section>')

    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{_CSS}</style>'
            f'{report_theme.theme_style_tag(theme)}</head><body><div class="wrap">'
            + ''.join(body) + '</div></body></html>')


_CSS = '''
@page { size: A4 landscape; margin: 11mm; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color: var(--rpt-ink); font-size: 12px; margin: 0; }
.wrap { padding: 0; }
h1 { font-size: 20px; margin: 0; }
.rh { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid var(--rpt-edge); padding-bottom: 9px; margin-bottom: 12px; }
.rhr { text-align: right; } .meta { color: var(--rpt-muted); font-size: 10.5px; margin-top: 3px; } .meta b { color: var(--rpt-ink); }
section.pagebreak { page-break-before: always; }
section { page-break-inside: auto; }
.secmark { display: flex; align-items: center; gap: 10px; margin: 6px 0 12px; border-top: 2px solid var(--rpt-edge); padding-top: 14px; }
.secmark .secn { font-size: 11px; font-weight: 800; letter-spacing: .06em; color: var(--rpt-accent-ink); background: var(--rpt-accent); border-radius: 6px; padding: 4px 9px; }
.secmark h2 { font-size: 16px; margin: 0; color: var(--rpt-ink); }
.secmark .sub { font-size: 11px; color: var(--rpt-muted); }
h3 { margin: 0 0 8px; font-size: 13px; color: var(--rpt-ink); } h3 .n { font-size: 10.5px; font-weight: 600; color: var(--rpt-muted); margin-left: 6px; }
.mut { color: var(--rpt-muted); } .new { color: var(--rpt-ink); font-weight: 600; }
.nodata { font-style: italic; padding: 6px 2px; }
.mono { font-family: ui-monospace, Consolas, monospace; font-size: 11px; color: var(--rpt-ink-soft); }
.n { text-align: right; } .foot { font-size: 10.5px; color: var(--rpt-muted); margin-top: 8px; } .foot b { color: var(--rpt-ink); }
.card { background: var(--rpt-surface); border: 1px solid var(--rpt-edge); border-radius: 12px; padding: 14px 15px; margin-bottom: 12px; page-break-inside: avoid; }
.filterbar { background: var(--rpt-surface-2); font-size: 11.5px; color: var(--rpt-ink-soft); }
.filterbar b { color: var(--rpt-ink); }
.flagcard { border-color: var(--rpt-bad); } .flagh { color: var(--rpt-bad); }
.sec { font-size: 11px; color: var(--rpt-muted); margin-bottom: 10px; }
.split { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; } .split .card { margin-bottom: 0; }
.bottomline { background: var(--rpt-accent-soft); border: 1px solid var(--rpt-accent); border-left: 5px solid var(--rpt-accent); border-radius: 10px; padding: 11px 14px; font-size: 12.5px; margin-bottom: 12px; color: var(--rpt-ink); }
.bottomline b { color: var(--rpt-accent); }
/* tables */
.tbl-wrap { border: 1px solid var(--rpt-edge); border-radius: 10px; overflow: hidden; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 11px; }
th { text-align: left; font-size: 9px; text-transform: uppercase; letter-spacing: .04em; color: var(--rpt-th-ink); font-weight: 800; padding: 7px 8px; background: var(--rpt-th-bg); border-bottom: 1px solid var(--rpt-edge); }
th.n, td.n { text-align: right; }
td { padding: 6px 8px; border-bottom: 1px solid var(--rpt-hair); vertical-align: top; }
tr:last-child td { border-bottom: 0; }
td.bord, th.bord { border-right: 1px solid var(--rpt-hair); }
.totrow td { font-weight: 800; border-top: 2px solid var(--rpt-edge); background: var(--rpt-surface-2); }
.lbl { font-weight: 600; color: var(--rpt-ink-soft); }
.d { font-weight: 700; } .d.up { color: var(--rpt-bad); } .d.down { color: var(--rpt-good); } .d.zero { color: var(--rpt-muted); }
.tag { font-size: 9px; font-weight: 800; padding: 2px 7px; border-radius: 6px; white-space: nowrap; }
.tag.add { background: var(--rpt-good-bg); color: var(--rpt-good); } .tag.rem { background: var(--rpt-bad-bg); color: var(--rpt-bad); }
.tag.chg { background: var(--rpt-warn-bg); color: var(--rpt-warn); } .tag.hard { background: var(--rpt-bad-bg); color: var(--rpt-bad); }
.tag.bad { background: var(--rpt-bad-bg); color: var(--rpt-bad); } .tag.warn { background: var(--rpt-warn-bg); color: var(--rpt-warn); }
.tag.accent { background: var(--rpt-accent-soft); color: var(--rpt-accent); } .tag.muted { background: var(--rpt-surface-2); color: var(--rpt-muted); }
/* snapshot */
.snap { display: grid; grid-template-columns: 1fr auto 1fr; }
.snapcol { padding: 2px 16px; } .snapcol.r0 { border-left: 3px solid var(--rpt-muted); } .snapcol.r1 { border-left: 3px solid var(--rpt-accent); }
.snaptag { font-size: 11px; font-weight: 800; color: var(--rpt-muted); margin-bottom: 6px; } .snapcol.r1 .snaptag { color: var(--rpt-accent); }
.snapfile { font-weight: 700; font-size: 12px; margin-bottom: 8px; }
.kv { display: flex; justify-content: space-between; font-size: 12px; padding: 4px 0; border-top: 1px dashed var(--rpt-hair); } .kv .k { color: var(--rpt-muted); } .kv .v { font-weight: 600; } .kv .v.hot { color: var(--rpt-bad); }
.snapmid { display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 0 14px; min-width: 110px; text-align: center; }
.snapmid .big { font-size: 22px; font-weight: 800; color: var(--rpt-bad); } .snapmid .l { font-size: 10px; color: var(--rpt-muted); text-transform: uppercase; letter-spacing: .05em; margin-top: 4px; }
/* bars (scope + slip bridge) */
.bar { display: grid; grid-template-columns: 130px 1fr 70px; gap: 9px; align-items: center; font-size: 11.5px; padding: 3px 0; }
.barl { color: var(--rpt-ink-soft); }
.track { background: var(--rpt-surface-2); border-radius: 5px; height: 15px; overflow: hidden; display: flex; }
.track .fa { background: var(--rpt-good); height: 100%; } .track .fr { background: var(--rpt-bad); height: 100%; }
.track .f-s1 { background: var(--rpt-series-1); height: 100%; } .track .f-s3 { background: var(--rpt-series-3); height: 100%; }
.track .f-s4 { background: var(--rpt-series-4); height: 100%; } .track .f-s5 { background: var(--rpt-series-5); height: 100%; }
.bar .v { text-align: right; font-weight: 700; }
.bridge { display: grid; grid-template-columns: 150px 1fr 78px; gap: 9px; align-items: center; font-size: 11.5px; padding: 4px 0; border-bottom: 1px dashed var(--rpt-hair); }
.bridge .brl { font-weight: 600; color: var(--rpt-ink-soft); } .bridge .v { text-align: right; font-weight: 700; }
.bridge .brd { grid-column: 1 / 4; font-size: 10px; margin-top: 2px; }
.bridge.total { border-bottom: 0; border-top: 2px solid var(--rpt-edge); margin-top: 4px; padding-top: 6px; } .bridge.total .brl { color: var(--rpt-ink); font-weight: 800; }
/* float bands */
.fband { display: grid; grid-template-columns: 90px 1fr 1fr 74px; gap: 8px; align-items: center; font-size: 11px; padding: 3px 0; }
.fbl { font-weight: 600; } .fbtrack { background: var(--rpt-surface-2); border-radius: 5px; height: 12px; overflow: hidden; }
.fbtrack i { display: block; height: 100%; } .fbtrack .f0 { background: var(--rpt-hair-strong); } .fbtrack .f1 { background: var(--rpt-accent); }
.fband .v { text-align: right; font-weight: 700; }
/* legends + swatches */
.legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 10.5px; color: var(--rpt-muted); margin-top: 9px; }
.legend b { display: inline-block; width: 10px; height: 10px; border-radius: 3px; vertical-align: middle; margin-right: 4px; }
.sw-good { background: var(--rpt-good); } .sw-bad { background: var(--rpt-bad); } .sw-warn { background: var(--rpt-warn); }
.sw-muted { background: var(--rpt-muted); } .sw-r0 { background: var(--rpt-hair-strong); } .sw-r1 { background: var(--rpt-accent); }
.sw-l1 { background: var(--rpt-series-1); } .sw-l2 { background: var(--rpt-series-5); } .sw-l3 { background: var(--rpt-accent); } .sw-l4 { background: var(--rpt-series-4); }
.legend b.ol { background: transparent; }
.legend b.sw-good.ol { outline: 2px solid var(--rpt-good); } .legend b.sw-bad.ol { outline: 2px solid var(--rpt-bad); } .legend b.sw-warn.ol { outline: 2px solid var(--rpt-warn); }
/* findings */
.find { border: 1px solid var(--rpt-edge); border-left: 4px solid var(--rpt-muted); border-radius: 8px; padding: 9px 12px; margin-bottom: 8px; page-break-inside: avoid; }
.find.bad { border-left-color: var(--rpt-bad); } .find.warn { border-left-color: var(--rpt-warn); } .find.accent { border-left-color: var(--rpt-accent); }
.ft { font-weight: 700; font-size: 12px; } .fb { font-size: 11px; color: var(--rpt-ink-soft); margin-top: 4px; line-height: 1.5; } .fb b { color: var(--rpt-ink); }
.flow { display: flex; gap: 7px; align-items: center; margin-top: 6px; font-size: 10px; color: var(--rpt-muted); } .flow b { color: var(--rpt-accent); }
/* callouts */
.callout { border-radius: 10px; padding: 9px 12px; font-size: 11px; background: var(--rpt-accent-soft); color: var(--rpt-ink); margin-top: 10px; }
.callout.warn { background: var(--rpt-warn-bg); color: var(--rpt-warn); }
/* sequence roll-up + chains */
.grouplab { font-size: 11px; font-weight: 800; color: var(--rpt-ink-soft); background: var(--rpt-surface-2); padding: 5px 10px; border-radius: 6px; margin: 10px 0 4px; }
.seqitem { padding: 6px 4px; font-size: 11.5px; } .dirtag { font-size: 9px; font-weight: 800; padding: 1px 7px; border-radius: 5px; background: var(--rpt-warn-bg); color: var(--rpt-warn); margin-left: 6px; }
.chain { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 5px 0; } .chain.ind { margin-left: 22px; }
.node { border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 4px 9px; font-size: 10.5px; font-weight: 600; background: var(--rpt-surface); }
.node.moved { border-color: var(--rpt-warn); background: var(--rpt-warn-bg); color: var(--rpt-warn); }
.node.crit { border-color: var(--rpt-bad); background: var(--rpt-bad-bg); color: var(--rpt-bad); }
.node.enter { border-color: var(--rpt-good); background: var(--rpt-good-bg); color: var(--rpt-good); }
.node.leave { border-color: var(--rpt-bad); background: var(--rpt-bad-bg); color: var(--rpt-bad); text-decoration: line-through; }
.node .ntf { font-weight: 400; color: var(--rpt-muted); font-size: 9px; }
.arw { color: var(--rpt-muted); font-weight: 800; }
.clab { font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; color: var(--rpt-muted); margin-top: 8px; } .clab.r1 { color: var(--rpt-accent); }
/* slip-bridge how-to + contribution breakdown */
.howto { background: var(--rpt-accent-soft); color: var(--rpt-ink); border-radius: 10px; padding: 9px 12px; font-size: 11px; margin-top: 10px; } .howto b { color: var(--rpt-accent); }
.contribs { margin-top: 8px; }
.contrib { display: grid; grid-template-columns: 13px 150px 58px 1fr; gap: 8px; align-items: center; font-size: 11px; padding: 5px 0; border-top: 1px dashed var(--rpt-hair); }
.contrib .sw { width: 12px; height: 12px; border-radius: 3px; }
.contrib .cause { font-weight: 700; color: var(--rpt-ink-soft); }
.contrib .wd { font-weight: 800; text-align: right; }
.contrib .mean { color: var(--rpt-muted); font-size: 10.5px; }
/* logic & sequence changes chart (findings) */
.grouphd { display: flex; align-items: center; gap: 8px; font-size: 11.5px; font-weight: 800; color: var(--rpt-ink); background: var(--rpt-surface-2); border: 1px solid var(--rpt-edge); border-left: 5px solid var(--rpt-accent); border-radius: 6px; padding: 6px 11px; margin: 12px 0 7px; page-break-after: avoid; }
.grouphd .gsw { width: 10px; height: 10px; border-radius: 3px; }
.grouphd .ct { margin-left: auto; font-weight: 700; background: var(--rpt-surface); color: var(--rpt-ink-soft); border-radius: 5px; padding: 1px 8px; font-size: 10px; }
.rel { border: 1px solid var(--rpt-edge); border-radius: 9px; padding: 8px 11px; margin-bottom: 7px; page-break-inside: avoid; }
.reltop { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.cpbadge { font-size: 8.5px; font-weight: 800; color: var(--rpt-bad); background: var(--rpt-bad-bg); border: 1px solid var(--rpt-bad); border-radius: 5px; padding: 0 6px; }
.rlab { font-size: 9px; font-weight: 800; text-transform: uppercase; color: var(--rpt-muted); width: 42px; display: inline-block; } .rlab.r1 { color: var(--rpt-accent); }
.node .id { color: var(--rpt-muted); font-weight: 500; font-size: 9px; display: block; }
.link { display: inline-flex; align-items: center; color: var(--rpt-muted); font-size: 9.5px; font-weight: 800; }
.link .lt { background: var(--rpt-surface-2); border-radius: 4px; padding: 1px 6px; }
.link.changed { color: var(--rpt-warn); } .link.changed .lt { background: var(--rpt-warn-bg); }
.link.removed { color: var(--rpt-bad); } .link.removed .lt { background: var(--rpt-bad-bg); text-decoration: line-through; }
.link.added { color: var(--rpt-good); } .link.added .lt { background: var(--rpt-good-bg); }
/* WBS Primavera bands (theme-safe: coloured left edge per level, ink text) */
.p6band { display: flex; align-items: center; gap: 8px; padding: 6px 10px; font-weight: 700; color: var(--rpt-ink); background: var(--rpt-surface-2); border-left: 5px solid var(--rpt-series-1); border-radius: 4px; margin: 3px 0; font-size: 11.5px; }
.p6-l1 { border-left-color: var(--rpt-series-1); } .p6-l2 { border-left-color: var(--rpt-series-5); } .p6-l3 { border-left-color: var(--rpt-accent); } .p6-l4 { border-left-color: var(--rpt-series-4); }
.p6band.added { outline: 2px solid var(--rpt-good); } .p6band.removed { outline: 2px solid var(--rpt-bad); opacity: .8; text-decoration: line-through; } .p6band.moved { outline: 2px solid var(--rpt-warn); }
.p6badge { font-size: 8.5px; font-weight: 800; padding: 1px 6px; border-radius: 5px; background: var(--rpt-surface); color: var(--rpt-ink-soft); margin-left: auto; }
'''
