"""Consultant-grade report for the Baseline Revision Comparison (redesigned).

Renders the report dict (from ``compare.build_report_from_data``) into a single
professional document laid out as the TEN approved sections — Executive Summary,
Key Findings, Critical Path & Float, Change Register (Duration only), Milestones,
Calendar, Cost & Resources, Resource, Manpower and Scope & Structure. It matches
the approved concept ``mockups/baseline-revision-round7-concept.html`` in layout
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


def _month_label(date_str):
    """'19 Dec 2026' → 'Mon YYYY' ('Dec 2026') to index a finish date against the month axis;
    returns '' when it cannot be parsed. Mirrors the screen's monthLabel."""
    if not date_str:
        return ''
    parts = str(date_str).split()
    if len(parts) >= 3:
        return f'{parts[1]} {parts[2]}'
    return ''


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


def _filter_heading(dim, val=None):
    """The planner's current selection from the ONE activity-code control, printed as a static
    heading (comment 1). A specific value reads 'Activity code: <val>'; the default (All, or the
    money-moved chart which has no value picker) reads 'Breakdown by <dim>'. Tokens only."""
    if val not in (None, '', 'All'):
        inner = (f'<span class="fk">Activity code</span> '
                 f'<span class="fv">{_e(val)}</span>')
    else:
        inner = (f'<span class="fk">Breakdown</span> '
                 f'<span class="fv">by {_e(dim) if dim else "—"}</span>')
    return f'<div class="filterhead">{inner}</div>'


def _hbars(items):
    """HORIZONTAL bar chart used for every by-code chart (scope added / duration %-change /
    money variance). Each category name sits on its OWN line, right-aligned and truncated with a
    ``title`` tooltip; the value sits at the bar end. Category names can therefore never collide
    no matter how long or how many, and the value stays tied to its bar. Tokens only.

    ``items``: [{label, vlabel, mag (may be < 0), color}]. Bar width ∝ |mag| / max|mag|."""
    if not items:
        return ''
    mx = max([abs(it.get('mag') or 0) for it in items] + [1])
    rows = ''
    for it in items:
        mag = it.get('mag') or 0
        w = max(2.0, abs(mag) / mx * 100.0)
        col = it.get('color') or 'var(--rpt-accent)'
        name = _e(it.get('label', ''))
        vlabel = _e(it.get('vlabel', ''))
        # value inside the bar (right-aligned) when the bar is wide enough, else just past its end
        if w > 22:
            vstyle = f'left:calc({w:.1f}% - 6px);transform:translateX(-100%);color:var(--rpt-accent-ink)'
        else:
            vstyle = f'left:calc({w:.1f}% + 6px);color:var(--rpt-ink-soft)'
        rows += (f'<div class="hrow"><div class="hlbl" title="{name}">{name}</div>'
                 f'<div class="htrack"><div class="hfill" style="width:{w:.1f}%;background:{col}"></div>'
                 f'<div class="hval" style="{vstyle}">{vlabel}</div></div></div>')
    return f'<div class="hbars">{rows}</div>'


def _donut(items, note='', center='added'):
    """A compact inline-SVG donut of a share breakdown (used for % of ADDED activities, and the
    cost-variance share, by the selected activity-code dimension). ``items``: [{label, value,
    color}]; each slice is a fraction of the total, the ring centre shows the total count, and a
    legend lists each slice's percentage. ``center`` is the small label under the ring total.
    Tokens only; returns '' when there is nothing to show."""
    vals = [(it, max(float(it.get('value') or 0), 0.0)) for it in (items or [])]
    total = sum(v for _it, v in vals)
    if total <= 0:
        return ''
    import math
    R, sw, cx, cy = 44, 20, 60, 60
    circ = 2 * math.pi * R
    segs, off = [], 0.0
    for it, v in vals:
        if v <= 0:
            continue
        dash = (v / total) * circ
        col = it.get('color') or 'var(--rpt-accent)'
        segs.append(f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="{col}" '
                    f'stroke-width="{sw}" stroke-dasharray="{dash:.2f} {circ - dash:.2f}" '
                    f'stroke-dashoffset="{-off:.2f}" transform="rotate(-90 {cx} {cy})"/>')
        off += dash
    svg = (f'<svg viewBox="0 0 120 120" width="118" height="118" role="img">'
           + ''.join(segs)
           + f'<text x="{cx}" y="{cy - 1}" text-anchor="middle" font-size="21" font-weight="800" '
             f'fill="var(--rpt-ink)">{int(round(total))}</text>'
           + f'<text x="{cx}" y="{cy + 15}" text-anchor="middle" font-size="8" '
             f'fill="var(--rpt-muted)">{_e(center)}</text></svg>')
    leg = ''
    for it, v in vals:
        if v <= 0:
            continue
        pct = round(v / total * 100)
        name = _e(it.get('label', ''))
        leg += (f'<div class="dleg"><span class="dsw" style="background:{it.get("color") or "var(--rpt-accent)"}"></span>'
                f'<span class="dlbl" title="{name}">{name}</span>'
                f'<span class="dpct">{pct}%</span></div>')
    n = f'<div class="chartlab">{_e(note)}</div>' if note else ''
    return f'{n}<div class="donutwrap"><div class="donut">{svg}</div><div class="dlegs">{leg}</div></div>'


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
    # Change 1 — the selected activity-code value is carried once by the static selection heading
    # (_filter_heading) and the counts callout below; do not restate it here (no redundant listing).
    intro = ('<div class="sec">How many activities were added / removed, by activity code. '
             + (f'Grouped by <b>{_e(dim)}</b>.' if dim else 'No activity-code dimension available.')
             + '</div>')

    if dim:
        # Donut of the % of ADDED activities by the selected dimension, from codes.scope_by_code —
        # re-slices whenever the single Activity-Code selector changes the dimension.
        sbc = (codes.get('scope_by_code') or {}).get(dim) or []
        ditems = [{'label': r.get('category'), 'value': r.get('added') or 0, 'color': _series_color(i)}
                  for i, r in enumerate(sbc) if (r.get('added') or 0) > 0]
        donut = _donut(ditems, note=f'% OF ADDED ACTIVITIES BY {_e(str(dim).upper())}')
        vals = []
        for r in all_rows:
            cv = (r.get('codes') or {}).get(dim) or '(uncoded)'
            if cv not in vals:
                vals.append(cv)
        items = []
        for i, cv in enumerate(vals):
            cnt = sum(1 for r in added if ((r.get('codes') or {}).get(dim) or '(uncoded)') == cv)
            items.append({'label': cv, 'vlabel': _num(cnt), 'mag': cnt, 'color': _series_color(i)})
        chart = (donut
                 + f'<div class="chartlab">ADDED ACTIVITIES BY {_e(str(dim).upper())}</div>'
                 + _hbars(items))
    else:
        chart = _muted('No activity-code breakdown available for scope changes.')

    def matches(r):
        return val == 'All' or (dim and ((r.get('codes') or {}).get(dim)) == val)

    frows = [r for r in all_rows if matches(r)]
    n_add = sum(1 for r in frows if r['k'] == 'Added')
    n_rem = sum(1 for r in frows if r['k'] == 'Removed')
    callout = (f'<div class="callout">Showing <b>{_e(val)}</b>: <b>{n_add} added</b> · '
               f'<b>{n_rem} removed</b>.</div>')

    rows = ''
    for r in frows:
        tag = 'add' if r['k'] == 'Added' else 'rem'
        rows += (f'<tr><td class="mono">{_e(r.get("id"))}</td><td>{_e(r.get("name"))}</td>'
                 f'<td><span class="tag {tag}">{_e(r["k"])}</span></td>'
                 f'<td class="mut">{_e(r.get("wbs") or "—")}</td></tr>')
    if not rows:
        rows = '<tr><td colspan="4" class="mut">None for this selection.</td></tr>'
    head = ('<tr><th>Activity ID</th><th>Activity Name</th><th>Change</th>'
            '<th>WBS Path</th></tr>')
    body = (_filter_heading(dim, val) + intro + chart + callout
            + '<div style="margin-top:8px"></div>' + _tbl(head, rows))
    return _card('Scope change', 'analysis by activity code', body)


def _sec_summary(report, filters=None):
    bl = report.get('bottom_line')
    banner = (f'<div class="bottomline"><b>Bottom line:</b> {_e(bl)}</div>' if bl else '')
    return (banner
            + _snapshot(report)
            + '<div class="split">' + _ledger(report) + _redflags(report) + '</div>'
            + _scope_analysis(report, filters))


# ══ 2 · KEY FINDINGS ═══════════════════════════════════════════════════════════

def _slip_waterfall_svg(contrib, total):
    """The finish-slip waterfall as an SVG with the axis CENTRED on 0 (comment 3): up = delay,
    down = pull-in, with enough top/bottom padding that no bar or label is ever clipped even when
    steps go negative. Tokens only."""
    steps = [('Rev.00 finish', 0, 'axis')]
    for c in contrib:
        steps.append((str(c.get('cause') or ''), c.get('wd') or 0, 'cause'))
    steps.append(('Rev.01 finish', total or 0, 'total'))
    n = len(steps)
    W, H = 820, 236
    L, R, T, B = 34, 16, 30, 56
    pw, ph = W - L - R, H - T - B
    step = pw / max(n, 1)
    bw = min(56, step * 0.6)
    cum_total = sum(v for (_l, v, k) in steps if k == 'cause')
    mx_abs = max([abs(v) for (_l, v, k) in steps] + [abs(cum_total), 1])
    zeroY = T + ph / 2
    scale = (ph / 2 - 10) / mx_abs         # -10 leaves headroom for the value labels
    cum = 0.0
    parts = []
    for i, (lbl, v, k) in enumerate(steps):
        x = L + i * step + step / 2
        if k == 'axis':
            parts.append(f'<line x1="{x:.1f}" y1="{zeroY - 6:.1f}" x2="{x:.1f}" y2="{zeroY + 6:.1f}" '
                         f'stroke="var(--rpt-muted)"/>')
        elif k == 'total':
            y = zeroY - v * scale if v >= 0 else zeroY
            h = max(abs(v * scale), 2)
            parts.append(f'<rect x="{x - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                         f'fill="var(--rpt-bad)" opacity="0.85"/>')
            ty = (y - 6) if v >= 0 else (y + h + 12)
            parts.append(f'<text x="{x:.1f}" y="{ty:.1f}" font-size="10" font-weight="800" '
                         f'fill="var(--rpt-bad)" text-anchor="middle">{_e(_sgn(v))}</text>')
        else:
            col = _BRIDGE_COLORS[(i - 1) % len(_BRIDGE_COLORS)]
            y0 = zeroY - cum * scale
            cum += v
            y1 = zeroY - cum * scale
            y = min(y0, y1)
            h = max(abs(y1 - y0), 2)
            parts.append(f'<rect x="{x - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="{col}"/>')
            ty = (y if v >= 0 else y + h) - 6
            parts.append(f'<text x="{x:.1f}" y="{ty:.1f}" font-size="9.5" font-weight="700" '
                         f'fill="{col}" text-anchor="middle">{_e(_sgn(v))}</text>')
        short = (lbl[:15] + '…') if len(lbl) > 16 else lbl
        lyb = T + ph + 14
        parts.append(f'<text x="{x:.1f}" y="{lyb:.1f}" font-size="8.5" fill="var(--rpt-muted)" '
                     f'text-anchor="end" transform="rotate(-35 {x:.1f} {lyb:.1f})">{_e(short)}</text>')
    baseline = (f'<line x1="{L}" y1="{zeroY:.1f}" x2="{W - R}" y2="{zeroY:.1f}" '
                f'stroke="var(--rpt-hair-strong)"/>')
    return (f'<div class="chartwrap"><svg viewBox="0 0 {W} {H}" style="width:100%;height:auto;min-width:640px">'
            + baseline + ''.join(parts) + '</svg></div>')


def _slip_bridge(report):
    slip = report.get('slip') or {}
    contrib = slip.get('contributions') or []
    total = slip.get('total_wd')
    if not contrib:
        return _card('What drove the finish move', 'finish-slip waterfall · neutral attribution',
                     _muted('No finish-slip attribution available (finish unchanged or no driving-path change).'))
    chart = _slip_waterfall_svg(contrib, total)
    legend = ('<div class="legend"><span>Up = delay</span><span>Down = pull-in</span>'
              '<span><b class="sw-bad"></b>Net finish move</span></div>')
    howto = ('<div class="howto"><b>How to read it —</b> each step is a <b>cause</b>; its height is the '
             '<b>working days it added (up) or pulled in (down)</b>. The axis is centred on 0 so negative '
             'steps stay in view. The tool only <b>attributes</b> the move along the Rev.01 driving chain; '
             'it never says the change is wrong.</div>')
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
    return _card('What drove the finish move', 'finish-slip waterfall · neutral attribution',
                 chart + legend + howto + breakdown + foot)


def _crumb_txt(wbs, n=3):
    """A compact WBS breadcrumb '@ seg @ seg', deepest → shallowest, capped at ``n`` segments —
    the sub-label shown inside a Critical-Path-Analyzer lane node."""
    segs = [s.strip() for s in str(wbs or '').split(' > ') if s.strip()]
    segs = list(reversed(segs))[:n]
    return ' '.join('@ ' + _e(s) for s in segs) if segs else '—'


def _wbs_ctx(wbs):
    """A short branch context (below the project root) for a lane header, e.g. 'Silos Civil Works'."""
    segs = [s.strip() for s in str(wbs or '').split(' > ') if s.strip()]
    if not segs:
        return ''
    branch = segs[1:] if len(segs) > 1 else segs   # drop the root, keep the branch
    return ' · '.join(_e(s) for s in branch[:2])


def _cnode(name, wbs, aid, crit=False):
    """One activity node in a lane chain: name · WBS breadcrumb · Activity ID."""
    cls = 'cnode crit' if crit else 'cnode'
    nm = _e(name)
    return (f'<div class="{cls}"><div class="cn" title="{nm}">{nm}</div>'
            f'<div class="cw">{_crumb_txt(wbs)}</div>'
            f'<div class="cid">{_e(aid)}</div></div>')


def _clink2(label, cls, arrow):
    """The relationship-link widget inside a before/after chain: the link value (or a status
    word) stacked above its arrow. ``cls`` tints it (none / add / rem / chg); a removed link's
    arrow is '✕', an added link's before is a muted 'no link'."""
    return (f'<div class="clink2"><span class="clt {cls}">{_e(label)}</span>'
            f'<span class="ar2 {cls}">{arrow}</span></div>')


def _chain2(l, link_html):
    """One predecessor → link → successor chain row (the successor marked critical when the
    relationship is on the critical path). Each node carries its WBS breadcrumb inside."""
    p = _cnode(l.get('pred_name'), l.get('pred_wbs'), l.get('pred_id'), crit=False)
    s = _cnode(l.get('succ_name'), l.get('succ_wbs'), l.get('succ_id'), crit=bool(l.get('on_cp')))
    return f'<div class="chain2">{p}{link_html}{s}</div>'


def _logic_lane(l, idx, added_by_succ=None):
    """A single numbered lane for one changed relationship (change 2): a header (#N + change tag
    + on-CP / context) then the relationship as TWO chains — Rev.00 (before) and Rev.01 (after) —
    so the change reads as a direct comparison. Each node carries its WBS breadcrumb; a removed
    link's after reads 'link removed ✕', an added link's before reads 'not linked in Rev.00'
    (comment 1). For a removed link the replacement predecessor (if any) is spelled out. Mirrors
    the screen."""
    added_by_succ = added_by_succ or {}
    change = str(l.get('change') or '')
    low = change.lower()
    kind = 'added' if 'added' in low else 'removed' if 'removed' in low else 'changed'
    tagcls = 'add' if kind == 'added' else 'rem' if kind == 'removed' else 'chg'
    bits = []
    if l.get('on_cp'):
        bits.append('on critical path')
    if l.get('is_lead'):
        bits.append('lead')
    ctx = _wbs_ctx(l.get('succ_wbs') or l.get('pred_wbs'))
    if ctx:
        bits.append(ctx)
    sub = ' · '.join(bits)
    subhtml = f'<span class="lanesub">{sub}</span>' if sub else ''
    before_link = (_clink2('not linked in Rev.00', 'none', '⋯') if kind == 'added'
                   else _clink2(l.get('before'), '', '→'))
    after_link = (_clink2('link removed', 'rem', '✕') if kind == 'removed'
                  else _clink2(l.get('after'), 'add' if kind == 'added' else 'chg', '→'))
    # For a REMOVED link, clarify the replacement — any NEW predecessor the successor gained.
    repl_html = ''
    if kind == 'removed':
        repl = [a for a in added_by_succ.get(l.get('succ_id'), []) if a.get('pred_id') != l.get('pred_id')]
        if repl:
            names = ', '.join(f'<b>{_e(a.get("pred_name"))}</b> ({_e(a.get("after"))})' for a in repl)
            repl_html = f'<div class="lrepl">↳ {_e(l.get("succ_name"))} is now driven instead by {names}.</div>'
        else:
            repl_html = (f'<div class="lrepl mut">↳ {_e(l.get("succ_name"))} lost this predecessor with no '
                         f'replacement link added — it may now be an open end.</div>')
    return (f'<div class="lane"><div class="lanehdr">'
            f'<span class="lanenum">#{idx}</span>'
            f'<span class="lanetag {tagcls}">{_e(change)}</span>{subhtml}</div>'
            f'<div class="rev2lab">Rev.00 — before</div>{_chain2(l, before_link)}'
            f'<div class="rev2lab r1">Rev.01 — after</div>{_chain2(l, after_link)}{repl_html}</div>')


def _logic_changes(report, filters):
    """Change 2 — Logic & Sequence Changes: every changed predecessor → successor link as a
    numbered lane laid out in a 2-up grid (no overflow scroll), each shown as two chains —
    Rev.00 (before) and Rev.01 (after) — with the WBS breadcrumb inside every node. Mirrors the
    on-screen view exactly. The activity-code filter (``filters.logic``) selects which changes
    appear; the current selection prints as a static heading."""
    rows = report.get('logic_register') or []
    if not rows:
        return _card('Logic & sequence changes', 'before → after · by activity code',
                     _muted('No relationship / logic changes on matched activities.'))
    dims = _dims_present((report.get('codes') or {}).get('dimensions'), rows)
    dim, val = _resolve_dim(filters, 'logic', dims)
    frows = [r for r in rows if val == 'All' or (dim and (r.get('codes') or {}).get(dim) == val)]
    if not frows:
        return _card('Logic & sequence changes', 'before → after · by activity code',
                     _filter_heading(dim, val) + _muted('No relationship changes for this filter.'))
    intro = ('<div class="sec">Each changed predecessor → successor link shown twice — '
             'Rev.00 (before) and Rev.01 (after) — with the WBS breadcrumb inside every node, so '
             'the change reads as a direct comparison. Links on the critical path are marked; a '
             'removed link names the new predecessor that replaced it.</div>')
    # Map each successor to the NEW predecessor links it gained, so a removed link names its replacement.
    added_by_succ = {}
    for r in rows:
        if 'added' in str(r.get('change') or '').lower():
            added_by_succ.setdefault(r.get('succ_id'), []).append(r)
    lanes = ''.join(_logic_lane(r, i + 1, added_by_succ) for i, r in enumerate(frows))
    body = _filter_heading(dim, val) + intro + f'<div class="lanes">{lanes}</div>'
    return _card('Logic & sequence changes', 'before → after · by activity code', body)


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
            + _hbars(items))


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
        note_cell = '<span class="mut">—</span>'
        name_tag = ''
        if before == '—':
            # Change 3 — an added activity carries no Rev.00 duration to compare against; flag it
            # as new work in both the Name cell and the Note cell (mirrors the screen).
            var_cell, pct_cell = '<span class="tag add">Added</span>', '<span class="mut">—</span>'
            note_cell = '<span class="tag add">New activity</span>'
            name_tag = ' <span class="tag add">New activity</span>'
        elif after == '—':
            var_cell, pct_cell = '<span class="tag rem">Removed</span>', '<span class="mut">—</span>'
        else:
            var_cell = _dcell(var, ' d')
            # prefer the engine's own % (report.duration_table[].pct); fall back for older payloads
            ep = r.get('pct')
            if ep is None:
                base = _money_num(before)
                ep = round(var / base * 100) if base and var is not None else None
            if ep is not None:
                pcls = 'up' if ep > 0 else 'down' if ep < 0 else 'zero'
                pct_cell = f'<span class="d {pcls}">{"+" if ep > 0 else ""}{round(ep)}%</span>'
            else:
                pct_cell = '<span class="mut">—</span>'
            # comment C — flag a > ±200% swing for justification (neutral; never says it is wrong)
            if r.get('big_variance'):
                note_cell = ('<span class="tag warn">⚠ needs justification</span>'
                             '<div class="notehint">&gt; ±200% swing — usually the activity type / '
                             'relationship type changed; confirm the basis.</div>')
        rows += (f'<tr><td class="mono">{_e(r.get("id"))}</td><td>{_e(r.get("name"))}{name_tag}</td>'
                 f'<td class="mut">{_e(r.get("wbs") or "—")}</td>'
                 f'<td class="n">{b_txt}</td><td class="n new">{a_txt}</td>'
                 f'<td class="n">{var_cell}</td><td class="n">{pct_cell}</td>'
                 f'<td>{note_cell}</td></tr>')
    if not rows:
        rows = '<tr><td colspan="8" class="mut">None for this activity code.</td></tr>'
    head = ('<tr><th>Activity ID</th><th>Activity Name</th><th>WBS</th><th class="n">Before</th>'
            '<th class="n">After</th><th class="n">Variance</th><th class="n">% change</th>'
            '<th>Note</th></tr>')
    note = ''
    if val != 'All':
        note = f' · filtered to {val}'
    table = _card('Duration changed', f'working days{note}', _tbl(head, rows))
    return _filter_heading(dim, val) + analysis + table


def _sec_register(report, filters=None):
    return _reg_duration(report, filters)


# ══ 5 · MILESTONES ═════════════════════════════════════════════════════════════

def _sec_ms(report, filters=None):
    """Comment 4 — milestone table: Activity ID, Name, Before, After, Variance (the Type column
    was removed). A kind 'idchange' row is a milestone re-coded (id 'OLD → NEW', both dates); it is
    shown as a normal row with a neutral 'ID changed' tag plus its slip, if any."""
    ms = [m for m in (report.get('milestones') or []) if m.get('kind') != 'unchanged']
    if not ms:
        return _card('Milestone changed', 'moves by activity', _muted('No milestone changes.'))
    tagcls = {'delayed': 'chg', 'advanced': 'add', 'new': 'add', 'removed': 'rem'}
    rows = ''
    for m in ms:
        kind = m.get('kind')
        if kind == 'idchange':
            cd = m.get('change_days')
            slip = (' ' + _dcell(cd, ' d')) if isinstance(cd, (int, float)) and not isinstance(cd, bool) else ''
            var_cell = f'<span class="tag muted">ID changed</span>{slip}'
        elif kind in ('new', 'removed'):
            var_cell = f'<span class="tag {tagcls.get(kind, "chg")}">{_e(kind.capitalize())}</span>'
        else:
            var_cell = _dcell(m.get('change_days'), ' d')
        rows += (f'<tr><td class="mono">{_e(m.get("id"))}</td><td>{_e(m.get("name"))}</td>'
                 f'<td class="n">{_e(m.get("rev0") or "—")}</td>'
                 f'<td class="n new">{_e(m.get("rev1") or "—")}</td>'
                 f'<td class="n">{var_cell}</td></tr>')
    head = ('<tr><th>Activity ID</th><th>Activity Name</th>'
            '<th class="n">Before</th><th class="n">After</th><th class="n">Variance</th></tr>')
    return _card('Milestone changed', 'moves by activity', _tbl(head, rows))


# ══ 6 · CALENDAR ═══════════════════════════════════════════════════════════════

def _cal_pat_txt(p):
    """A plain working-pattern string 'N d/wk · H h/day · HPW h/wk' (comment 5)."""
    if not p:
        return '—'
    d, h, hpw = p.get('days'), p.get('hours'), p.get('hpw')
    return (f'{_num(d) if d is not None else "—"} d/wk · '
            f'{_num(h) if h is not None else "—"} h/day · '
            f'{_num(hpw) if hpw is not None else "—"} h/wk')


def _dow_grid_row(grid, changed_set, lab, r1=False):
    """One Mon→Sun working/non-working strip for a revision, changed days highlighted (comment 2)."""
    if not grid:
        return ''
    cells = ''
    for g in grid:
        st = 'on' if g.get('working') else 'off'
        chg = ' chg' if g.get('day') in changed_set else ''
        day = str(g.get('day') or '')
        cells += f'<span class="dow {st}{chg}">{_e(day[:1])}</span>'
    return f'<div class="dowrow"><span class="dowlab{" r1" if r1 else ""}">{_e(lab)}</span>{cells}</div>'


def _dow_grid_block(p):
    """The before/after day grid for one calendar pattern, with a changed-days note (comment 2)."""
    g0, g1 = p.get('rev0_grid'), p.get('rev1_grid')
    if not (g0 or g1):
        return ''
    changed = set(p.get('changed_days') or [])
    note = ''
    if changed:
        becomes_nw = any((not g.get('working')) and g.get('day') in changed for g in (g1 or []))
        note = (f'<div class="dowchg">Changed: <b>{_e(", ".join(changed))}</b> now '
                f'{"non-working" if becomes_nw else "working"}</div>')
    return (f'<div class="dowgrid">{_dow_grid_row(g0, changed, "Rev.00")}'
            f'{_dow_grid_row(g1, changed, "Rev.01", r1=True)}{note}</div>')


def _cal_narrative(patterns):
    """Comment 2 (round 11) — specific calendar DATES whose working status flipped between the
    revisions (e.g. 07 Jan 2026 non-working in Rev.00, working in Rev.01): a table of every changed
    date + a plain-language narrative. Empty string when no calendar has a date exception change."""
    rows = ''
    lines = []
    for p in patterns:
        ex = p.get('date_exceptions') or []
        if not ex:
            continue
        for e in ex:
            tagcls = 'add' if e.get('change') == 'now working' else 'rem'
            rows += (f'<tr><td>{_e(p.get("name"))}</td><td class="mono">{_e(e.get("date"))}</td>'
                     f'<td class="mut">{_e(e.get("rev0"))}</td><td class="new">{_e(e.get("rev1"))}</td>'
                     f'<td><span class="tag {tagcls}">{_e(e.get("change"))}</span></td></tr>')
        now_w = [e.get('date') for e in ex if e.get('change') == 'now working']
        now_n = [e.get('date') for e in ex if e.get('change') == 'now non-working']
        parts = []
        if now_w:
            parts.append(f'<b>{_e(", ".join(now_w))}</b> {"was non-working" if len(now_w) == 1 else "were non-working"} '
                         f'in Rev.00 and {"is now a working day" if len(now_w) == 1 else "are now working days"} in Rev.01')
        if now_n:
            parts.append(f'<b>{_e(", ".join(now_n))}</b> {"was a working day" if len(now_n) == 1 else "were working days"} '
                         f'in Rev.00 and {"is now non-working" if len(now_n) == 1 else "are now non-working"} in Rev.01')
        if parts:
            lines.append(f'In the <b>{_e(p.get("name"))}</b> calendar, {"; ".join(parts)}.')
    if not rows:
        return ''
    head = '<tr><th>Calendar</th><th>Date</th><th>Rev.00</th><th>Rev.01</th><th>Change</th></tr>'
    narr = ('<div class="callout"><b>Calendar date changes:</b><ul style="margin:6px 0 0;padding-left:18px">'
            + ''.join(f'<li>{l}</li>' for l in lines) + '</ul></div>')
    return ('<div class="sec" style="margin-top:12px"><b>Calendar exception dates</b> — specific dates that changed '
            'working status (Rev.00 → Rev.01)</div>' + _tbl(head, rows) + narr)


def _sec_cal(report, filters=None):
    """Comment 5 — Calendar presented clearly from ``calendar_changes.patterns``: one row per
    calendar (name · Rev.00 pattern · Rev.01 pattern · activities). The 24-hour-calendar 0-days
    bug is fixed in the engine. Keeps the reassignment summary/callout."""
    cal = report.get('calendar_changes') or {}
    patterns = cal.get('patterns') or []
    reass = cal.get('reassignments') or []
    if not patterns and not reass:
        return _card('Working pattern per calendar', 'Rev.00 → Rev.01 · per calendar',
                     _muted('No calendar reassignments or definition changes.'))

    intro = ('<div class="sec">Each calendar shown as a plain working pattern — days/week · '
             'hours/day · hours/week — before and after, plus a Mon→Sun working / non-working '
             'grid with any day whose state changed highlighted (comment 2). A 24-hour calendar '
             'reads 7 days.</div>')
    head = ('<div class="calrow calhd"><div>Calendar</div><div>Rev.00 pattern</div>'
            '<div>Rev.01 pattern</div><div class="ract">Activities</div></div>')
    rows = ''
    longer = []
    for p in patterns:
        r0, r1 = p.get('rev0'), p.get('rev1')
        chg = p.get('change')
        chg_lbl = (f'<span class="s"> · {_e(chg)}</span>' if chg and chg != 'unchanged' else '')
        row = (f'<div class="calrow"><div class="calname">{_e(p.get("name"))}{chg_lbl}</div>'
               f'<div><span class="pattern">{_cal_pat_txt(r0)}</span></div>'
               f'<div><span class="pattern r1">{_cal_pat_txt(r1)}</span></div>'
               f'<div class="ract">{_num(p.get("activities"))}</div></div>')
        rows += f'<div class="calblk">{row}{_dow_grid_block(p)}</div>'
        if r0 and r1 and (r1.get('hpw') or 0) > (r0.get('hpw') or 0):
            longer.append((p.get('name'), r0, r1, p.get('activities')))
    body = intro + head + rows + _cal_narrative(patterns)

    if reass:
        total_re = sum(g.get('count') or 0 for g in reass)
        top = reass[0]
        body += (f'<div class="callout"><b>{_num(total_re)} '
                 f'activit{"y" if total_re == 1 else "ies"}</b> reassigned across '
                 f'{len(reass)} calendar switch(es) — largest: {_e(top.get("from"))} → '
                 f'{_e(top.get("to"))} ({_num(top.get("count"))}).</div>')
    if longer:
        names = ', '.join(_e(n) for (n, *_r) in longer)
        body += ('<div class="callout warn">Longer working week on: ' + names
                 + ' — a paper acceleration that shortens durations without adding work. '
                   'Confirm the basis.</div>')
    return _card('Working pattern per calendar', 'Rev.00 → Rev.01 · per calendar', body)


# ══ 7 · COST & RESOURCES ═══════════════════════════════════════════════════════

def _scurve_svg(report):
    c = report.get('curves') or {}
    months = c.get('months') or []
    vm = c.get('value_monthly') or []
    vc = c.get('value_cumulative') or []
    if not c.get('cost_available') or not months or not vm:
        return _muted('Neither revision carries cost loading — the planned-value chart is not applicable.')
    n = len(months)
    W, H = 860, 300
    # comment 6a — extra top padding so the tallest bar's value label is never clipped; a wide
    # right margin (comment 3) leaves room for the Rev.01 completion label past the curve end so
    # it is never trimmed off screen.
    left, right, top, bot = 52, 112, 46, 56
    plot_w = W - left - right
    plot_h = H - top - bot
    step = plot_w / max(n, 1)
    bw = min(14, step / 3)
    # value labels thin out when columns crowd (so they never touch); MONTH labels are drawn
    # under EVERY bar (comment 6a), angled so they never run together
    thin = 2 if step < 34 else 1
    max_m = max([max(m.get('rev0', 0) or 0, m.get('rev1', 0) or 0) for m in vm] + [1])
    cum_mx = max([(x.get('rev0', 0) or 0) for x in vc] + [(x.get('rev1', 0) or 0) for x in vc] + [1])
    baseY = top + plot_h

    bars = []
    for i, m in enumerate(vm):
        x = left + i * step + step / 2
        v0, v1 = m.get('rev0', 0) or 0, m.get('rev1', 0) or 0
        # comment 3 — a non-zero month always draws a visible bar (min height) so the earliest
        # small months (the "first histogram not shown") are never invisible.
        h0 = max(2.0, v0 / max_m * plot_h) if v0 > 0 else 0.0
        h1 = max(2.0, v1 / max_m * plot_h) if v1 > 0 else 0.0
        bars.append(f'<rect x="{x - bw - 1:.1f}" y="{baseY - h0:.1f}" width="{bw:.1f}" height="{h0:.1f}" fill="var(--rpt-hair-strong)"/>')
        bars.append(f'<rect x="{x + 1:.1f}" y="{baseY - h1:.1f}" width="{bw:.1f}" height="{h1:.1f}" fill="var(--rpt-accent)" opacity="0.9"/>')
        # comment 3 — value label sits DIRECTLY above its own histogram bar (not lifted to the
        # cumulative curve); thinned so labels never touch. Top padding keeps it in frame.
        if v1 and i % thin == 0:
            bars.append(f'<text x="{x + 1 + bw / 2:.1f}" y="{baseY - h1 - 5:.1f}" font-size="8" '
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

    # comment 3 — the ORIGINAL (Rev.00) completion date, drawn at its month on the axis when it
    # falls within the value spread, labelled with the date so both finishes read clearly.
    r0fin = (report.get('rev0') or {}).get('finish')
    orig_line = ''
    o_idx = months.index(_month_label(r0fin)) if _month_label(r0fin) in months else None
    if o_idx is not None:
        ox = left + o_idx * step + step / 2
        orig_line = (f'<line x1="{ox:.1f}" y1="{top}" x2="{ox:.1f}" y2="{baseY}" stroke="var(--rpt-bad)" stroke-dasharray="4 3"/>'
                     f'<text x="{ox + 4:.1f}" y="{top + 12}" font-size="9" fill="var(--rpt-bad)">orig finish {_e(r0fin)}</text>')

    labels = ''
    for i in range(0, n):        # comment 6a — a month label under EVERY bar
        x = left + i * step + step / 2
        ly = baseY + 12
        labels += (f'<text x="{x:.1f}" y="{ly:.1f}" font-size="8" fill="var(--rpt-muted)" '
                   f'text-anchor="end" transform="rotate(-40 {x:.1f} {ly:.1f})">{_e(months[i])}</text>')

    # comment 3/5 — the Rev.01 completion date at the END of the cumulative curve, anchored to the
    # right (into the wide margin) so it is never trimmed.
    r1fin = (report.get('rev1') or {}).get('finish')
    finish_marker = ''
    if r1fin and vc:
        fx = left + (n - 1) * step + step / 2
        fy = baseY - (vc[-1].get('rev1', 0) or 0) / cum_mx * plot_h
        tx = fx + 8
        finish_marker = (f'<circle cx="{fx:.1f}" cy="{fy:.1f}" r="3.2" fill="var(--rpt-accent)"/>'
                         f'<text x="{tx:.1f}" y="{fy - 7:.1f}" font-size="9.5" font-weight="800" '
                         f'fill="var(--rpt-accent)" text-anchor="start">{_e(r1fin)}</text>'
                         f'<text x="{tx:.1f}" y="{fy + 5:.1f}" font-size="8" '
                         f'fill="var(--rpt-muted)" text-anchor="start">Rev.01 finish</text>')

    svg = (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto;min-width:640px">'
           f'<line x1="{left}" y1="{baseY}" x2="{W - right}" y2="{baseY}" stroke="var(--rpt-chart-axis)"/>'
           f'<line x1="{left}" y1="{top}" x2="{left}" y2="{baseY}" stroke="var(--rpt-chart-axis)"/>'
           + ''.join(bars)
           + line(cum_mx, 'rev0', 'var(--rpt-muted)', '2.2')
           + line(cum_mx, 'rev1', 'var(--rpt-accent)', '2.6')
           + orig_line + labels + finish_marker + '</svg>')
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
    chart = (f'<div class="chartlab">BUDGET VARIANCE BY {_e(str(dim).upper())}</div>' + _hbars(items))
    rows = ''
    for r in rows_data:
        rows += (f'<tr><td>{_e(r.get("category"))}</td><td class="n">{_money(r.get("rev0"))}</td>'
                 f'<td class="n new">{_money(r.get("rev1"))}</td>'
                 f'<td class="n">{_money_delta(r.get("var"))}</td></tr>')
    head = f'<tr><th>{_e(dim)}</th><th class="n">Before</th><th class="n">After</th><th class="n">Variance</th></tr>'
    body = (_filter_heading(dim) + '<div class="sec">Planned budget total cost by activity code, Rev.00 → Rev.01.</div>'
            + chart + '<div style="margin-top:8px"></div>' + _tbl(head, rows))
    return _card('Where the money moved', f'by {_e(dim)}', body)


def _cost_pie(cc, dim):
    """Comment 4 — share of the total cost variance by the selected activity-code dimension
    (|Δ| per code value), as a donut. Returns '' when the dimension has no coded changes."""
    if not dim:
        return ''
    by_val = {}
    for c in cc:
        v = (c.get('codes') or {}).get(dim)
        if v in (None, ''):
            continue
        by_val[v] = by_val.get(v, 0) + abs(c.get('delta') or 0)
    items = [{'label': k, 'value': v, 'color': _series_color(i)}
             for i, (k, v) in enumerate(sorted(by_val.items(), key=lambda kv: -kv[1])) if v > 0]
    if not items:
        return ''
    return _donut(items, note=f'COST VARIANCE BY {_e(str(dim).upper())} — SHARE OF THE TOTAL CHANGE',
                  center='Δ cost')


def _reg_cost(report, filters=None):
    rc = report.get('resource_changes') or {}
    if not rc.get('cost_available'):
        return _card('Cost changed', 'budget total cost · variance',
                     _muted('Neither revision carries cost loading — reported as not applicable.'))
    cc = rc.get('activity_cost_changes') or []
    # Comment 4 — activity-code filter: the selected dimension prints as a static heading and drives
    # the variance-share pie; a specific value narrows the table to that code.
    cdims = []
    for c in cc:
        for k in (c.get('codes') or {}):
            if k not in cdims:
                cdims.append(k)
    dim, val = _filt(filters, 'cost')
    if dim not in cdims:
        dim = cdims[0] if cdims else None
    shown = [c for c in cc if val in (None, '', 'All') or (dim and (c.get('codes') or {}).get(dim) == val)]
    rows = ''
    for c in shown:
        delta = c.get('delta')
        base = _money_num(c.get('rev0'))
        var_cell = _money_delta(delta)
        pct = (f'{"+" if delta > 0 else ""}{round(delta / base * 100)}%'
               if base and delta is not None else '—')
        rows += (f'<tr><td class="mono">{_e(c.get("code"))}</td><td>{_e(c.get("name"))}</td>'
                 f'<td class="n">{_money(c.get("rev0"))}</td><td class="n new">{_money(c.get("rev1"))}</td>'
                 f'<td class="n">{var_cell}</td><td class="n mut">{_e(pct)}</td></tr>')
    # Total row — the before/after variance across the SHOWN changed activities (comment 4). This
    # sums the itemised rows (matching the screen and the pie's Δ), NOT the whole-project budget.
    sum0 = sum(_money_num(c.get('rev0')) or 0 for c in shown)
    sum1 = sum(_money_num(c.get('rev1')) or 0 for c in shown)
    tot_label = 'Total — changed activities' if val in (None, '', 'All') else f'Total — {_e(val)}'
    d = sum1 - sum0
    tpct = (f'{"+" if d > 0 else ""}{round(d / sum0 * 100, 1)}%' if sum0 else '—')
    rows += (f'<tr class="totrow"><td colspan="2">{tot_label}</td>'
             f'<td class="n">{_money(sum0)}</td><td class="n">{_money(sum1)}</td>'
             f'<td class="n">{_money_delta(d)}</td><td class="n">{_e(tpct)}</td></tr>')
    head = ('<tr><th>Activity ID</th><th>Activity Name</th><th class="n">Before</th><th class="n">After</th>'
            '<th class="n">Variance</th><th class="n">%</th></tr>')
    pie = _cost_pie(cc, dim)
    body = _filter_heading(dim, val) + pie + _tbl(head, rows)
    return _card('Cost changed', 'budget total cost · variance % · filter · pie · total', body)


def _cost_reconciliation(report):
    """Comment 3 — where the rest of the budget sits: the changed-activity total is only part of
    the whole budget; account for every unit (Changed + Unchanged + New scope − Removed scope =
    Budget total) so the remaining budget is never unexplained."""
    recon = (report.get('resource_changes') or {}).get('cost_reconciliation') or []
    if not recon:
        return ''
    rows = ''
    for b in recon:
        is_tot = b.get('bucket') == 'total'
        cls = ' class="totrow"' if is_tot else ''
        name = f'<b>{_e(b.get("label"))}</b>' if is_tot else _e(b.get('label'))
        rows += (f'<tr{cls}><td>{name}</td><td class="mut">{_e(b.get("note"))}</td>'
                 f'<td class="n">{_money(b.get("rev0")) if b.get("rev0") else "—"}</td>'
                 f'<td class="n">{_money(b.get("rev1")) if b.get("rev1") else "—"}</td>'
                 f'<td class="n">{_money_delta(b.get("delta"))}</td></tr>')
    head = ('<tr><th>Bucket</th><th>What it is</th><th class="n">Rev.00</th><th class="n">Rev.01</th>'
            '<th class="n">Variance</th></tr>')
    intro = ('<div class="sec">The changed-activity total is only part of the whole budget — this '
             'accounts for every unit, so the remaining budget is never unexplained.</div>')
    return _card('Cost reconciliation', 'where the budget sits — changed vs the whole total',
                 intro + _tbl(head, rows))


_RES_TAG = {'added': ('add', 'Added'), 'removed': ('rem', 'Removed'),
            'increased': ('chg', 'Increased'), 'decreased': ('chg', 'Reduced'),
            'unchanged': ('muted', 'Unchanged')}


def _ba_bars(rows, fmt):
    """Before/after horizontal bars — Rev.00 over Rev.01 per resource, biggest movers first, with
    Added (green) / Removed (red) called out and the variance at the end (comments 5 & 6). ``rows``:
    [{name, rev0, rev1, kind}]. ``fmt``: value formatter."""
    if not rows:
        return ''
    mx = max([max(r.get('rev0', 0) or 0, r.get('rev1', 0) or 0) for r in rows] + [1])
    out = ''
    for r in rows:
        a, b = r.get('rev0', 0) or 0, r.get('rev1', 0) or 0
        v = b - a
        added, removed = (a == 0 and b > 0), (b == 0 and a > 0)
        wa = max(a / mx * 100, 2 if a > 0 else 0)
        wb = max(b / mx * 100, 2 if b > 0 else 0)
        b0cls = ' rem' if removed else ''
        b1cls = ' add' if added else ''
        vcls = 'up' if v >= 0 else 'down'
        out += (f'<div class="barow"><div class="balbl" title="{_e(r.get("name"))}">{_e(r.get("name"))}</div>'
                f'<div class="baw"><div class="babars">'
                f'<div class="baseg b0{b0cls}" style="width:{wa:.1f}%">{_e(fmt(a)) if a else ""}</div>'
                f'<div class="baseg b1{b1cls}" style="width:{wb:.1f}%">{_e(fmt(b)) if b else ""}</div></div>'
                f'<span class="bavar {vcls}">{"+" if v >= 0 else ""}{_e(fmt(v))}</span></div></div>')
    return f'<div class="babarlist">{out}</div>'


def _reg_resources(report):
    """Comments 5 & 6 — before vs after, at a glance: summary chips (added / removed / re-sized),
    a before/after bar per resource with Added/Removed highlighted, then an enhanced grouped table
    (id · type · units before/after · variance · activities · change). Mirrors the screen."""
    rc = report.get('resource_changes') or {}
    totals = rc.get('resource_totals') or []
    ac = rc.get('assignment_changes') or []
    if not totals and not ac:
        return _card('Resources — before vs after', 'compare each resource across the two revisions',
                     _muted('Neither revision carries resource loading — reported as not applicable.'))

    sm = rc.get('summary') or {}
    n_add = sm.get('res_added', sum(1 for t in totals if t.get('kind') == 'added'))
    n_rem = sm.get('res_removed', sum(1 for t in totals if t.get('kind') == 'removed'))
    n_chg = sm.get('res_resized', sum(1 for t in totals if t.get('kind') in ('increased', 'decreased')))
    chips = (f'<div class="rsum"><span class="rchip add">{n_add} added</span>'
             f'<span class="rchip rem">{n_rem} removed</span>'
             f'<span class="rchip chg">{n_chg} re-sized</span></div>')

    def _ufmt(x):
        return f'{int(round(x)):,}'
    bars = _ba_bars(totals, _ufmt)
    legend = ('<div class="legend"><span><b class="sw-r0"></b>Rev.00 units</span>'
              '<span><b class="sw-r1"></b>Rev.01 units</span>'
              '<span><b class="sw-good"></b>Added</span><span><b class="sw-bad"></b>Removed</span></div>')

    rows = ''
    for t in totals:
        v = t.get('var')
        if v is None:
            v = (t.get('rev1') or 0) - (t.get('rev0') or 0)
        tcls, tlbl = _RES_TAG.get(t.get('kind'), ('chg', str(t.get('kind') or 'Changed')))
        vcls = 'up' if v > 0 else 'down' if v < 0 else 'zero'
        rows += (f'<tr><td class="mono">{_e(t.get("id") or "—")}</td><td>{_e(t.get("name"))}</td>'
                 f'<td class="mut">{_e(t.get("type") or "—")}</td>'
                 f'<td class="n">{_ufmt(t.get("rev0")) if t.get("rev0") else "—"}</td>'
                 f'<td class="n new">{_ufmt(t.get("rev1")) if t.get("rev1") else "—"}</td>'
                 f'<td class="n"><span class="d {vcls}">{"+" if v > 0 else ""}{_ufmt(v)}</span></td>'
                 f'<td class="n mut">{int(t.get("activities") or 0)}</td>'
                 f'<td><span class="tag {tcls}">{_e(tlbl)}</span></td></tr>')
    head = ('<tr><th>Resource ID</th><th>Resource</th><th>Type</th><th class="n">Rev.00 (units)</th>'
            '<th class="n">Rev.01 (units)</th><th class="n">Variance</th><th class="n">Activities</th><th>Change</th></tr>')
    intro = ('<div class="sec">Every resource, Rev.00 vs Rev.01, sorted by the biggest change — '
             '<b style="color:var(--rpt-good)">Added</b> (new in Rev.01, 0 → N), '
             '<b style="color:var(--rpt-bad)">Removed</b> (gone in Rev.01, N → 0), and re-sized are all called out.</div>')
    body = intro + chips + (bars + legend if bars else '') + '<div style="margin-top:10px"></div>' + _tbl(head, rows)
    return _card('Resources — before vs after', 'summary · before/after bars · grouped table', body)


def _sec_cost(report, filters=None):
    """Change 6 — Cost & Resources keeps the planned-value curve, where-the-money-moved and the
    itemised activity-level Cost-changed table (returned here). The Resource-changed table now
    lives in its own 'resource' section; the by-WBS Cost Changes tab was removed."""
    scurve = _card('Planned value of work', 'monthly value (label above each bar) + cumulative curves',
                   _scurve_svg(report))
    return (scurve
            + _money_moved(report, filters)
            + _reg_cost(report, filters)
            + _cost_reconciliation(report))


# ══ 7b · RESOURCE ══════════════════════════════════════════════════════════════

def _sec_resource(report, filters=None):
    """Change 5 — the Resource-changed table on its own, moved out of Cost & Resources."""
    return _reg_resources(report)


# ══ 8 · MANPOWER ═══════════════════════════════════════════════════════════════

def _sec_manpower(report, filters=None):
    """Comment 4 (round 11) — Manpower on site per month as TWO-COLOUR grouped bars: Rev.00 (grey)
    vs Rev.01 (blue) side by side each month, with the difference (Rev.01 − Rev.00) labelled above
    each pair (no more busy stacked-trade colours). Plus peak-on-site KPIs and a resource-mix card."""
    c = report.get('curves') or {}
    months = c.get('months') or []
    if not months or not c.get('resource_available'):
        return _card('Manpower', 'people on site per month',
                     _muted('Neither revision carries resource units — manpower is not applicable.'))
    n = len(months)
    r0_by_month = {m.get('month'): (m.get('rev0') or 0) for m in (c.get('manpower_monthly') or [])}
    r1_by_month = {m.get('month'): (m.get('rev1') or 0) for m in (c.get('manpower_monthly') or [])}
    rev0tot = [r0_by_month.get(mo, 0) for mo in months]
    rev1tot = [r1_by_month.get(mo, 0) for mo in months]
    mx = max(rev0tot + rev1tot + [1])
    W, H = 860, 290
    left, top, bot = 52, 34, 52
    plot_w, plot_h = W - left - 30, H - top - bot
    step = plot_w / max(n, 1)
    bw = min(18, step * 0.30)
    baseY = top + plot_h
    thin = 2 if step < 34 else 1

    seg = ''
    for i in range(n):
        cx = left + i * step + step / 2
        h0 = rev0tot[i] / mx * plot_h
        h1 = rev1tot[i] / mx * plot_h
        x0, x1 = cx - bw - 2, cx + 2
        if h0 > 0:
            seg += f'<rect x="{x0:.1f}" y="{baseY - h0:.1f}" width="{bw:.1f}" height="{h0:.1f}" rx="2" fill="var(--rpt-hair-strong)"/>'
        if h1 > 0:
            seg += f'<rect x="{x1:.1f}" y="{baseY - h1:.1f}" width="{bw:.1f}" height="{h1:.1f}" rx="2" fill="var(--rpt-accent)"/>'
        d = int(round(rev1tot[i] - rev0tot[i]))
        if rev0tot[i] or rev1tot[i]:
            col = 'var(--rpt-bad)' if d > 0 else 'var(--rpt-good)' if d < 0 else 'var(--rpt-muted)'
            seg += (f'<text x="{cx:.1f}" y="{baseY - max(h0, h1) - 6:.1f}" font-size="9" font-weight="800" '
                    f'fill="{col}" text-anchor="middle">{"+" if d > 0 else ""}{d:,}</text>')
        if i % thin == 0:
            ly = baseY + 12
            seg += (f'<text x="{cx:.1f}" y="{ly:.1f}" font-size="8" fill="var(--rpt-muted)" '
                    f'text-anchor="end" transform="rotate(-40 {cx:.1f} {ly:.1f})">{_e(months[i])}</text>')

    svg = (f'<div class="chartwrap"><svg viewBox="0 0 {W} {H}" style="width:100%;height:auto;min-width:640px">'
           f'<line x1="{left}" y1="{baseY}" x2="{W - 30}" y2="{baseY}" stroke="var(--rpt-chart-axis)"/>'
           f'{seg}</svg></div>')
    legend = ('<div class="legend"><span><b class="sw-r0"></b>Rev.00 on site</span>'
              '<span><b class="sw-r1"></b>Rev.01 on site</span>'
              '<span style="color:var(--rpt-bad)">▲ more than Rev.00</span>'
              '<span style="color:var(--rpt-good)">▼ fewer than Rev.00</span></div>')

    # Peak-on-site KPIs + total man-hours change (comment 5).
    peak = c.get('peak') or {}
    mh = c.get('manhours_total') or {}
    pct = mh.get('pct')
    pct_txt = '—' if pct is None else f'{"+" if pct > 0 else ""}{pct:.1f}%'
    pct_cls = ' hot' if (pct or 0) > 0 else ''
    p0 = int(round(peak.get('rev0') or 0))
    p1 = int(round(peak.get('rev1') or 0))
    kpis = (
        '<div class="mpk">'
        f'<div class="mpkc"><div class="mpkk">Rev.00 peak on site</div><div class="mpkv">{p0:,}</div>'
        f'<div class="mpks">{_e("in " + peak.get("rev0_month")) if peak.get("rev0_month") else ""}</div></div>'
        f'<div class="mpkc"><div class="mpkk">Rev.01 peak on site</div><div class="mpkv{" hot" if p1 > p0 else ""}">{p1:,}</div>'
        f'<div class="mpks">{_e("in " + peak.get("rev1_month")) if peak.get("rev1_month") else ""}</div></div>'
        f'<div class="mpkc"><div class="mpkk">Total man-hours</div><div class="mpkv{pct_cls}">{pct_txt}</div>'
        f'<div class="mpks">Rev.00 → Rev.01</div></div></div>')
    note = ('<div class="sec">Each month shows Rev.00 (grey) and Rev.01 (blue) people on site side by '
            'side; the number above each pair is the difference (Rev.01 − Rev.00). "Peak on site" is '
            'the busiest month. The trade breakdown is the resource-mix chart below.</div>')
    chart_card = _card('Manpower on site per month',
                       'Rev.00 vs Rev.01 side by side · the difference labelled',
                       kpis + note + svg + legend)

    # Resource mix — total man-hours by trade, Rev.00 → Rev.01.
    mix = c.get('manhours_by_trade') or []
    mix_card = ''
    if mix:
        def _mhfmt(x):
            x = x or 0
            return f'{round(x / 1000)}k' if abs(x) >= 1000 else f'{int(round(x)):,}'
        mrows = [{'name': t.get('name') or t.get('resource_id'), 'rev0': t.get('rev0'),
                  'rev1': t.get('rev1'), 'kind': t.get('kind')} for t in mix]
        mbars = _ba_bars(mrows, _mhfmt)
        mlegend = ('<div class="legend"><span><b class="sw-r0"></b>Rev.00 man-hours</span>'
                   '<span><b class="sw-r1"></b>Rev.01 man-hours</span></div>')
        mix_card = _card('Resource mix — total man-hours by trade', 'Rev.00 → Rev.01',
                         '<div class="sec">The overall shift in the labour mix — which trades grew or '
                         'shrank between the two baselines.</div>' + mbars + mlegend)
    return chart_card + mix_card


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
    ('summary',  1,  'Executive Summary',      '', _sec_summary, False),
    ('findings', 2,  'Key Findings',           'what drove the slip + logic & sequence changes (CPA lanes) by activity code', _sec_findings, True),
    ('critical', 3,  'Critical Path & Float',  'driving chain, entered/left, float-band shift, negative float', _sec_critical, True),
    ('register', 4,  'Change Register',        'activity-duration changes only · code filter + duration-change analysis', _sec_register, True),
    ('ms',       5,  'Milestones',             'milestone moves by activity', _sec_ms, True),
    ('cal',      6,  'Calendar',               'working pattern per calendar, before → after', _sec_cal, True),
    ('cost',     7,  'Cost & Resources',       'planned-value curve, where the money moved, itemised cost changes', _sec_cost, True),
    ('resource', 8,  'Resource',               'resource assignment changes before → after', _sec_resource, True),
    ('manpower', 9,  'Manpower',               'monthly histogram stacked by trade with total-headcount line', _sec_manpower, True),
    ('scope',    10, 'Scope & Structure',      'WBS in Primavera colour-grouping + largest date shifts', _sec_scope, True),
]


def render_html(report, meta=None, sections=None, theme='light', filters=None):
    """Render the full ten-section report.

    ``sections`` gates which of the ten canonical keys are emitted:
      * ``None``  → all ten (default)
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
/* one-control selection heading (the on-screen Dimension ▾ / Activity code ▾ dropdowns, printed static) */
.filterhead { display: flex; flex-wrap: wrap; gap: 6px 20px; align-items: baseline; font-size: 11px; color: var(--rpt-muted); background: var(--rpt-surface-2); border: 1px solid var(--rpt-edge); border-radius: 9px; padding: 8px 12px; margin-bottom: 10px; }
.filterhead .fk { font-weight: 800; text-transform: uppercase; letter-spacing: .04em; }
.filterhead .fv { color: var(--rpt-ink); font-weight: 700; }
/* horizontal by-code bars — one name per line, value at bar end, no label collisions ever */
.hbars { display: flex; flex-direction: column; gap: 8px; margin-top: 2px; }
.hrow { display: grid; grid-template-columns: 210px 1fr; gap: 12px; align-items: center; }
.hlbl { font-size: 11.5px; font-weight: 600; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--rpt-ink-soft); }
.htrack { position: relative; background: var(--rpt-surface-2); border-radius: 6px; height: 24px; display: flex; align-items: center; }
.hfill { height: 100%; border-radius: 6px; min-width: 2px; }
.hval { position: absolute; font-size: 11.5px; font-weight: 800; white-space: nowrap; }
/* scope donut — % of added activities by the selected dimension (change 1) */
.donutwrap { display: flex; align-items: center; gap: 18px; margin: 4px 0 12px; flex-wrap: wrap; }
.donut { flex: 0 0 auto; }
.dlegs { display: flex; flex-direction: column; gap: 5px; min-width: 180px; }
.dleg { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--rpt-ink-soft); }
.dsw { width: 11px; height: 11px; border-radius: 3px; flex: 0 0 auto; }
.dlbl { flex: 1 1 auto; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dpct { font-weight: 800; color: var(--rpt-ink); }
.notehint { font-size: 10px; color: var(--rpt-muted); margin-top: 2px; }
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
/* calendar working-pattern rows (comment 5) — name · Rev.00 pattern · Rev.01 pattern · activities */
.calrow { display: grid; grid-template-columns: 180px 1fr 1fr 74px; gap: 12px; align-items: center; font-size: 11.5px; padding: 8px 0; border-top: 1px solid var(--rpt-hair); }
.calrow.calhd { border-top: 0; font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; color: var(--rpt-th-ink); }
.calrow .calname { font-weight: 700; color: var(--rpt-ink); } .calrow .calname .s { font-size: 10px; color: var(--rpt-muted); font-weight: 400; }
.calrow .ract { text-align: right; font-weight: 700; }
.pattern { display: inline-block; font-size: 11px; font-weight: 700; padding: 4px 9px; border-radius: 7px; background: var(--rpt-surface-2); color: var(--rpt-ink); }
.pattern.r1 { background: var(--rpt-accent-soft); color: var(--rpt-accent); }
/* calendar day grid (comment 2) — Mon→Sun working/non-working before/after, changed days ringed */
.calblk { page-break-inside: avoid; }
.dowgrid { padding: 2px 0 8px 192px; }
.dowrow { display: flex; align-items: center; gap: 5px; margin-top: 4px; }
.dowlab { font-size: 9px; font-weight: 800; color: var(--rpt-muted); width: 46px; text-transform: uppercase; }
.dowlab.r1 { color: var(--rpt-accent); }
.dow { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 21px; border-radius: 5px; font-size: 10px; font-weight: 700; border: 1px solid var(--rpt-edge); }
.dow.on { background: var(--rpt-accent-soft); color: var(--rpt-accent); }
.dow.off { background: var(--rpt-surface-2); color: var(--rpt-muted); }
.dow.chg { outline: 2px solid var(--rpt-warn); box-shadow: 0 0 0 1px var(--rpt-warn); }
.dowchg { font-size: 10.5px; color: var(--rpt-warn); margin-top: 5px; }
/* manpower KPIs (comment 5) */
.mpk { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 2px 0 10px; }
.mpkc { border: 1px solid var(--rpt-edge); border-radius: 10px; padding: 9px 11px; background: var(--rpt-surface); }
.mpkk { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; color: var(--rpt-muted); }
.mpkv { font-size: 20px; font-weight: 800; margin-top: 4px; line-height: 1; } .mpkv.hot { color: var(--rpt-bad); }
.mpks { font-size: 10px; color: var(--rpt-muted); margin-top: 4px; }
/* resource summary chips + before/after bars (comments 5 & 6) */
.rsum { display: flex; gap: 8px; flex-wrap: wrap; margin: 4px 0 10px; }
.rchip { font-size: 10px; font-weight: 700; padding: 3px 10px; border-radius: 999px; border: 1px solid var(--rpt-edge); color: var(--rpt-ink-soft); }
.rchip.add { background: var(--rpt-good-bg); color: var(--rpt-good); border-color: var(--rpt-good); }
.rchip.rem { background: var(--rpt-bad-bg); color: var(--rpt-bad); border-color: var(--rpt-bad); }
.rchip.chg { background: var(--rpt-warn-bg); color: var(--rpt-warn); border-color: var(--rpt-warn); }
.babarlist { display: flex; flex-direction: column; gap: 8px; margin-top: 2px; }
.barow { display: grid; grid-template-columns: 180px 1fr; gap: 12px; align-items: center; }
.balbl { font-size: 11px; font-weight: 600; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--rpt-ink-soft); }
.baw { display: flex; align-items: center; gap: 10px; }
.babars { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; }
.baseg { height: 14px; border-radius: 4px; min-width: 2px; display: flex; align-items: center; padding: 0 6px; font-size: 9px; font-weight: 800; color: #fff; box-sizing: border-box; white-space: nowrap; }
.baseg.b0 { background: var(--rpt-hair-strong); color: var(--rpt-ink-soft); }
.baseg.b1 { background: var(--rpt-accent); }
.baseg.b0.rem { background: var(--rpt-bad); color: #fff; }
.baseg.b1.add { background: var(--rpt-good); }
.bavar { font-size: 11px; font-weight: 800; white-space: nowrap; flex-shrink: 0; }
.bavar.up { color: var(--rpt-bad); } .bavar.down { color: var(--rpt-good); }
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
/* logic & sequence changes — grouping header + compact CPA lanes (comment 2) */
.grouphd { display: flex; align-items: center; gap: 8px; font-size: 11.5px; font-weight: 800; color: var(--rpt-ink); background: var(--rpt-surface-2); border: 1px solid var(--rpt-edge); border-left: 5px solid var(--rpt-accent); border-radius: 6px; padding: 6px 11px; margin: 12px 0 7px; page-break-after: avoid; }
.grouphd .gsw { width: 10px; height: 10px; border-radius: 3px; }
.grouphd .ct { margin-left: auto; font-weight: 700; background: var(--rpt-surface); color: var(--rpt-ink-soft); border-radius: 5px; padding: 1px 8px; font-size: 10px; }
.lane { border: 1px solid var(--rpt-edge); border-radius: 11px; padding: 10px 12px; margin-bottom: 9px; page-break-inside: avoid; }
.lanehdr { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; font-size: 12px; }
.lanetag { font-size: 9.5px; font-weight: 800; padding: 2px 8px; border-radius: 6px; }
.lanetag.add { background: var(--rpt-good-bg); color: var(--rpt-good); }
.lanetag.rem { background: var(--rpt-bad-bg); color: var(--rpt-bad); }
.lanetag.chg { background: var(--rpt-warn-bg); color: var(--rpt-warn); }
.lanesub { color: var(--rpt-muted); font-size: 11px; }
.lrepl { margin-top: 7px; font-size: 11px; color: var(--rpt-ink-soft); background: var(--rpt-surface-2); border-radius: 7px; padding: 5px 9px; }
.lrepl b { color: var(--rpt-ink); } .lrepl.mut { color: var(--rpt-muted); }
/* logic lane chain — one aligned row: fixed-width nodes, no wrap, long names truncate (change 2) */
.chain.lanechain { flex-wrap: nowrap; overflow-x: auto; align-items: center; }
.cnode { border: 1px solid var(--rpt-edge); border-radius: 9px; padding: 7px 12px; background: var(--rpt-surface); flex: 0 0 230px; width: 230px; max-width: 230px; overflow: hidden; }
.cnode.crit { border-color: var(--rpt-bad); background: var(--rpt-bad-bg); }
.cnode .cn { font-weight: 700; font-size: 12px; color: var(--rpt-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cnode .cw { font-size: 9.5px; color: var(--rpt-accent); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cnode .cid { font-size: 9px; color: var(--rpt-muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.clink { display: flex; flex: 0 0 auto; flex-direction: column; justify-content: center; align-items: center; padding: 0 10px; min-width: 64px; color: var(--rpt-muted); }
.clink .l0 { font-size: 9px; text-decoration: line-through; color: var(--rpt-bad); }
.clink .l1 { font-size: 10px; font-weight: 800; color: var(--rpt-warn); } .clink .l1.add { color: var(--rpt-good); }
.clink .ar { font-size: 20px; line-height: 1; } .clink .ar.rem { color: var(--rpt-bad); } .clink .ar.add { color: var(--rpt-good); }
/* cost change by WBS — indented colour-per-level bands (comment 6b) */
.cband { display: grid; grid-template-columns: 1fr 92px 92px 96px; gap: 8px; align-items: center; padding: 4px 0; font-size: 11.5px; }
.cband.cbhd { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; color: var(--rpt-th-ink); }
.cband .n { text-align: right; }
.cband .nm { font-weight: 700; color: var(--rpt-accent-ink); border-radius: 5px; padding: 4px 10px; }
.cb-l1 { background: var(--rpt-series-1); } .cb-l2 { background: var(--rpt-series-5); } .cb-l3 { background: var(--rpt-accent); } .cb-l4 { background: var(--rpt-series-4); }
/* WBS Primavera bands */
.p6band { display: flex; align-items: center; gap: 8px; padding: 6px 10px; font-weight: 700; color: var(--rpt-ink); background: var(--rpt-surface-2); border-left: 5px solid var(--rpt-series-1); border-radius: 4px; margin: 3px 0; font-size: 11.5px; }
.p6-l1 { border-left-color: var(--rpt-series-1); } .p6-l2 { border-left-color: var(--rpt-series-5); } .p6-l3 { border-left-color: var(--rpt-accent); } .p6-l4 { border-left-color: var(--rpt-series-4); }
.p6band.added { outline: 2px solid var(--rpt-good); } .p6band.removed { outline: 2px solid var(--rpt-bad); opacity: .8; text-decoration: line-through; } .p6band.moved { outline: 2px solid var(--rpt-warn); }
.p6badge { font-size: 8.5px; font-weight: 800; padding: 1px 6px; border-radius: 5px; background: var(--rpt-surface); color: var(--rpt-ink-soft); margin-left: auto; }
'''
