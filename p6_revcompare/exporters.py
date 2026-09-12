"""Consultant-grade report for the Baseline Revision Comparison (redesigned).

Renders the report dict (from ``compare.build_report_from_data``) into a single
professional document laid out as the NINE approved sections — Executive Summary,
Key Findings, Critical Path & Float, Change Register (Duration only), Milestones,
Calendar, Cost & Resources, Manpower and Scope & Structure. It matches the approved
interactive prototype ``mockups/baseline-revision-interactive-v2.html`` in layout
and behaviour.

Every colour is read from the shared ``--rpt-*`` report theme tokens
(``report_theme``) so the on-screen preview and the exported PDF look identical
across all six appearance modes. No colour is ever hard-coded.

The report is strictly neutral — Change detected → Potential impact → Planning
review — and never uses verdict language. Every section guards its own empty
state with a muted "no data / not applicable" line and never crashes on missing
or partial data.

PDF-reflects-selection: ``render_html`` takes a ``filters`` dict so the printed
report renders the exact filtered view the planner chose on screen::

    filters = { scope:{dim,val}, logic:{dim,val}, duration:{dim,val}, money:{dim} }

Each key is optional; a missing key (or ``val`` == 'All' / absent) means no filter.
"""
import html as _html
import re
import report_theme


# ── tiny formatting helpers ───────────────────────────────────────────────────

def _e(v):
    return _html.escape(str(v)) if v is not None else ''


def _num(v):
    """Human count: thousands-separated ints, 2dp floats, pass strings through.
    Used for whole counts (activities, float-band populations)."""
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
    """Parse a value that may arrive as a formatted string ('420,000') into a float,
    so variance % can be computed without dividing by a string."""
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(',', '').replace('%', '').strip() or 0)
    except (ValueError, TypeError):
        return 0.0


def _money(v):
    """THE shared money/value/cost formatter (comment 9): thousands separators + 2dp,
    e.g. 124563 → '124,563.00'. '—' for missing; strings that aren't numeric pass through."""
    if v is None or v == '':
        return '—'
    if isinstance(v, bool):
        return _e(v)
    if isinstance(v, (int, float)):
        return f'{float(v):,.2f}'
    try:
        return f'{float(str(v).replace(",", "").strip()):,.2f}'
    except (ValueError, TypeError):
        return _e(v)


def _money_label(v):
    """Compact money for a chart bar label (comment 8): '1.2M' / '640K' / '820.00'."""
    try:
        f = float(_money_num(v))
    except (ValueError, TypeError):
        return _e(v)
    sign = '+' if f > 0 else '−' if f < 0 else ''
    a = abs(f)
    if a >= 1e6:
        body = f'{a / 1e6:.1f}M' if a / 1e6 >= 10 else f'{a / 1e6:.2f}M'
    elif a >= 1e3:
        body = f'{a / 1e3:.0f}K'
    else:
        body = f'{a:,.2f}'
    return f'{sign}{body}'


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


def _money_delta(v):
    """A coloured money delta span (thousands + 2dp, signed) for cost/value variances."""
    if v is None or v == '':
        return '<span class="d zero">—</span>'
    try:
        f = float(_money_num(v))
    except (TypeError, ValueError):
        return f'<span class="d">{_e(v)}</span>'
    cls = 'up' if f > 0 else 'down' if f < 0 else 'zero'
    sign = '+' if f > 0 else ''
    return f'<span class="d {cls}">{sign}{f:,.2f}</span>'


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


# ── filters + shared chart helpers ─────────────────────────────────────────────

def _filt(filters, key):
    """(dim, val) the planner chose for one section, from the ``filters`` dict; a missing
    entry or blank val yields (None, 'All')."""
    f = (filters or {}).get(key) if isinstance(filters, dict) else None
    if not isinstance(f, dict):
        return None, 'All'
    val = f.get('val')
    if val in (None, ''):
        val = 'All'
    return f.get('dim'), val


# Rotating series palette (tokens only) — one colour per activity-code value / trade / group.
_SERIES = ['var(--rpt-series-1)', 'var(--rpt-series-2)', 'var(--rpt-series-3)',
           'var(--rpt-series-4)', 'var(--rpt-series-5)', 'var(--rpt-series-6)', 'var(--rpt-accent)']


def _series_color(i):
    return _SERIES[i % len(_SERIES)]


def _dims_present(declared, entries):
    """Activity-code dimensions that actually tag at least one entry (each entry carries a
    ``codes`` map), declared dimensions first then any extras (e.g. the synthetic 'WBS')."""
    seen = []
    for e in entries:
        for k in (e.get('codes') or {}):
            if k not in seen:
                seen.append(k)
    out = [d for d in (declared or []) if d in seen]
    for k in seen:
        if k not in out:
            out.append(k)
    return out


def _resolve_dim(filters, key, dims):
    """The dimension to use: the planner's pick when it exists in the data, else the first
    available dimension, else None. Returns (dim, val)."""
    dim, val = _filt(filters, key)
    if dim not in dims:
        dim = dims[0] if dims else None
        val = 'All'
    return dim, val


def _bars_svg(items, min_w=560):
    """Vertical histogram with a data label ABOVE each bar (comments 1, 3, 8, 10).

    ``items``: [{label (x-axis), vlabel (above bar), mag (bar height driver, may be < 0),
    color}]. Bars grow up from the axis; height ∝ |mag| / max|mag|. Tokens only."""
    if not items:
        return ''
    n = len(items)
    w = max(min_w, n * 70)
    h, L, B, T = 230, 46, 40, 26
    pw, ph = w - L - 16, h - T - B
    step = pw / n
    bw = min(38, step * 0.6)
    mx = max([abs(it.get('mag') or 0) for it in items] + [1])
    base = T + ph
    s = ''
    for i, it in enumerate(items):
        x = L + i * step + step / 2
        bh = abs(it.get('mag') or 0) / mx * ph
        y = base - bh
        col = it.get('color') or 'var(--rpt-accent)'
        s += f'<rect x="{x - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="3" fill="{col}"/>'
        s += (f'<text x="{x:.1f}" y="{y - 6:.1f}" font-size="10" font-weight="700" '
              f'fill="var(--rpt-ink-soft)" text-anchor="middle">{_e(it.get("vlabel", ""))}</text>')
        s += (f'<text x="{x:.1f}" y="{base + 14:.1f}" font-size="9" fill="var(--rpt-muted)" '
              f'text-anchor="middle">{_e(it.get("label", ""))}</text>')
    return (f'<div class="chartwrap"><svg viewBox="0 0 {w} {h}" style="height:230px;min-width:{w}px">'
            f'<line x1="{L}" y1="{base}" x2="{w - 16}" y2="{base}" stroke="var(--rpt-chart-axis)"/>'
            f'{s}</svg></div>')


# Slip-bridge cause colours — a CSS-var per index, paired with the matching track class in _CSS.
_BRIDGE_COLORS = ['var(--rpt-good)', 'var(--rpt-bad)', 'var(--rpt-series-3)',
                  'var(--rpt-series-4)', 'var(--rpt-series-1)', 'var(--rpt-series-5)']
_BRIDGE_TRACK = ['fa', 'fr', 'f-s3', 'f-s4', 'f-s1', 'f-s5']


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


def _scope_analysis(report, filters):
    """Comment 1 — scope change as an activity-code ANALYSIS. Pick a dimension, then a code
    value: the count, a bar chart (added activities per code value) and the itemised list all
    reflect the ``filters.scope`` selection. No Building column in the table."""
    codes = report.get('codes') or {}
    added = [{**it, 'k': 'Added'} for it in (codes.get('added') or [])]
    removed = [{**it, 'k': 'Removed'} for it in (codes.get('removed') or [])]
    all_rows = added + removed
    if not all_rows:
        return _card('Scope change', 'analysis by activity code',
                     _muted('No activities added or removed between the revisions.'))

    dims = _dims_present(codes.get('dimensions'), all_rows)
    dim, val = _resolve_dim(filters, 'scope', dims)
    intro = ('<div class="sec">How many activities were added / removed, by activity code. '
             + (f'Grouped by <b>{_e(dim)}</b>' if dim else 'No activity-code dimension available')
             + (f'; showing the <b>{_e(val)}</b> selection.' if val != 'All' else '.') + '</div>')

    if dim:
        vals = []
        for r in all_rows:
            cv = (r.get('codes') or {}).get(dim) or '(uncoded)'
            if cv not in vals:
                vals.append(cv)
        items = []
        for i, cv in enumerate(vals):
            cnt = sum(1 for r in added if ((r.get('codes') or {}).get(dim) or '(uncoded)') == cv)
            items.append({'label': cv, 'vlabel': _num(cnt), 'mag': cnt, 'color': _series_color(i)})
        chart = (f'<div class="chartlab">ADDED ACTIVITIES BY {_e(str(dim).upper())}</div>'
                 + _bars_svg(items))
    else:
        chart = _muted('No activity-code breakdown available for scope changes.')

    def matches(r):
        return val == 'All' or (dim and ((r.get('codes') or {}).get(dim)) == val)

    frows = [r for r in all_rows if matches(r)]
    n_add = sum(1 for r in frows if r['k'] == 'Added')
    n_rem = sum(1 for r in frows if r['k'] == 'Removed')
    callout = (f'<div class="callout">Showing <b>{_e(val)}</b>: <b>{n_add} added</b> · '
               f'<b>{n_rem} removed</b>.</div>')

    col_lbl = 'Discipline / code' if dim == 'WBS' else (dim or 'Code')
    rows = ''
    for r in frows:
        cv = (r.get('codes') or {}).get(dim) if dim else None
        if dim == 'WBS':
            # avoid repeating WBS in both columns — show any other code value
            other = next((v for k, v in (r.get('codes') or {}).items() if k != 'WBS' and v), None)
            cv = other
        tag = 'add' if r['k'] == 'Added' else 'rem'
        rows += (f'<tr><td class="mono">{_e(r.get("id"))}</td><td>{_e(r.get("name"))}</td>'
                 f'<td><span class="tag {tag}">{_e(r["k"])}</span></td>'
                 f'<td class="mut">{_e(r.get("wbs") or "—")}</td>'
                 f'<td>{_e(cv or "—")}</td></tr>')
    if not rows:
        rows = '<tr><td colspan="5" class="mut">None for this selection.</td></tr>'
    head = (f'<tr><th>Activity ID</th><th>Activity Name</th><th>Change</th>'
            f'<th>WBS</th><th>{_e(col_lbl)}</th></tr>')
    body = intro + chart + callout + '<div style="margin-top:8px"></div>' + _tbl(head, rows)
    return _card('Scope change', 'analysis by activity code', body)


def _sec_summary(report, filters=None):
    bl = report.get('bottom_line')
    banner = (f'<div class="bottomline"><b>Bottom line:</b> {_e(bl)}</div>' if bl else '')
    return (banner
            + _snapshot(report)
            + '<div class="split">' + _ledger(report) + _redflags(report) + '</div>'
            + _scope_analysis(report, filters))


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


def _crumb(name, wbs, aid):
    """A Critical-Path-Analyzer-style breadcrumb box: activity name, then the WBS path
    deepest→shallowest as '@ seg @ parent @ grandparent', then the Activity ID."""
    segs = [s.strip() for s in str(wbs or '').split(' > ') if s.strip()]
    segs = list(reversed(segs))
    bc = ' @ '.join(_e(s) for s in segs) if segs else '—'
    return (f'<div class="lnode"><div class="ln">{_e(name)}</div>'
            f'<div class="lb">@ {bc}</div>'
            f'<div class="lid">{_e(aid)}</div></div>')


def _logic_box(l):
    change = str(l.get('change') or '')
    low = change.lower()
    kind = 'added' if 'added' in low else 'removed' if 'removed' in low else 'changed'
    tag = 'add' if kind == 'added' else 'rem' if kind == 'removed' else 'chg'
    cp = '<span class="cpbadge">on critical path</span>' if l.get('on_cp') else ''
    lead = ' <span class="tag rem">lead</span>' if l.get('is_lead') else ''
    p = _crumb(l.get('pred_name'), l.get('pred_wbs'), l.get('pred_id'))
    s = _crumb(l.get('succ_name'), l.get('succ_wbs'), l.get('succ_id'))

    def arw(text, cls):
        return (f'<div class="larw {cls}"><span class="lt">{_e(text)}</span>'
                f'<span class="ar">→</span></div>')

    return (f'<div class="relhd"><span class="tag {tag}">{_e(change)}</span>{cp}{lead}</div>'
            f'<div class="rrow">Rev.00 — before</div>'
            f'<div class="lchain">{p}{arw(l.get("before"), "")}{s}</div>'
            f'<div class="rrow r1">Rev.01 — after</div>'
            f'<div class="lchain">{p}{arw(l.get("after"), kind)}{s}</div>')


def _logic_changes(report, filters):
    """Comment 2 — Logic & Sequence Changes as BIG side-by-side before→after boxes with the
    full WBS breadcrumb inside each. Group-by + activity-code filter reflect ``filters.logic``;
    the whole chart is wrapped in an overflow-x:auto container so the boxes never trim."""
    rows = report.get('logic_register') or []
    if not rows:
        return _card('Logic & sequence changes', 'grouped by activity code',
                     _muted('No relationship / logic changes on matched activities.'))
    dims = _dims_present((report.get('codes') or {}).get('dimensions'), rows)
    dim, val = _resolve_dim(filters, 'logic', dims)
    frows = [r for r in rows if val == 'All' or (dim and (r.get('codes') or {}).get(dim) == val)]
    if not frows:
        return _card('Logic & sequence changes',
                     f'grouped by {_e(dim)}' if dim else 'ungrouped',
                     _muted('No relationship changes for this filter.'))

    groups, order = {}, []
    for r in frows:
        g = ((r.get('codes') or {}).get(dim) if dim else None) or '(uncoded)'
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(r)

    sub = f'grouped by {_e(dim)}' if dim else 'ungrouped (no activity codes)'
    intro = ('<div class="sec">Every changed predecessor→successor link, drawn Rev.00 → Rev.01. '
             'Each box carries the full WBS breadcrumb (deepest → shallowest), like the '
             'Critical Path Analyzer. '
             + (f'Grouped by {_e(dim)}' if dim else 'Ungrouped')
             + (f'; showing <b>{_e(val)}</b>.' if val != 'All' else '; links on the critical path are badged.')
             + '</div>')
    inner = []
    for gi, g in enumerate(order):
        rs = groups[g]
        col = _series_color(gi)
        inner.append(f'<div class="grouphd" style="border-left-color:{col}">'
                     f'<span class="gsw" style="background:{col}"></span>{_e(g)}'
                     f'<span class="ct">{len(rs)} change{"s" if len(rs) != 1 else ""}</span></div>')
        inner.extend(_logic_box(r) for r in rs)
    body = intro + '<div class="chartwrap">' + ''.join(inner) + '</div>'
    return _card('Logic & sequence changes', sub, body)


def _sec_findings(report, filters=None):
    return _slip_bridge(report) + _logic_changes(report, filters)


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


def _sec_critical(report, filters=None):
    return _critpath(report) + '<div class="split">' + _float_bands(report) + _neg_float(report) + '</div>'


# ══ 4 · CHANGE REGISTER (DURATION ONLY) ════════════════════════════════════════

def _duration_analysis(report, filters, dim):
    """Comment 3 — a duration-change analysis chart: the average % duration change by activity
    code (matched activities only; added/removed carry no before → skipped)."""
    tbl = report.get('duration_table') or []
    matched = [r for r in tbl
               if isinstance(r.get('before'), (int, float)) and not isinstance(r.get('before'), bool)
               and isinstance(r.get('after'), (int, float)) and not isinstance(r.get('after'), bool)
               and r.get('before')]
    if not dim or not matched:
        return _muted('No numeric duration changes to analyse by code.')
    buckets, order = {}, []
    for r in matched:
        cv = (r.get('codes') or {}).get(dim) or '(uncoded)'
        if cv not in buckets:
            buckets[cv] = []
            order.append(cv)
        buckets[cv].append(abs((r['after'] - r['before']) / r['before'] * 100.0))
    items = []
    for i, cv in enumerate(order):
        vals = buckets[cv]
        avg = round(sum(vals) / len(vals)) if vals else 0
        items.append({'label': cv, 'vlabel': f'{avg}%', 'mag': avg, 'color': _series_color(i)})
    return (f'<div class="chartlab">AVG DURATION CHANGE (%) BY {_e(str(dim).upper())}</div>'
            + _bars_svg(items))


def _reg_duration(report, filters):
    """Comment 3 — duration changes only. No Calendar and no TF-After columns; the activity-code
    filter (``filters.duration``) actually filters the table; a duration-change analysis chart on top."""
    tbl = report.get('duration_table') or []
    if not tbl:
        return _card('Duration changed', 'working days · by activity code',
                     _muted('No activity duration changes.'))
    dims = _dims_present((report.get('codes') or {}).get('dimensions'), tbl)
    dim, val = _resolve_dim(filters, 'duration', dims)

    analysis = _card('Duration-change analysis', 'by activity code',
                     '<div class="sec">Average % duration change per code value'
                     + (f' — grouped by <b>{_e(dim)}</b>.' if dim else '.') + '</div>'
                     + _duration_analysis(report, filters, dim))

    def matches(r):
        return val == 'All' or (dim and (r.get('codes') or {}).get(dim) == val)

    rows = ''
    for r in tbl:
        if not matches(r):
            continue
        before, after, var = r.get('before'), r.get('after'), r.get('variance')
        b_txt = f'{_num(before)} d' if isinstance(before, (int, float)) and not isinstance(before, bool) else _e(before)
        a_txt = f'{_num(after)} d' if isinstance(after, (int, float)) and not isinstance(after, bool) else _e(after)
        if before == '—':
            var_cell, pct_cell = '<span class="tag add">Added</span>', '<span class="mut">—</span>'
        elif after == '—':
            var_cell, pct_cell = '<span class="tag rem">Removed</span>', '<span class="mut">—</span>'
        else:
            var_cell = _dcell(var, ' d')
            base = _money_num(before)
            if base and var is not None:
                p = round(var / base * 100)
                pcls = 'up' if p > 0 else 'down' if p < 0 else 'zero'
                pct_cell = f'<span class="d {pcls}">{"+" if p > 0 else ""}{p}%</span>'
            else:
                pct_cell = '<span class="mut">—</span>'
        rows += (f'<tr><td class="mono">{_e(r.get("id"))}</td><td>{_e(r.get("name"))}</td>'
                 f'<td class="mut">{_e(r.get("wbs") or "—")}</td>'
                 f'<td class="n">{b_txt}</td><td class="n new">{a_txt}</td>'
                 f'<td class="n">{var_cell}</td><td class="n">{pct_cell}</td></tr>')
    if not rows:
        rows = '<tr><td colspan="7" class="mut">None for this activity code.</td></tr>'
    head = ('<tr><th>Activity ID</th><th>Activity Name</th><th>WBS</th><th class="n">Before</th>'
            '<th class="n">After</th><th class="n">Variance</th><th class="n">% change</th></tr>')
    note = ''
    if val != 'All':
        note = f' · filtered to {val}'
    table = _card('Duration changed', f'working days{note}', _tbl(head, rows))
    return analysis + table


def _sec_register(report, filters=None):
    return _reg_duration(report, filters)


# ══ 5 · MILESTONES ═════════════════════════════════════════════════════════════

def _sec_ms(report, filters=None):
    """Comment 5 — milestone table with Activity ID + Type columns (they were missing)."""
    ms = [m for m in (report.get('milestones') or []) if m.get('kind') != 'unchanged']
    if not ms:
        return _card('Milestone changed', 'with Activity ID & Type', _muted('No milestone changes.'))
    tagcls = {'delayed': 'chg', 'advanced': 'add', 'new': 'add', 'removed': 'rem'}
    rows = ''
    for m in ms:
        kind = m.get('kind')
        if kind in ('new', 'removed'):
            var_cell = f'<span class="tag {tagcls.get(kind, "chg")}">{_e(kind.capitalize())}</span>'
        else:
            var_cell = _dcell(m.get('change_days'), ' d')
        rows += (f'<tr><td class="mono">{_e(m.get("id"))}</td><td>{_e(m.get("name"))}</td>'
                 f'<td>{_e(m.get("type") or "—")}</td>'
                 f'<td class="n">{_e(m.get("rev0") or "—")}</td>'
                 f'<td class="n new">{_e(m.get("rev1") or "—")}</td>'
                 f'<td class="n">{var_cell}</td></tr>')
    head = ('<tr><th>Activity ID</th><th>Activity Name</th><th>Type</th>'
            '<th class="n">Before</th><th class="n">After</th><th class="n">Variance</th></tr>')
    return _card('Milestone changed', 'with Activity ID & Type', _tbl(head, rows))


# ══ 6 · CALENDAR ═══════════════════════════════════════════════════════════════

_WW_RE = re.compile(r'(\d+)\s*-?\s*day\s*(?:→|->|to)\s*(\d+)\s*-?\s*day', re.I)


def _sec_cal(report, filters=None):
    """Comment 7 — Calendar as a before/after working-days-per-week bar chart per calendar
    (never a plain table). The Constraint table is not rendered (comment 6)."""
    cal = report.get('calendar_changes') or {}
    reass = cal.get('reassignments') or []
    defs = cal.get('calendars') or []
    if not reass and not defs:
        return _card('Working days per week', 'Rev.00 vs Rev.01 · per calendar',
                     _muted('No calendar reassignments or definition changes.'))

    # Assemble before/after days-per-week rows from reassignments (numeric) + workweek changes
    # parsed out of the calendar-definition detail strings.
    chart_rows, other_defs = [], []
    for g in reass:
        fw, tw = g.get('from_wd'), g.get('to_wd')
        if fw is not None and tw is not None:
            chart_rows.append({'name': f'{g.get("from")} → {g.get("to")}',
                               'b': fw, 'a': tw, 'count': g.get('count')})
    for d in defs:
        detail = d.get('detail') or ''
        m = _WW_RE.search(detail)
        if m and (d.get('change') in (None, 'modified')):
            chart_rows.append({'name': d.get('name'), 'b': int(m.group(1)),
                               'a': int(m.group(2)), 'count': None})
        else:
            other_defs.append(d)

    accel = any(r['a'] > r['b'] for r in chart_rows)
    mx = max([max(r['b'], r['a']) for r in chart_rows] + [7])

    if chart_rows:
        bars = ''
        for r in chart_rows:
            wb = round(r['b'] / mx * 55)
            wa = round(r['a'] / mx * 55)
            cnt = (f'<div class="sub2">{_num(r["count"])} activities</div>'
                   if r.get('count') is not None else '')
            delta = (f'<span class="d up">+{r["a"] - r["b"]} d/wk</span>' if r['a'] > r['b']
                     else f'<span class="d down">{r["a"] - r["b"]} d/wk</span>' if r['a'] < r['b']
                     else '<span class="mut">same</span>')
            bars += (f'<div class="calrow"><div class="cname">{_e(r["name"])}{cnt}</div>'
                     f'<div class="caltrack"><i class="cb" style="width:{wb}%">{r["b"]}d</i>'
                     f'<i class="ca" style="width:{wa}%">{r["a"]}d</i></div>'
                     f'<div class="v">{delta}</div></div>')
        legend = ('<div class="legend"><span><b class="sw-r0"></b>Rev.00 days/week</span>'
                  '<span><b class="sw-r1"></b>Rev.01 days/week</span></div>')
        intro = ('<div class="sec">A calendar switched to a longer working week shortens '
                 'durations on paper without changing the work — shown here as a before → after '
                 'working-days-per-week chart.</div>')
        chart = intro + bars + legend
    else:
        chart = _muted('No numeric working-week change to chart; see definition changes below.')

    extra = ''
    if other_defs:
        rows = ''
        for d in other_defs:
            rows += (f'<tr><td>{_e(d.get("name"))}</td><td>{_e(d.get("change"))}</td>'
                     f'<td class="mut">{_e(d.get("detail"))}</td></tr>')
        head = '<tr><th>Calendar</th><th>Change</th><th>Detail</th></tr>'
        extra = ('<div style="margin-top:10px"></div>'
                 + _card('Other calendar-definition changes', 'added / removed / hours / holidays',
                         _tbl(head, rows)))

    callout = ''
    if accel:
        callout = ('<div class="callout warn">One or more calendars moved to a longer working '
                   'week — a paper acceleration that shortens durations without adding work. '
                   'Confirm the basis.</div>')
    return _card('Working days per week', 'Rev.00 vs Rev.01 · per calendar', chart + callout) + extra


# ══ 7 · COST & RESOURCES ═══════════════════════════════════════════════════════

def _scurve_svg(report):
    c = report.get('curves') or {}
    months = c.get('months') or []
    vm = c.get('value_monthly') or []
    vc = c.get('value_cumulative') or []
    if not c.get('cost_available') or not months or not vm:
        return _muted('Neither revision carries cost loading — the planned-value chart is not applicable.')
    n = len(months)
    W, H = 860, 290
    left, right, top, bot = 52, 30, 30, 40
    plot_w = W - left - right
    plot_h = H - top - bot
    step = plot_w / max(n, 1)
    bw = min(14, step / 3)
    max_m = max([max(m.get('rev0', 0) or 0, m.get('rev1', 0) or 0) for m in vm] + [1])
    cum_mx = max([(x.get('rev0', 0) or 0) for x in vc] + [(x.get('rev1', 0) or 0) for x in vc] + [1])
    baseY = top + plot_h

    bars = []
    for i, m in enumerate(vm):
        x = left + i * step + step / 2
        v0, v1 = m.get('rev0', 0) or 0, m.get('rev1', 0) or 0
        h0 = v0 / max_m * plot_h
        h1 = v1 / max_m * plot_h
        bars.append(f'<rect x="{x - bw - 1:.1f}" y="{baseY - h0:.1f}" width="{bw:.1f}" height="{h0:.1f}" fill="var(--rpt-hair-strong)"/>')
        bars.append(f'<rect x="{x + 1:.1f}" y="{baseY - h1:.1f}" width="{bw:.1f}" height="{h1:.1f}" fill="var(--rpt-accent)" opacity="0.9"/>')
        # comment 8 — value label above the (revised) bar
        if v1:
            bars.append(f'<text x="{x + 1 + bw / 2:.1f}" y="{baseY - h1 - 4:.1f}" font-size="8" '
                        f'font-weight="700" fill="var(--rpt-ink-soft)" text-anchor="middle">{_e(_money_label(v1))}</text>')

    def line(mx, key, stroke, sw):
        if not vc:
            return ''
        pts = []
        for i, x in enumerate(vc):
            px = left + i * step + step / 2
            py = baseY - (x.get(key, 0) or 0) / mx * plot_h
            pts.append(f'{px:.1f},{py:.1f}')
        return f'<polyline points="{" ".join(pts)}" fill="none" stroke="{stroke}" stroke-width="{sw}"/>'

    orig_idx = None
    for i, m in enumerate(vm):
        if (m.get('rev0', 0) or 0) > 0:
            orig_idx = i
    orig_line = ''
    if orig_idx is not None:
        ox = left + orig_idx * step + step / 2
        orig_line = (f'<line x1="{ox:.1f}" y1="{top}" x2="{ox:.1f}" y2="{baseY}" stroke="var(--rpt-bad)" stroke-dasharray="4 3"/>'
                     f'<text x="{ox + 4:.1f}" y="{top + 12}" font-size="9" fill="var(--rpt-bad)">orig finish</text>')

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
    callout = (f'<div class="callout warn"><b>{_money(vao)} of planned value now falls after the original finish</b> — '
               'extended-works exposure (prolongation, prelims, plant hire).</div>' if vao else '')
    return '<div class="chartwrap">' + svg + '</div>' + legend + callout


def _money_moved(report, filters):
    """Comment 10 — 'Where the money moved': an activity-code selector (``filters.money.dim``)
    + a variance bar chart + the before/after/variance table, for the chosen dimension."""
    c = report.get('curves') or {}
    bd = c.get('budget_by_dim') or {}
    dims = [d for d in bd if bd.get(d)]
    if not dims:
        return _card('Where the money moved', 'by activity code', _muted('No budget breakdown available.'))
    dim, _ = _filt(filters, 'money')
    if dim not in dims:
        dim = dims[0]
    rows_data = bd.get(dim) or []
    items = []
    for i, r in enumerate(rows_data):
        var = r.get('var') or 0
        col = 'var(--rpt-accent)' if var >= 0 else 'var(--rpt-hair-strong)'
        items.append({'label': r.get('category'), 'vlabel': _money_label(var), 'mag': var, 'color': col})
    chart = (f'<div class="chartlab">BUDGET VARIANCE BY {_e(str(dim).upper())}</div>' + _bars_svg(items))
    rows = ''
    for r in rows_data:
        rows += (f'<tr><td>{_e(r.get("category"))}</td><td class="n">{_money(r.get("rev0"))}</td>'
                 f'<td class="n new">{_money(r.get("rev1"))}</td>'
                 f'<td class="n">{_money_delta(r.get("var"))}</td></tr>')
    head = f'<tr><th>{_e(dim)}</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th></tr>'
    body = ('<div class="sec">Planned budget total cost by activity code, Rev.00 → Rev.01.</div>'
            + chart + '<div style="margin-top:8px"></div>' + _tbl(head, rows))
    return _card('Where the money moved', f'by {_e(dim)}', body)


def _reg_cost(report):
    rc = report.get('resource_changes') or {}
    if not rc.get('cost_available'):
        return _card('Cost changed', 'budget total cost · variance',
                     _muted('Neither revision carries cost loading — reported as not applicable.'))
    cc = rc.get('activity_cost_changes') or []
    rows = ''
    for c in cc:
        delta = c.get('delta')
        base = _money_num(c.get('rev0'))
        var_cell = _money_delta(delta)
        pct = (f'{"+" if delta > 0 else ""}{round(delta / base * 100)}%'
               if base and delta is not None else '—')
        rows += (f'<tr><td class="mono">{_e(c.get("code"))}</td><td>{_e(c.get("name"))}</td>'
                 f'<td class="n">{_money(c.get("rev0"))}</td><td class="n new">{_money(c.get("rev1"))}</td>'
                 f'<td class="n">{var_cell}</td><td class="n mut">{_e(pct)}</td></tr>')
    tb = rc.get('total_budget') or {}
    d = tb.get('delta') or 0
    base = tb.get('rev0') or 0
    tpct = (f'{"+" if d > 0 else ""}{round(d / base * 100, 1)}%' if base else '—')
    rows += (f'<tr class="totrow"><td colspan="2">Total budget</td>'
             f'<td class="n">{_money(tb.get("rev0"))}</td><td class="n">{_money(tb.get("rev1"))}</td>'
             f'<td class="n">{_money_delta(d)}</td><td class="n">{_e(tpct)}</td></tr>')
    head = ('<tr><th>Activity ID</th><th>Activity Name</th><th class="n">Before</th><th class="n">After</th>'
            '<th class="n">Variance</th><th class="n">%</th></tr>')
    return _card('Cost changed', 'budget total cost · variance % · subtotals', _tbl(head, rows))


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


def _sec_cost(report, filters=None):
    scurve = _card('Planned value of work', 'monthly value (label above each bar) + cumulative curves',
                   _scurve_svg(report))
    return (scurve
            + _money_moved(report, filters)
            + _reg_cost(report)
            + _reg_resources(report))


# ══ 8 · MANPOWER ═══════════════════════════════════════════════════════════════

def _sec_manpower(report, filters=None):
    """Comment 11 — Manpower as a COMBO chart: monthly histogram STACKED by trade, the monthly
    TOTAL label above each bar, a total-headcount line, and a legend of the trades. Comment 12 —
    no tables below the histogram; the combo chart carries it."""
    c = report.get('curves') or {}
    months = c.get('months') or []
    trades = c.get('manpower_by_trade') or []
    if not months or not trades:
        return _card('Manpower', 'monthly histogram stacked by trade',
                     _muted('Neither revision carries resource units — manpower is not applicable.'))
    n = len(months)
    totals = [round(sum((t.get('monthly') or [0] * n)[i] if i < len(t.get('monthly') or []) else 0
                        for t in trades), 1) for i in range(n)]
    mx = max(totals + [1])
    W, H = 860, 290
    left, top, bot = 52, 30, 40
    plot_w, plot_h = W - left - 30, H - top - bot
    step = plot_w / max(n, 1)
    bw = min(40, step * 0.62)
    baseY = top + plot_h

    seg = ''
    for i in range(n):
        x = left + i * step + step / 2
        y = baseY
        for ti, t in enumerate(trades):
            monthly = t.get('monthly') or []
            v = monthly[i] if i < len(monthly) else 0
            sh = (v or 0) / mx * plot_h
            y -= sh
            if sh > 0:
                seg += (f'<rect x="{x - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{sh:.1f}" '
                        f'fill="{_series_color(ti)}"/>')
        # monthly total label above the stacked bar
        ty = baseY - totals[i] / mx * plot_h - 6
        seg += (f'<text x="{x:.1f}" y="{ty:.1f}" font-size="9" font-weight="800" '
                f'fill="var(--rpt-ink-soft)" text-anchor="middle">{_num(totals[i])}</text>')
        seg += (f'<text x="{x:.1f}" y="{baseY + 14:.1f}" font-size="8" fill="var(--rpt-muted)" '
                f'text-anchor="middle">{_e(months[i])}</text>')

    pts = ' '.join(f'{left + i * step + step / 2:.1f},{baseY - totals[i] / mx * plot_h:.1f}' for i in range(n))
    line = f'<polyline points="{pts}" fill="none" stroke="var(--rpt-bad)" stroke-width="2.4"/>'
    svg = (f'<div class="chartwrap"><svg viewBox="0 0 {W} {H}" style="width:100%;height:auto;min-width:640px">'
           f'<line x1="{left}" y1="{baseY}" x2="{W - 30}" y2="{baseY}" stroke="var(--rpt-chart-axis)"/>'
           f'{seg}{line}</svg></div>')
    legend = ('<div class="legend">'
              + ''.join(f'<span><b style="background:{_series_color(ti)}"></b>{_e(t.get("trade"))}</span>'
                        for ti, t in enumerate(trades))
              + '<span><b style="background:var(--rpt-bad)"></b>Total headcount</span></div>')
    peak_v = max(totals) if totals else 0
    peak_m = months[totals.index(peak_v)] if totals and peak_v else '—'
    by_trade = ' · '.join(f'{_e(t.get("trade"))} {_num(t.get("total"))}' for t in trades)
    callout = (f'<div class="callout">Peak monthly total <b>{_num(peak_v)}</b> in {_e(peak_m)}. '
               f'Planned man-hours by trade: {by_trade}.</div>')
    return _card('Manpower histogram — combo by trade',
                 'monthly total above each bar · line = total headcount',
                 svg + legend + callout)


# ══ 9 · SCOPE & STRUCTURE ══════════════════════════════════════════════════════

def _wbs_view(report):
    wv = report.get('wbs_view') or {}
    r0 = wv.get('rev0') or []
    r1 = wv.get('rev1') or []
    if not r0 and not r1:
        return _card('WBS comparison', 'Primavera colour-grouping', _muted('No WBS structure available.'))

    def bands(nodes):
        out = []
        for nd in nodes:
            lvl = min(int(nd.get('level', 0)), 3) + 1
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


def _sec_scope(report, filters=None):
    return _wbs_view(report) + _date_shifts(report)


# ── header + document ──────────────────────────────────────────────────────────

def _header(report, meta):
    r0, r1 = report.get('rev0') or {}, report.get('rev1') or {}
    date = (meta or {}).get('report_date', '')
    return f'''<div class="rh">
      <div><h1>Baseline Revision Comparison</h1>
        <div class="meta">Rev.00 <b>{_e(r0.get('file') or '—')}</b> &nbsp;→&nbsp; Rev.01 <b>{_e(r1.get('file') or '—')}</b></div></div>
      <div class="rhr"><div class="meta">Planning &amp; schedule review</div><div class="meta">{_e(date)}</div></div>
    </div>'''


# canonical section order: key, number, title, subtitle, builder(report, filters), page-break-before
_SECTIONS = [
    ('summary',  1, 'Executive Summary',      '', _sec_summary, False),
    ('findings', 2, 'Key Findings',           'what drove the slip + logic & sequence changes (WBS breadcrumbs) by activity code', _sec_findings, True),
    ('critical', 3, 'Critical Path & Float',  'driving chain, entered/left, float-band shift, negative float', _sec_critical, True),
    ('register', 4, 'Change Register',        'activity-duration changes only · code filter + duration-change analysis', _sec_register, True),
    ('ms',       5, 'Milestones',             'milestone moves with Activity ID & Type', _sec_ms, True),
    ('cal',      6, 'Calendar',               'working days per week, before → after per calendar', _sec_cal, True),
    ('cost',     7, 'Cost & Resources',       'planned-value curve, where the money moved, cost & resource changes', _sec_cost, True),
    ('manpower', 8, 'Manpower',               'monthly histogram stacked by trade with total-headcount line', _sec_manpower, True),
    ('scope',    9, 'Scope & Structure',      'WBS in Primavera colour-grouping + largest date shifts', _sec_scope, True),
]


def render_html(report, meta=None, sections=None, theme='light', filters=None):
    """Render the full nine-section report.

    ``sections`` gates which of the nine canonical keys are emitted:
      * ``None``  → all nine (default)
      * ``[]``    → header only (picker cleared everything)
      * a list of keys → only those, in canonical order.
    Each section is wrapped in ``<section data-sec="KEY">``.

    ``filters`` (optional) carries the planner's on-screen selections so the printed
    report renders the exact same filtered view::

        {scope:{dim,val}, logic:{dim,val}, duration:{dim,val}, money:{dim}}
    """
    keys = set(sections) if sections is not None else None
    body = [_header(report, meta)]
    for key, num, title, sub, builder, brk in _SECTIONS:
        if keys is not None and key not in keys:
            continue
        try:
            inner = builder(report, filters)
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
.sec { font-size: 11px; color: var(--rpt-muted); margin-bottom: 10px; } .sec b { color: var(--rpt-ink); }
.split { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; } .split .card { margin-bottom: 0; }
.bottomline { background: var(--rpt-accent-soft); border: 1px solid var(--rpt-accent); border-left: 5px solid var(--rpt-accent); border-radius: 10px; padding: 11px 14px; font-size: 12.5px; margin-bottom: 12px; color: var(--rpt-ink); }
.bottomline b { color: var(--rpt-accent); }
.chartwrap { overflow-x: auto; }
.chartlab { font-size: 11px; font-weight: 800; color: var(--rpt-muted); margin-bottom: 4px; letter-spacing: .03em; }
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
/* horizontal bars (scope legacy + slip bridge + float) */
.bar { display: grid; grid-template-columns: 130px 1fr 70px; gap: 9px; align-items: center; font-size: 11.5px; padding: 3px 0; }
.barl { color: var(--rpt-ink-soft); }
.track { background: var(--rpt-surface-2); border-radius: 5px; height: 15px; overflow: hidden; display: flex; }
.track .fa { background: var(--rpt-good); height: 100%; } .track .fr { background: var(--rpt-bad); height: 100%; }
.track .f-s1 { background: var(--rpt-series-1); height: 100%; } .track .f-s3 { background: var(--rpt-series-3); height: 100%; }
.track .f-s4 { background: var(--rpt-series-4); height: 100%; } .track .f-s5 { background: var(--rpt-series-5); height: 100%; }
.bar .v { text-align: right; font-weight: 700; }
.bridge { display: grid; grid-template-columns: 150px 1fr 78px; gap: 9px; align-items: center; font-size: 11.5px; padding: 4px 0; border-bottom: 1px dashed var(--rpt-hair); }
.bridge .brl { font-weight: 600; color: var(--rpt-ink-soft); } .bridge .v { text-align: right; font-weight: 700; }
.bridge.total { border-bottom: 0; border-top: 2px solid var(--rpt-edge); margin-top: 4px; padding-top: 6px; } .bridge.total .brl { color: var(--rpt-ink); font-weight: 800; }
/* float bands */
.fband { display: grid; grid-template-columns: 90px 1fr 1fr 74px; gap: 8px; align-items: center; font-size: 11px; padding: 3px 0; }
.fbl { font-weight: 600; } .fbtrack { background: var(--rpt-surface-2); border-radius: 5px; height: 12px; overflow: hidden; }
.fbtrack i { display: block; height: 100%; } .fbtrack .f0 { background: var(--rpt-hair-strong); } .fbtrack .f1 { background: var(--rpt-accent); }
.fband .v { text-align: right; font-weight: 700; }
/* calendar chart (comment 7) */
.calrow { display: grid; grid-template-columns: 170px 1fr 90px; gap: 9px; align-items: center; font-size: 11.5px; padding: 5px 0; border-bottom: 1px dashed var(--rpt-hair); }
.calrow:last-child { border-bottom: 0; }
.calrow .cname { font-weight: 600; color: var(--rpt-ink-soft); } .calrow .cname .sub2 { font-size: 10px; color: var(--rpt-muted); font-weight: 400; }
.caltrack { display: flex; gap: 6px; height: 22px; }
.caltrack i { display: flex; align-items: center; justify-content: flex-end; padding-right: 5px; border-radius: 4px; font-size: 10px; font-weight: 700; }
.caltrack .cb { background: var(--rpt-hair-strong); color: var(--rpt-ink); }
.caltrack .ca { background: var(--rpt-accent); color: var(--rpt-accent-ink); }
.calrow .v { text-align: right; font-weight: 700; }
/* legends + swatches */
.legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 10.5px; color: var(--rpt-muted); margin-top: 9px; }
.legend b { display: inline-block; width: 10px; height: 10px; border-radius: 3px; vertical-align: middle; margin-right: 4px; }
.sw-good { background: var(--rpt-good); } .sw-bad { background: var(--rpt-bad); } .sw-warn { background: var(--rpt-warn); }
.sw-muted { background: var(--rpt-muted); } .sw-r0 { background: var(--rpt-hair-strong); } .sw-r1 { background: var(--rpt-accent); }
.sw-l1 { background: var(--rpt-series-1); } .sw-l2 { background: var(--rpt-series-5); } .sw-l3 { background: var(--rpt-accent); } .sw-l4 { background: var(--rpt-series-4); }
.legend b.ol { background: transparent; }
.legend b.sw-good.ol { outline: 2px solid var(--rpt-good); } .legend b.sw-bad.ol { outline: 2px solid var(--rpt-bad); } .legend b.sw-warn.ol { outline: 2px solid var(--rpt-warn); }
/* callouts */
.callout { border-radius: 10px; padding: 9px 12px; font-size: 11px; background: var(--rpt-accent-soft); color: var(--rpt-ink); margin-top: 10px; }
.callout.warn { background: var(--rpt-warn-bg); color: var(--rpt-warn); }
/* chains (critical path) */
.chain { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 5px 0; }
.node { border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 4px 9px; font-size: 10.5px; font-weight: 600; background: var(--rpt-surface); }
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
/* logic & sequence changes — big WBS-breadcrumb boxes (comment 2) */
.grouphd { display: flex; align-items: center; gap: 8px; font-size: 11.5px; font-weight: 800; color: var(--rpt-ink); background: var(--rpt-surface-2); border: 1px solid var(--rpt-edge); border-left: 5px solid var(--rpt-accent); border-radius: 6px; padding: 6px 11px; margin: 12px 0 7px; page-break-after: avoid; }
.grouphd .gsw { width: 10px; height: 10px; border-radius: 3px; }
.grouphd .ct { margin-left: auto; font-weight: 700; background: var(--rpt-surface); color: var(--rpt-ink-soft); border-radius: 5px; padding: 1px 8px; font-size: 10px; }
.relhd { display: flex; align-items: center; gap: 8px; margin: 12px 0 2px; }
.cpbadge { font-size: 8.5px; font-weight: 800; color: var(--rpt-bad); background: var(--rpt-bad-bg); border: 1px solid var(--rpt-bad); border-radius: 5px; padding: 0 6px; }
.rrow { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; color: var(--rpt-muted); margin: 6px 0 2px; } .rrow.r1 { color: var(--rpt-accent); }
.lchain { display: flex; align-items: stretch; gap: 14px; flex-wrap: nowrap; margin: 4px 0; page-break-inside: avoid; }
.lnode { border: 2px solid var(--rpt-edge); border-radius: 12px; padding: 10px 14px; min-width: 210px; background: var(--rpt-surface); }
.lnode .ln { font-weight: 800; font-size: 13px; color: var(--rpt-ink); }
.lnode .lb { font-size: 11px; color: var(--rpt-accent); margin-top: 3px; font-weight: 600; word-break: break-word; }
.lnode .lid { font-size: 10px; color: var(--rpt-muted); margin-top: 2px; }
.larw { display: flex; flex-direction: column; justify-content: center; align-items: center; color: var(--rpt-muted); font-weight: 800; min-width: 74px; }
.larw .lt { font-size: 11px; background: var(--rpt-surface-2); border-radius: 5px; padding: 1px 7px; margin-bottom: 2px; white-space: nowrap; }
.larw .ar { font-size: 26px; line-height: 1; }
.larw.changed { color: var(--rpt-warn); } .larw.changed .lt { background: var(--rpt-warn-bg); }
.larw.added { color: var(--rpt-good); } .larw.added .lt { background: var(--rpt-good-bg); }
.larw.removed { color: var(--rpt-bad); } .larw.removed .lt { background: var(--rpt-bad-bg); }
/* WBS Primavera bands */
.p6band { display: flex; align-items: center; gap: 8px; padding: 6px 10px; font-weight: 700; color: var(--rpt-ink); background: var(--rpt-surface-2); border-left: 5px solid var(--rpt-series-1); border-radius: 4px; margin: 3px 0; font-size: 11.5px; }
.p6-l1 { border-left-color: var(--rpt-series-1); } .p6-l2 { border-left-color: var(--rpt-series-5); } .p6-l3 { border-left-color: var(--rpt-accent); } .p6-l4 { border-left-color: var(--rpt-series-4); }
.p6band.added { outline: 2px solid var(--rpt-good); } .p6band.removed { outline: 2px solid var(--rpt-bad); opacity: .8; text-decoration: line-through; } .p6band.moved { outline: 2px solid var(--rpt-warn); }
.p6badge { font-size: 8.5px; font-weight: 800; padding: 1px 6px; border-radius: 5px; background: var(--rpt-surface); color: var(--rpt-ink-soft); margin-left: auto; }
'''
