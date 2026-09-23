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
from datetime import date as _date
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


def _compact(n):
    """Compact whole-number chart label mirroring the screen's ``fmtCompact`` (round-16): a value is
    shown in full but short so it never trims or collides above a bar — 147000 → '147k',
    12400 → '12.4k', 1_200_000 → '1.2M'. Returns '' for None / non-numeric / non-finite."""
    try:
        v = float(n)
    except (TypeError, ValueError):
        return ''
    if v != v or v in (float('inf'), float('-inf')):   # NaN / ±inf guard
        return ''
    a = abs(v)
    s = '-' if v < 0 else ''
    if a >= 1e6:
        num = f'{a / 1e6:.0f}' if a >= 1e7 else f'{a / 1e6:.1f}'
        if num.endswith('.0'):
            num = num[:-2]
        return f'{s}{num}M'
    if a >= 1e3:
        num = f'{int(a / 1e3 + 0.5)}' if a >= 1e5 else f'{a / 1e3:.1f}'
        if num.endswith('.0'):
            num = num[:-2]
        return f'{s}{num}k'
    return f'{s}{int(a + 0.5)}'


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


def _mh(x):
    """Whole man-hours / units, thousands-separated. 0 stays '0' (never '—') — a man-hours figure
    of zero is real information, not missing data."""
    return f'{int(round(x or 0)):,}'


def _mhs(x):
    """Signed whole man-hours: '+N' / '−N' / '0' with a real minus glyph — used for the neutral
    difference-first manpower headline and deltas."""
    xi = int(round(x or 0))
    return ('+' if xi > 0 else '−' if xi < 0 else '') + f'{abs(xi):,}'


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
             f'fill="var(--rpt-ink)">{_e(_compact(total))}</text>'
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
    any_flip = False
    for p in patterns:
        ex = p.get('date_exceptions') or []
        if not ex:
            continue
        for e in ex:
            chg = str(e.get('change') or '')
            if chg == 'now working':
                cell = '<span class="tag add">now working</span>'
            elif chg == 'now non-working':
                cell = '<span class="tag rem">now non-working</span>'
            elif 'h →' in chg or 'h ->' in chg:      # "6h → 8h" reduced/restored hours
                cell = f'<span class="tag chg">{_e(chg)}</span>'
            else:
                cell = '<span class="mut">same</span>'
            rows += (f'<tr><td>{_e(p.get("name"))}</td><td class="mono">{_e(e.get("date"))}</td>'
                     f'<td class="mut">{_e(e.get("rev0"))}</td><td class="new">{_e(e.get("rev1"))}</td>'
                     f'<td>{cell}</td></tr>')
        now_w = [e.get('date') for e in ex if e.get('change') == 'now working']
        now_n = [e.get('date') for e in ex if e.get('change') == 'now non-working']
        hrs = [e for e in ex if 'h →' in str(e.get('change') or '')]
        if now_w or now_n or hrs:
            any_flip = True
        parts = []
        if now_w:
            parts.append(f'<b>{_e(", ".join(now_w))}</b> {"was non-working" if len(now_w) == 1 else "were non-working"} '
                         f'in Rev.00 and {"is now a working day" if len(now_w) == 1 else "are now working days"} in Rev.01')
        if now_n:
            parts.append(f'<b>{_e(", ".join(now_n))}</b> {"was a working day" if len(now_n) == 1 else "were working days"} '
                         f'in Rev.00 and {"is now non-working" if len(now_n) == 1 else "are now non-working"} in Rev.01')
        for e in hrs:
            parts.append(f'<b>{_e(e.get("date"))}</b> changed from {_e(e.get("rev0"))} to {_e(e.get("rev1"))}')
        if parts:
            lines.append(f'In the <b>{_e(p.get("name"))}</b> calendar, {"; ".join(parts)}.')
    # Per-revision non-working-date counts (parity with the screen summary).
    counts = []
    for p in patterns:
        nc = p.get('nonworking_count') or {}
        if nc.get('rev0') is not None or nc.get('rev1') is not None:
            counts.append(f'{_e(p.get("name"))}: {_num(nc.get("rev0") or 0)} non-working date(s) in Rev.00 · '
                          f'{_num(nc.get("rev1") or 0)} in Rev.01')
    count_txt = f' <span class="mut">({" · ".join(counts)})</span>' if counts else ''
    hdr = ('<div class="sec" style="margin-top:12px"><b>Calendar exception dates</b> — non-working days &amp; '
           f'reduced-hours days in either revision, changes highlighted (Rev.00 → Rev.01){count_txt}</div>')
    if not rows:
        # No specific exception dates, but the calendars were still compared — say so (parity with screen).
        if counts:
            return hdr + ('<div class="callout">Neither revision defines any specific non-working exception dates '
                          '(holidays) on its calendars — only the weekly working pattern applies.</div>')
        return ''
    head = '<tr><th>Calendar</th><th>Date</th><th>Rev.00</th><th>Rev.01</th><th>Change</th></tr>'
    if any_flip:
        narr = ('<div class="callout"><b>Calendar date changes:</b><ul style="margin:6px 0 0;padding-left:18px">'
                + ''.join(f'<li>{l}</li>' for l in lines) + '</ul></div>')
    else:
        narr = ('<div class="callout">The calendar exception dates (non-working days and reduced-hours days) are the '
                '<b>same</b> in both revisions — none was added, removed or re-houred.</div>')
    return hdr + _tbl(head, rows) + narr


def _cal_timeline_svg(flips):
    """A horizontal timeline strip marking WHERE in the project the changed calendar dates fall —
    green tick = became working, red = became non-working, amber = hours changed (a range for a
    multi-day span). Positions each change by its date within the span of the changes."""
    from datetime import date as _date

    def _p(iso):
        try:
            return _date.fromisoformat(iso)
        except Exception:
            return None
    pts = []
    for e in flips:
        s = _p(e.get('iso'))
        if s:
            pts.append((s, _p(e.get('iso_end') or e.get('iso')) or s, e.get('change')))
    if not pts:
        return ''
    lo = min(p[0] for p in pts)
    hi = max(p[1] for p in pts)
    span = (hi - lo).days or 1
    W, H = 700, 30

    def x(d):
        return 8 + (d - lo).days / span * (W - 16)
    ticks = ''
    for s, en, chg in pts:
        col = 'var(--rpt-good)' if chg == 'now working' else 'var(--rpt-bad)' if chg == 'now non-working' else 'var(--rpt-warn)'
        if en > s:
            ticks += f'<rect x="{x(s):.1f}" y="8" width="{max(3.0, x(en) - x(s)):.1f}" height="14" rx="2" fill="{col}" opacity="0.55"/>'
        else:
            ticks += f'<rect x="{x(s) - 2:.1f}" y="5" width="4" height="20" rx="2" fill="{col}"/>'
    return (f'<div class="caltl"><div class="caltllab"><span>{_e(lo.strftime("%b %Y"))}</span>'
            f'<span>{_e(hi.strftime("%b %Y"))}</span></div>'
            f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto"><rect x="0" y="4" width="{W}" height="22" '
            f'rx="5" fill="var(--rpt-surface-2)" stroke="var(--rpt-edge)"/>{ticks}</svg></div>')


def _cal_flip_days(e):
    """Actual number of DAYS an exception entry covers — a grouped range like '23–26 Mar' is one
    entry but four days (round-17 #01: the brief and digest must count days, not grouped entries).
    Mirrors the screen's calFlipDays: days between ``iso`` and ``iso_end`` inclusive, fallback 1."""
    iso = e.get('iso')
    iso_end = e.get('iso_end') or iso
    try:
        a = _date.fromisoformat(str(iso)[:10])
        b = _date.fromisoformat(str(iso_end)[:10])
    except (ValueError, TypeError):
        return 1
    if b < a:
        return 1
    return (b - a).days + 1


def _cal_sum_days(flips, pred):
    """Total DAYS across the flips matching ``pred`` — mirrors the screen's calSumDays."""
    return sum(_cal_flip_days(e) for e in flips if pred(e))


def _cal_assigned_pdf(p):
    """Which activities use a calendar, by activity code (round-17 #03, Option A) — one 100%-width
    PROPORTION BAR per dimension split by activity-code value (segment width = share of the
    calendar's activities), so the dominant trade reads at a glance; a legend under it carries each
    value's %. Replaces the flat chips. Mirrors the screen's calAssigned (a static PDF renders every
    dimension's bar stacked, with no interactive selector). Keeps the expandable activity-ID list."""
    a = p.get('assigned') or {}
    by_dim = a.get('by_dim') or {}
    if not a.get('count'):
        return ''
    rev = 'Rev.00' if p.get('assigned_rev') == 'rev0' else 'Rev.01'
    hdr = ('Activities that used it in Rev.00' if p.get('change') == 'removed'
           else 'Activities using it in Rev.01' if p.get('change') == 'added' else 'Assigned activities')
    # round-18 #01 — dimension picker as static PILLS (first active); a static PDF renders every
    # dimension's proportion bar stacked underneath, each labelled by its pill.
    dims = list(by_dim.keys())
    pills = ''.join(f'<span class="rc-dimtab{" on" if i == 0 else ""}">{_e(d)}</span>'
                    for i, d in enumerate(dims))
    pills = f'<div class="rc-dimtabs">{pills}</div>' if dims else ''
    rows = ''
    for dim, vals in by_dim.items():
        vals = vals or []
        tot = sum((x.get('count') or 0) for x in vals) or 1
        if vals:
            segs = ''
            leg = ''
            for i, x in enumerate(vals):
                w = (x.get('count') or 0) / tot * 100
                col = _series_color(i)   # same chart-token palette as the donut/pie
                seg_lbl = f'{_e(x.get("value"))} {_num(x.get("count"))}' if w >= 12 else ''
                segs += (f'<span class="acseg" style="width:{w:.2f}%;background:{col}" '
                         f'title="{_e(x.get("value"))}: {_num(x.get("count"))}">{seg_lbl}</span>')
                pct = int((x.get('count') or 0) / tot * 100 + 0.5)
                leg += (f'<span><i style="background:{col}"></i>{_e(x.get("value"))} {pct}%</span>')
            body = f'<div class="acbar">{segs}</div><div class="aclegend">{leg}</div>'
        else:
            body = '<span class="mut">no activity codes on these activities</span>'
        rows += f'<div class="acrow"><div class="acdimn">{_e(dim)}</div>{body}</div>'
    ids = a.get('ids') or []
    ids_html = ''
    if ids:
        shown = ' · '.join(_e(i) for i in ids[:40])
        more = f' · … ({_num(len(ids) - 40)} more)' if len(ids) > 40 else ''
        ids_html = f'<div class="acids"><span class="mut">Activity IDs:</span> <span class="idlist">{shown}{more}</span></div>'
    # round-18 #01 — the whole block is a distinct full-width PANEL at the bottom of the card.
    return (f'<div class="rc-assignpanel"><div class="rc-assignhead">'
            f'<span class="rc-assignt">{hdr} — by activity code</span>'
            f'<span class="rc-assigntot">{_num(a.get("count"))} activities in {rev}</span></div>'
            f'{pills}{rows}{ids_html}</div>')


def _fmtpat(p):
    """Compact working pattern 'N d/wk · H h/day · HPW h/wk' — only the parts present (mirrors the
    screen's fmtPattern). Returns '' when nothing is set."""
    if not p:
        return ''
    parts = []
    if p.get('days') is not None:
        parts.append(f'{_num(p.get("days"))} d/wk')
    if p.get('hours') is not None:
        parts.append(f'{_num(p.get("hours"))} h/day')
    if p.get('hpw') is not None:
        parts.append(f'{_num(p.get("hpw"))} h/wk')
    return ' · '.join(parts)


def _cal_brief(p, reass_from):
    """One plain-language BRIEF sentence per calendar (mirrors the screen's calBrief) — self-
    explaining for a planner who did not build the baseline, built entirely from the engine's
    counts. Neutral: it states what moved, never whether it is good or bad."""
    name = f'<b>{_e(p.get("name"))}</b>'
    acts = p.get('activities') or 0
    by_dim = (p.get('assigned') or {}).get('by_dim') or {}
    first_dim = next(iter(by_dim), None)
    top = (by_dim.get(first_dim) or [{}])[0] if first_dim else None
    used_by = ''
    if acts:
        mostly = f', mostly {_e(top.get("value"))}' if top and top.get('value') is not None else ''
        used_by = f' Used by {_num(acts)} activities{mostly}.'
    chg = p.get('change')
    if chg == 'removed':
        dest = sorted(reass_from.get(p.get('name'), []), key=lambda g: -(g.get('count') or 0))
        dest = dest[0] if dest else None
        tail = (f' The {_num(dest.get("count"))} activities that used it now run on <b>{_e(dest.get("to"))}</b>.'
                if dest else f' {_num(acts)} activities no longer carry this calendar.')
        return f'{name} — retired in Rev.01.{tail}'
    if chg == 'added':
        pat = _fmtpat(p.get('rev1'))
        r1 = p.get('rev1') or {}
        longer = (' A longer working week shortens those durations on paper.'
                  if (r1.get('hpw') is not None and (r1.get('hpw') or 0) >= 60) else '')
        return f'{name} — new{(" " + _e(pat)) if pat else ""} calendar, now used by {_num(acts)} activities.{longer}'
    flips = [e for e in (p.get('date_exceptions') or []) if e.get('change') != 'unchanged']
    # round-17 #01 — count DAYS, not grouped entries: a range like "23–26 Mar" is one entry but
    # four days. Mirrors the screen's calSumDays over calFlipDays.
    day_w = _cal_sum_days(flips, lambda e: e.get('change') == 'now working')
    day_n = _cal_sum_days(flips, lambda e: e.get('change') == 'now non-working')
    day_h = _cal_sum_days(flips, lambda e: not str(e.get('change') or '').startswith('now'))
    bits = []
    if day_w:
        bits.append(f'<span class="rc-hl-g">{day_w} day{"s" if day_w > 1 else ""} made working</span>')
    if day_n:
        bits.append(f'<span class="rc-hl-r">{day_n} day{"s" if day_n > 1 else ""} made non-working</span>')
    if day_h:
        bits.append(f'<span class="rc-hl-a">{day_h} day{"s" if day_h > 1 else ""} re-houred</span>')
    week_changed = _fmtpat(p.get('rev0')) != _fmtpat(p.get('rev1'))
    if bits:
        lead = (bits[0] if len(bits) == 1 else ', '.join(bits[:-1]) + ' and ' + bits[-1]) + '.'
        lead += ' Working week also changed.' if week_changed else ' Working week itself unchanged.'
    elif week_changed:
        lead = f'working week changed {_e(_fmtpat(p.get("rev0")) or "—")} &rarr; {_e(_fmtpat(p.get("rev1")) or "—")}.'
    else:
        lead = 'no material change to the working calendar.'
    return f'{name} — {lead}{used_by}'


def _cal_ledger(p):
    """The P6-shaped ledger — Attribute | Rev.00 | Rev.01 | Change (mirrors the screen's calLedger):
    fixed working-pattern rows, then ONLY the changed exception dates, then one collapse row that
    proves the identical dates were compared. Added / removed calendars carry no exception list
    (only-in-both), so those simply render the three working-pattern rows."""
    r0 = p.get('rev0') or {}
    r1 = p.get('rev1') or {}

    def cell(v, suf=''):
        return '—' if v is None else f'{_num(v)}{suf}'

    def wk_change(a, b):
        if a is None and b is None:
            return ''
        if a == b:
            return 'unchanged'
        if a is None:
            return 'added'
        if b is None:
            return 'removed'
        return 'changed'

    def wk_cls(c):
        return 'n' if c == 'unchanged' else 'r' if c == 'removed' else 'g' if c == 'added' else 'a'

    def wk_row(lbl, a, b, suf=''):
        c = wk_change(a, b)
        return (f'<tr><td class="rc-lattr">{lbl}</td><td class="rc-lrev">{cell(a, suf)}</td>'
                f'<td class="rc-lrev">{cell(b, suf)}</td>'
                f'<td class="rc-lchg rc-chg-{wk_cls(c)}">{c or "—"}</td></tr>')

    rows = (wk_row('Working days / week', r0.get('days'), r1.get('days'), ' d/wk')
            + wk_row('Hours / day', r0.get('hours'), r1.get('hours'), ' h')
            + wk_row('Hours / week', r0.get('hpw'), r1.get('hpw'), ' h'))
    excs = p.get('date_exceptions') or []
    flips = [e for e in excs if e.get('change') != 'unchanged']
    identical = sum(1 for e in excs if e.get('change') == 'unchanged')
    exc = ''
    if flips:
        exc += '<tr class="rc-lband"><td colspan="4">Exception dates — changed only</td></tr>'
        for e in flips:
            c = e.get('change')
            cls = 'g' if c == 'now working' else 'r' if c == 'now non-working' else 'a'
            # round-18 #02 — a day non-working in Rev.01 that wasn't in Rev.00 is a NEW non-working
            # day (red highlight + badge); a reduced-hours day/period is amber. Reduced = either
            # revision reads "(reduced)" OR the change is an hours change (Ah → Bh).
            is_new = c == 'now non-working'
            is_reduced = ('(reduced)' in (str(e.get('rev0')) + str(e.get('rev1')))
                          or (not str(c or '').startswith('now') and '→' in str(c or '')))
            hi = ' rc-hi-new' if is_new else ' rc-hi-red' if is_reduced else ''
            badge = (' <span class="rc-flag new">NEW</span>' if is_new
                     else ' <span class="rc-flag red">REDUCED</span>' if is_reduced else '')
            note = (('now working, reduced' if is_reduced else 'made working') if c == 'now working'
                    else 'new non-working' if c == 'now non-working'
                    else f'hours {_e(c)}') + badge
            exc += (f'<tr class="{hi.strip()}"><td class="rc-lattr"><span class="rc-dot {cls}"></span>{_e(e.get("date"))}</td>'
                    f'<td class="rc-lrev">{_e(e.get("rev0"))}</td><td class="rc-lrev">{_e(e.get("rev1"))}</td>'
                    f'<td class="rc-lchg rc-chg-{cls}">{note}</td></tr>')
    if identical:
        # round-16 #03b — one clear full-width line proving the identical dates were compared (mirrors
        # the screen's calLedger rc-lident row), with 'not listed' kept in the Change column.
        exc += (f'<tr class="rc-lident"><td colspan="3"><b>{_num(identical)} non-working '
                f'day{"s" if identical > 1 else ""}</b> {"are" if identical > 1 else "is"} '
                f'identical in both revisions — no change</td>'
                f'<td class="rc-lchg">not listed</td></tr>')
    return (f'<table class="rc-ldg"><thead><tr><th class="rc-lattr">Attribute</th>'
            f'<th class="rc-lrev">Rev.00</th><th class="rc-lrev">Rev.01</th>'
            f'<th class="rc-lchg">Change</th></tr></thead><tbody>{rows}{exc}</tbody></table>')


def _cal_nonworking_table(p):
    """Round-16 #03c — an ADDED (or removed) calendar has no other revision to diff against, so its
    own non-working days are listed in a TABLE (Date | Status) from the pattern's ``nonworking_dates``
    (list of {date, iso, status}) rather than only being implied by the weekly pattern. Mirrors the
    screen's ``calNonworkingTable`` so screen == PDF. Empty string for a modified/renamed calendar."""
    chg = p.get('change')
    if chg not in ('added', 'removed'):
        return ''
    nd = p.get('nonworking_dates') or []
    is_removed = chg == 'removed'
    # round-18 #02 — an ADDED calendar's non-working days are ALL new in Rev.01 (red band + NEW
    # badge); a REMOVED calendar's are gone with it in Rev.01 (muted band). Mirrors calNonworkingTable.
    band = 'rc-nwtbl rem' if is_removed else 'rc-nwtbl new'
    title = ('Non-working days it had in Rev.00 — gone with the calendar in Rev.01' if is_removed
             else 'New non-working days — all new in Rev.01 (no prior revision to compare)')
    badge = '' if is_removed else ' <span class="rc-flag new">NEW</span>'
    if not nd:
        return (f'<div class="{band}"><div class="rc-nwh">{_e(title)}{badge}</div>'
                '<div class="sec rc-mut" style="margin:4px 0 0">No dated non-working days — this '
                'calendar works every day in its weekly pattern (shown above).</div></div>')

    def _st_cls(d):
        if '(reduced)' in str(d.get('status') or ''):
            return 'rc-chg-a'
        return 'rc-mut' if is_removed else 'rc-chg-r'
    trows = ''.join(f'<tr><td class="rc-lattr">{_e(d.get("date"))}</td>'
                    f'<td class="rc-lchg {_st_cls(d)}">{_e(d.get("status"))}{" (removed)" if is_removed else ""}</td></tr>'
                    for d in nd)
    return (f'<div class="{band}"><div class="rc-nwh">{_e(title)}{badge}</div>'
            f'<table class="rc-ldg rc-nwld"><thead><tr><th class="rc-lattr">Date</th>'
            f'<th class="rc-lchg">Status</th></tr></thead><tbody>{trows}</tbody></table></div>')


def _sec_cal(report, filters=None):
    """Calendar — Option A (Brief + P6 ledger). A whole-section digest, then one block per CHANGED
    calendar: a plain-language brief (self-explaining for a planner who did not build the baseline),
    a P6-shaped Attribute|Rev.00|Rev.01|Change ledger (working pattern + only the changed exception
    dates + a collapse row), and the assigned activities by activity code. Unchanged calendars fold
    into a single line. Strictly neutral — change detected → potential impact → planning review,
    never a verdict. Mirrors the screen's calendarView so screen == PDF == Excel."""
    cal = report.get('calendar_changes') or {}
    patterns = cal.get('patterns') or []
    reass = cal.get('reassignments') or []
    if not patterns:
        return _card('Calendar', 'working pattern · exception dates · assigned activities by code',
                     _muted('No calendar definitions available for these revisions.'))
    reass_from = {}
    for g in reass:
        reass_from.setdefault(g.get('from'), []).append(g)
    tag = {'modified': ('chg', 'modified'), 'renamed': ('ren', 'renamed'),
           'added': ('add', 'added'), 'removed': ('rem', 'retired')}
    # round-16 #03a — an added OR removed calendar with 0 activities assigned has no schedule impact
    # and only adds noise for the planner, so it is dropped from the detailed cards AND the digest
    # counts; a single small note records how many were hidden (mirrors the screen's isEmptyZero /
    # emptyZero / dropNote).
    def _is_empty_zero(p):
        return p.get('change') in ('added', 'removed') and not ((p.get('activities') or 0) > 0)
    empty_zero = [p for p in patterns if _is_empty_zero(p)]
    changed = [p for p in patterns if p.get('change') != 'unchanged' and not _is_empty_zero(p)]
    unchanged = [p for p in patterns if p.get('change') == 'unchanged']

    # Section digest — the whole-section headline before any single calendar (counts exclude the
    # dropped empty added calendars, matching the detailed cards below).
    n_mod = sum(1 for p in changed if p.get('change') in ('modified', 'renamed'))
    n_add = sum(1 for p in changed if p.get('change') == 'added')
    n_rem = sum(1 for p in changed if p.get('change') == 'removed')
    # round-17 #01 — total DAYS changed across all calendars (a grouped range counts every day it
    # spans), not the number of grouped entries. Mirrors the screen's totDays / calSumDays.
    tot_days = sum(_cal_sum_days((p.get('date_exceptions') or []), lambda e: e.get('change') != 'unchanged')
                   for p in changed)
    legend = ('<span class="rc-callegend"><span><i class="g"></i>made working</span>'
              '<span><i class="r"></i>made non-working</span>'
              '<span><i class="a"></i>hours changed</span></span>')
    digest = (f'<div class="rc-caldigest"><span><b>{n_mod} modified · {n_add} added · {n_rem} retired '
              f'· {len(unchanged)} unchanged</b> — {tot_days} exception day'
              f'{"" if tot_days == 1 else "s"} changed.</span>{legend}</div>')
    drop_note = ''
    if empty_zero:
        ne = len(empty_zero)
        drop_note = (f'<div class="rc-caldrop">{_num(ne)} calendar{"s" if ne > 1 else ""} '
                     f'with <b>0 activities</b> assigned (added or retired) {"are" if ne > 1 else "is"} '
                     'not detailed — no schedule impact.</div>')

    paper_accel = False
    cards = ''
    for p in changed:
        chg = p.get('change')
        tagcls, taglbl = tag.get(chg, ('chg', chg or 'changed'))
        r0, r1 = p.get('rev0'), p.get('rev1')
        if (r0 and r1 and r0.get('hpw') is not None and r1.get('hpw') is not None
                and (r1.get('hpw') or 0) > (r0.get('hpw') or 0)):
            paper_accel = True
        name_html = (f'{_e(p.get("name"))} <span class="rc-mut">&rarr; {_e(p.get("renamed_to"))}</span>'
                     if chg == 'renamed' else _e(p.get('name')))
        meta = f'{_num(p.get("activities"))} activities' if p.get('activities') else ''
        ctx = ''
        if chg == 'removed':
            dest = sorted(reass_from.get(p.get('name'), []), key=lambda g: -(g.get('count') or 0))
            dest = dest[0] if dest else None
            moved = (f' The {_num(dest.get("count"))} activities that used it now use '
                     f'<b>{_e(dest.get("to"))}</b> — consolidated, no work left without a calendar.'
                     if dest else '')
            ctx = (f'<div class="rc-calctx">Retired in Rev.01.{moved} '
                   '<span class="rc-flag">Flagged for review.</span></div>')
        elif chg == 'added':
            r1d = r1 or {}
            longer = (' A longer working week shortens those durations on paper.'
                      if (r1d.get('hpw') is not None and (r1d.get('hpw') or 0) >= 60) else '')
            ctx = (f'<div class="rc-calctx">New in Rev.01 — now used by '
                   f'<b>{_num(p.get("activities") or 0)}</b> activities.{longer} '
                   '<span class="rc-flag">Flagged for review.</span></div>')
        cards += (f'<div class="rc-calcard">'
                  f'<div class="rc-calhead"><span class="rc-calname">{name_html}</span>'
                  f'<span class="rc-caltag {tagcls}">{_e(taglbl)}</span>'
                  f'<span class="rc-calmeta">{meta}</span></div>'
                  f'<div class="rc-calbrief">{_cal_brief(p, reass_from)}</div>'
                  f'{ctx}{_cal_ledger(p)}{_cal_nonworking_table(p)}{_cal_assigned_pdf(p)}</div>')

    unchanged_line = ''
    if unchanged:
        parts = []
        for p in unchanged:
            a = f' ({_num(p.get("activities"))})' if p.get('activities') else ''
            parts.append(f'{_e(p.get("name"))}{a}')
        unchanged_line = (f'<div class="rc-calunchanged"><b>{len(unchanged)} calendar'
                          f'{"s" if len(unchanged) > 1 else ""} unchanged</b> — {", ".join(parts)}. '
                          'Identical working pattern and non-working dates in both revisions.</div>')

    callout = ('<div class="callout warn">A calendar moved to a longer working week (more hours/week) '
               '— durations shorten <b>on paper</b> without changing the work. A paper acceleration to '
               'confirm.</div>') if paper_accel else ''
    return _card('Calendar', 'working pattern · exception dates · assigned activities by code',
                 digest + drop_note + cards + unchanged_line + callout)


def _scurve_svg(report):
    c = report.get('curves') or {}
    months = c.get('months') or []
    vm = c.get('value_monthly') or []
    vc = c.get('value_cumulative') or []
    if not c.get('cost_available') or not months or not vm:
        return _muted('Neither revision carries cost loading — the planned-value chart is not applicable.')
    n = len(months)
    by0 = {x.get('month'): (x.get('rev0') or 0) for x in vm}
    by1 = {x.get('month'): (x.get('rev1') or 0) for x in vm}
    rev0v = [by0.get(mo, 0) or 0 for mo in months]
    rev1v = [by1.get(mo, 0) or 0 for mo in months]
    cum_by = {x.get('month'): x for x in vc}
    # round-16 #02b — widen the per-month spacing (66px/month) so the month labels at the right end
    # never clash and the "Rev.01 finish" end label clears the last x-axis label. Mirrors the screen.
    W, H = max(760, n * 66), 300
    # round-16 #02a — extra top padding (top=58) so an angled value label off the tallest bar is
    # never clipped; a wide right margin (116) leaves room for the Rev.01 completion label past the
    # curve end so it is never trimmed off screen.
    left, right, top, baseY = 56, 116, 58, 250
    plot_w = W - left - right
    plot_h = baseY - top
    step = plot_w / max(n, 1)
    bw = min(13.0, step * 0.32)   # narrower — two grouped bars per month
    max_m = max(rev0v + rev1v + [1])
    cum_mx = max([(x.get('rev0', 0) or 0) for x in vc] + [(x.get('rev1', 0) or 0) for x in vc] + [1])

    bars = []
    for i, mo in enumerate(months):
        cx = left + (i + 0.5) * step
        v0, v1 = rev0v[i], rev1v[i]
        # BOTH the Rev.00 (before, grey) and Rev.01 (after, accent) monthly bars are drawn side by
        # side; a non-zero month keeps a min height so the earliest small months stay visible.
        h0 = max(3.0, v0 / max_m * plot_h) if v0 > 0 else 0.0
        h1 = max(3.0, v1 / max_m * plot_h) if v1 > 0 else 0.0
        x0, x1 = cx - bw - 1, cx + 1
        if h0 > 0:
            bars.append(f'<rect x="{x0:.1f}" y="{baseY - h0:.1f}" width="{bw:.1f}" height="{h0:.1f}" rx="2" fill="var(--rpt-hair-strong)"/>')
        if h1 > 0:
            bars.append(f'<rect x="{x1:.1f}" y="{baseY - h1:.1f}" width="{bw:.1f}" height="{h1:.1f}" rx="2" fill="var(--rpt-accent)" opacity="0.9"/>')
        # round-17 #04 — a compact value on BOTH bars (Rev.00 grey + Rev.01 blue), each angled up
        # off its OWN bar top so the two numbers never run into each other or get trimmed; the top
        # padding keeps the tallest label in frame. Compact money formatter so a big value never
        # overflows. Mirrors the screen's scurveSvg.
        if v0 > 0:
            ly0 = baseY - h0 - 5
            lx0 = x0 + bw / 2
            bars.append(f'<text x="{lx0:.1f}" y="{ly0:.1f}" font-size="8.5" font-weight="700" '
                        f'fill="var(--rpt-muted)" text-anchor="start" '
                        f'transform="rotate(-55 {lx0:.1f} {ly0:.1f})">{_e(_money_label(v0))}</text>')
        if v1 > 0:
            ly1 = baseY - h1 - 5
            lx1 = x1 + bw / 2
            bars.append(f'<text x="{lx1:.1f}" y="{ly1:.1f}" font-size="8.5" font-weight="700" '
                        f'fill="var(--rpt-accent)" text-anchor="start" '
                        f'transform="rotate(-55 {lx1:.1f} {ly1:.1f})">{_e(_money_label(v1))}</text>')

    def line(mx, key, stroke, sw):
        if not vc:
            return ''
        pts = []
        for i, mo in enumerate(months):
            px = left + (i + 0.5) * step
            val = (cum_by.get(mo) or {}).get(key, 0) or 0
            py = baseY - val / mx * plot_h
            pts.append(f'{px:.1f},{py:.1f}')
        return f'<polyline points="{" ".join(pts)}" fill="none" stroke="{stroke}" stroke-width="{sw}"/>'

    # The ORIGINAL (Rev.00) completion date, drawn at its month on the axis when it falls within the
    # value spread, labelled with the date so both finishes read clearly.
    r0fin = (report.get('rev0') or {}).get('finish')
    orig_line = ''
    o_idx = months.index(_month_label(r0fin)) if _month_label(r0fin) in months else None
    if o_idx is not None:
        ox = left + (o_idx + 1) * step
        orig_line = (f'<line x1="{ox:.1f}" y1="{top}" x2="{ox:.1f}" y2="{baseY}" stroke="var(--rpt-bad)" stroke-dasharray="4 3"/>'
                     f'<text x="{ox + 4:.1f}" y="{top + 12}" font-size="9" fill="var(--rpt-bad)">orig finish {_e(r0fin)}</text>')

    labels = ''
    for i in range(0, n):        # a month label under EVERY bar, angled so none is missing or clashes
        x = left + (i + 0.5) * step
        ly = baseY + 12
        labels += (f'<text x="{x:.1f}" y="{ly:.1f}" font-size="8.5" fill="var(--rpt-muted)" '
                   f'text-anchor="end" transform="rotate(-42 {x:.1f} {ly:.1f})">{_e(months[i])}</text>')

    # round-16 #02b — the Rev.01 completion date at the END of the cumulative curve, anchored to the
    # right (into the wide margin) so it is never trimmed and never collides with the last x-axis label.
    r1fin = (report.get('rev1') or {}).get('finish')
    finish_marker = ''
    if r1fin and vc:
        last_val = (cum_by.get(months[-1]) or {}).get('rev1', 0) or 0
        fx = left + (n - 1 + 0.5) * step
        fy = baseY - last_val / cum_mx * plot_h
        tx = fx + 8
        finish_marker = (f'<circle cx="{fx:.1f}" cy="{fy:.1f}" r="3.2" fill="var(--rpt-accent)"/>'
                         f'<text x="{tx:.1f}" y="{fy - 7:.1f}" font-size="10" font-weight="800" '
                         f'fill="var(--rpt-accent)" text-anchor="start">{_e(r1fin)}</text>'
                         f'<text x="{tx:.1f}" y="{fy + 5:.1f}" font-size="8" '
                         f'fill="var(--rpt-muted)" text-anchor="start">Rev.01 finish</text>')

    svg = (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto;min-width:{W}px">'
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
                  center='|Δ| cost')


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
                 f'<td class="n">{_money(c.get("rev0_num"))}</td><td class="n new">{_money(c.get("rev1_num"))}</td>'
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
    [{name, rev0, rev1, kind, code?}]. ``fmt``: value formatter.

    Round 14 — the value label is NEVER trimmed: it sits INSIDE the bar (right-aligned, light text)
    when the bar is wide enough (> ~26%), otherwise just PAST the bar end (dark text). Each bar
    carries a small Rev.00 / Rev.01 label to its left so a before/after pair never reads as
    duplicated work, and a row's ``code`` (the P6 resource id) prints as a muted sub-line under the
    resource name to disambiguate same-named resources."""
    if not rows:
        return ''
    mx = max([max(r.get('rev0', 0) or 0, r.get('rev1', 0) or 0) for r in rows] + [1])

    def _val(w, x, ink):
        # value inside the bar (right-aligned) when the bar is wide enough, else just past its end
        if w > 26:
            style = f'left:calc({w:.1f}% - 6px);transform:translateX(-100%);color:{ink}'
        else:
            style = f'left:calc({w:.1f}% + 6px);color:var(--rpt-ink-soft)'
        return f'<span class="bval" style="{style}">{_e(fmt(x)) if x else ""}</span>'

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
        code = r.get('code')
        code_html = f'<span class="bacode" title="{_e(code)}">{_e(code)}</span>' if code else ''
        out += (f'<div class="barow"><div class="balbl">'
                f'<span class="bnm" title="{_e(r.get("name"))}">{_e(r.get("name"))}</span>{code_html}</div>'
                f'<div class="baw"><div class="babars">'
                f'<div class="brow"><span class="blab">Rev.00</span><div class="btrack">'
                f'<div class="baseg b0{b0cls}" style="width:{wa:.1f}%"></div>'
                f'{_val(wa, a, "var(--rpt-ink-soft)")}</div></div>'
                f'<div class="brow"><span class="blab r1">Rev.01</span><div class="btrack">'
                f'<div class="baseg b1{b1cls}" style="width:{wb:.1f}%"></div>'
                f'{_val(wb, b, "var(--rpt-accent-ink)")}</div></div>'
                f'</div>'
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
    # Round 14 — carry each resource's P6 id as ``code`` so same-named resources (e.g. LAB-01 vs
    # LAB-07 "Steelfixers") are told apart in the before/after bars.
    bar_rows = [{'name': t.get('name'), 'rev0': t.get('rev0'), 'rev1': t.get('rev1'),
                 'kind': t.get('kind'), 'code': t.get('id')} for t in totals]
    bars = _ba_bars(bar_rows, _ufmt)
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

def _mp_other(other):
    """Equipment / material / untyped resources — reported honestly beside man-hours, NEVER summed
    into them (mirrors the screen's mpOtherResources). Each type carries its own unit of measure,
    so nothing is dropped from the comparison, but none of it belongs in a labour man-hours total.
    Renders even when labour resource loading is absent, as long as other resources exist."""
    label = {'equipment': ('Equipment', 'equipment-hours'),
             'material': ('Material', 'quantities (m³ / t / m²)'),
             'untyped': ('Untyped', 'units — no resource type in the P6 export')}
    boxes = ''
    for k, v in other.items():
        nm, unit = label.get(k, (k, 'units'))
        dv = v.get('var') if v.get('var') is not None else ((v.get('rev1') or 0) - (v.get('rev0') or 0))
        assigns = f' · {_mh(v.get("n1"))} assignments' if v.get('n1') else ''
        boxes += (f'<div class="rc-obox"><div class="rc-k">{_e(nm)}</div>'
                  f'<div class="rc-ov">{_mh(v.get("rev0"))} &rarr; {_mh(v.get("rev1"))}</div>'
                  f'<div class="rc-ou">{_e(unit)} · {_mhs(dv)}{assigns}</div></div>')
    mat_warn = ('<div class="rc-warn">Material quantities are shown as one figure because this export '
                "doesn't carry each resource's unit of measure — they can't be safely labelled per "
                'material (m³ vs t) or summed.</div>') if other.get('material') else ''
    untyped_warn = ''
    if other.get('untyped'):
        ut = other.get('untyped') or {}
        n_ut = ut.get('n1') or ut.get('n0') or 0
        untyped_warn = (f'<div class="rc-warn">{_mh(n_ut)} assignment(s) carry no resource type in the '
                        'P6 export — excluded from man-hours (never guessed as labour). Populate the P6 '
                        'resource dictionary to include them.</div>')
    body = ('<div class="sec">Equipment and material carry their own units of measure, so nothing is '
            'dropped from the comparison — but they do not belong in a man-hours total.</div>'
            f'<div class="rc-other">{boxes}</div>{mat_warn}{untyped_warn}')
    return _card('Other resources', 'reported separately · never added to man-hours', body)


def _sec_manpower(report, filters=None):
    """Manpower — difference-first, LABOUR-only (mirrors the screen's manpowerView). Man-hours = the
    sum of P6 Budgeted Labour Units; equipment-hours and material quantities carry their own units of
    measure and are reported separately, NEVER summed in. The section LEADS with the signed man-hours
    difference (Rev.01 − Rev.00); the two absolute totals are supporting context. Strictly neutral —
    directional colour only (blue for +, violet for −), never good/bad. So screen == PDF == Excel."""
    c = report.get('curves') or {}
    months = c.get('months') or []
    mix = c.get('manhours_by_trade') or []
    mt = c.get('manhours_total') or {}
    other = c.get('other_resources') or {}
    has_other = bool(other)

    if not c.get('resource_available') or not months:
        msg = ('Neither revision carries LABOUR resource loading — man-hours are reported as not '
               'applicable rather than "no change".')
        if has_other:
            msg += ' Equipment / material resources are listed below.'
        return (_card('Manpower', 'labour man-hours, before vs after', _muted(msg))
                + (_mp_other(other) if has_other else ''))

    # ── Hero: the man-hours DIFFERENCE (Rev.01 − Rev.00), labour only — the headline ──
    v0 = mt.get('rev0') or 0
    v1 = mt.get('rev1') or 0
    diff = mt.get('var') if mt.get('var') is not None else (v1 - v0)
    pct = mt.get('pct')
    dcls = 'up' if diff > 0 else 'down' if diff < 0 else 'zero'
    if v0 == 0 and v1 > 0:
        pct_txt = 'new'
    elif pct is None:
        pct_txt = '—'
    else:
        pct_txt = ('+' if pct > 0 else '') + f'{pct:.1f}%'
    if int(round(diff)) == 0:
        line = 'Rev.01 plans the <b>same</b> labour man-hours as Rev.00.'
    else:
        line = (f'Rev.01 plans <b>{_mh(abs(diff))} {"more" if diff > 0 else "fewer"}</b> labour '
                'man-hours than Rev.00 — change detected; review the trade and monthly breakdown below.')
    hero_body = (
        '<div class="rc-mp-herorow">'
        f'<div class="rc-mp-big {dcls}">{_mhs(diff)}'
        '<div class="rc-mp-biglbl">labour man-hours change</div></div>'
        '<div class="rc-mp-chips">'
        f'<div class="rc-mp-chip"><div class="rc-k">Labour · Rev.00</div>'
        f'<div class="rc-v soft">{_mh(v0)}</div></div>'
        '<div class="rc-mp-arrow">&rarr;</div>'
        f'<div class="rc-mp-chip"><div class="rc-k">Labour · Rev.01</div>'
        f'<div class="rc-v soft">{_mh(v1)}</div></div>'
        f'<div class="rc-mp-chip"><div class="rc-k">Change</div>'
        f'<div class="rc-v {dcls}">{_e(pct_txt)}</div></div>'
        '</div></div>'
        f'<div class="sec">{line}</div>'
        '<div class="rc-cap"><b>Man-hours = sum of P6 Budgeted Labor Units</b> (resource type = '
        'Labour). Equipment and material are reported separately below and are <b>not</b> in this '
        "number, so it ties to P6's Labor Units total for each revision.</div>")
    hero = _card('Labour man-hours — Rev.00 → Rev.01', 'the change is the headline', hero_body)

    # ── Monthly labour man-hours — Before & After grouped bars (round-16 #01) ──
    # Per month, a Rev.00 bar (grey) and a Rev.01 bar (accent) side by side, scaled to the max of all
    # monthly values, each carrying a COMPACT value label angled up off the bar top so adjacent labels
    # never overlap or clip; every month labelled on the x-axis. The variance lives in the hero above
    # and the by-trade chart below. Mirrors the screen's manpowerView monthly block (screen == PDF).
    mm = c.get('manpower_monthly') or []
    r0map = {m.get('month'): m.get('rev0') for m in mm}
    r1map = {m.get('month'): m.get('rev1') for m in mm}
    rev0v = [float(r0map.get(mo) or 0) for mo in months]
    rev1v = [float(r1map.get(mo) or 0) for mo in months]
    n = len(months)
    W = max(760, n * 58)
    H, L, Rp, T, B = 300, 40, 14, 48, 54
    ph = H - T - B
    mx = max(rev0v + rev1v + [1])
    step = (W - L - Rp) / n
    bw = min(16.0, step * 0.30)
    gap = 3.0

    def _mvlabel(cxb, val, hb, col):
        """A compact value label angled up-right (-55°) off the bar top so labels never overlap/clip."""
        if val <= 0:
            return ''
        ly = T + ph - hb - 5
        return (f'<text x="{cxb:.1f}" y="{ly:.1f}" font-size="9" font-weight="700" fill="{col}" '
                f'text-anchor="start" transform="rotate(-55 {cxb:.1f} {ly:.1f})">{_e(_compact(val))}</text>')

    s = f'<line x1="{L}" y1="{T + ph}" x2="{W - Rp}" y2="{T + ph}" stroke="var(--rpt-chart-axis)"/>'
    for i, mo in enumerate(months):
        cx = L + i * step + step / 2
        h0 = rev0v[i] / mx * ph
        h1 = rev1v[i] / mx * ph
        x0 = cx - bw - gap / 2
        x1 = cx + gap / 2
        if rev0v[i] > 0:
            s += (f'<rect x="{x0:.1f}" y="{T + ph - h0:.1f}" width="{bw:.1f}" '
                  f'height="{max(1.0, h0):.1f}" rx="2" fill="var(--rpt-hair-strong)"/>')
        if rev1v[i] > 0:
            s += (f'<rect x="{x1:.1f}" y="{T + ph - h1:.1f}" width="{bw:.1f}" '
                  f'height="{max(1.0, h1):.1f}" rx="2" fill="var(--rpt-accent)"/>')
        s += _mvlabel(x0 + bw / 2, rev0v[i], h0, 'var(--rpt-ink-soft)')
        s += _mvlabel(x1 + bw / 2, rev1v[i], h1, 'var(--rpt-accent)')
        ly = T + ph + 14
        s += (f'<text x="{cx:.1f}" y="{ly}" font-size="9" fill="var(--rpt-muted)" text-anchor="end" '
              f'transform="rotate(-40 {cx:.1f} {ly})">{_e(mo)}</text>')
    peak = c.get('peak') or {}
    peak_note = ''
    if peak.get('rev0') or peak.get('rev1'):
        m0, m1 = peak.get('rev0_month'), peak.get('rev1_month')
        peak_note = (f'<div class="sec" style="margin-top:2px">Peak labour: <b>{_mh(peak.get("rev0"))}</b> '
                     f'mh/month{(" in " + _e(m0)) if m0 else ""} (Rev.00) → <b>{_mh(peak.get("rev1"))}</b> '
                     f'mh/month{(" in " + _e(m1)) if m1 else ""} (Rev.01). Peak is man-hours per month, '
                     'not headcount.</div>')
    month_body = (
        '<div class="sec"><b>Rev.00 (grey)</b> and <b>Rev.01 (blue)</b> labour man-hours side by side, '
        'every month, with the value on each bar. The variance is the hero above and the by-trade chart below.</div>'
        + peak_note
        + f'<div class="chartwrap" style="overflow:visible"><svg viewBox="0 0 {W} {H}" '
          f'style="width:100%;height:auto" role="img" '
          f'aria-label="Monthly labour man-hours before and after">{s}</svg></div>'
        '<div class="legend"><span><b style="background:var(--rpt-hair-strong)"></b>Rev.00 (before)</span>'
        '<span><b style="background:var(--rpt-accent)"></b>Rev.01 (after)</span></div>')
    month_card = _card('Labour man-hours by month', 'Before & After — Rev.00 vs Rev.01, every bar labelled',
                       month_body)

    # ── Labour man-hours by trade — diverging delta bars (the change is drawn) + exact table ──
    trade_card = ''
    if mix:
        rows = []
        for t in mix:
            v = t.get('var') if t.get('var') is not None else ((t.get('rev1') or 0) - (t.get('rev0') or 0))
            rows.append({'name': t.get('name') or t.get('resource_id'),
                         'resource_id': t.get('resource_id'),
                         'rev0': t.get('rev0') or 0, 'rev1': t.get('rev1') or 0, 'v': v})
        rows.sort(key=lambda t: -abs(t['v']))
        tmx = max([abs(t['v']) for t in rows] + [1])
        bars = ''
        for t in rows:
            up = t['v'] > 0
            w = abs(t['v']) / tmx * 50.0
            fill = ('left:50%;background:var(--rpt-accent)' if up
                    else 'right:50%;background:var(--rpt-series-4)')
            vcls = 'up' if t['v'] > 0 else 'down' if t['v'] < 0 else 'zero'
            small = f'<small>{_e(t["resource_id"])}</small>' if t['resource_id'] else ''
            bars += (f'<div class="rc-trow"><div class="rc-tn">{_e(t["name"])}{small}</div>'
                     f'<div class="rc-tbar"><span class="rc-tmid"></span>'
                     f'<span class="rc-tfill" style="{fill};width:{w:.1f}%"></span></div>'
                     f'<div class="rc-tval {vcls}">{_mhs(t["v"])}</div></div>')
        trows = ''
        for t in rows:
            vcls = 'up' if t['v'] > 0 else 'down' if t['v'] < 0 else 'zero'
            trows += (f'<tr><td class="mono">{_e(t["resource_id"] or "—")}</td><td>{_e(t["name"])}</td>'
                      f'<td class="n mut">{_mh(t["rev0"])}</td><td class="n new">{_mh(t["rev1"])}</td>'
                      f'<td class="n"><span class="rc-d {vcls}">{_mhs(t["v"])}</span></td></tr>')
        thead = ('<tr><th>Resource ID</th><th>Resource</th><th class="n">Rev.00 (mh)</th>'
                 '<th class="n">Rev.01 (mh)</th><th class="n">Change</th></tr>')
        caption = (f'<div class="sec" style="margin-top:2px"><b>Per-trade man-hours — exact figures</b> '
                   f'<span>({len(rows)} labour resource{"" if len(rows) == 1 else "s"})</span></div>')
        trade_body = (
            '<div class="sec">One row per labour resource, biggest change first — the same P6 Resource '
            'Id you see in Primavera. The <b>change</b> is drawn; before/after are in the table below.</div>'
            f'<div class="rc-tdiv">{bars}</div>'
            '<div class="legend"><span><b style="background:var(--rpt-accent)"></b>increased</span>'
            '<span><b style="background:var(--rpt-series-4)"></b>decreased</span>'
            f'<span>net across all labour trades: <b>{_mhs(diff)} mh</b></span></div>'
            '<div style="margin-top:12px"></div>' + caption + _tbl(thead, trows))
        trade_card = _card('Labour man-hours by trade', 'which trades grew or shrank (Rev.01 − Rev.00)',
                           trade_body)

    return hero + month_card + trade_card + (_mp_other(other) if has_other else '')


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
    ('cal',      6,  'Calendar',               'working pattern · exception dates · assigned activities by code', _sec_cal, True),
    ('cost',     7,  'Cost & Resources',       'planned-value curve, where the money moved, itemised cost changes', _sec_cost, True),
    ('resource', 8,  'Resource',               'resource assignment changes before → after', _sec_resource, True),
    ('manpower', 9,  'Manpower',               'labour man-hours, before vs after', _sec_manpower, True),
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
/* round-14 calendar cards */
.calcard2 { border: 1px solid var(--rpt-edge); border-radius: 11px; padding: 11px 13px; margin-bottom: 10px; page-break-inside: avoid; }
.calhd2 { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; margin-bottom: 3px; }
.calnm { font-size: 13.5px; font-weight: 800; color: var(--rpt-ink); }
.calmeta { font-size: 10.5px; color: var(--rpt-muted); margin-left: auto; }
.caltag { font-size: 8.5px; font-weight: 800; padding: 2px 8px; border-radius: 6px; }
.caltag.chg { background: var(--rpt-warn-bg); color: var(--rpt-warn); }
.caltag.add { background: var(--rpt-good-bg); color: var(--rpt-good); }
.caltag.rem { background: var(--rpt-bad-bg); color: var(--rpt-bad); }
.caltag.ren { background: var(--rpt-accent-soft); color: var(--rpt-accent); }
.caltag.none { background: var(--rpt-surface-2); color: var(--rpt-muted); }
.calplain { font-size: 12px; color: var(--rpt-ink-soft); }
.patrow { display: flex; gap: 8px; align-items: baseline; font-size: 11.5px; margin: 5px 0 2px; flex-wrap: wrap; }
.patrow .pk { font-size: 9px; text-transform: uppercase; letter-spacing: .03em; font-weight: 800; color: var(--rpt-muted); }
.patrow .pr0 { color: var(--rpt-ink-soft); } .patrow .pr1 { color: var(--rpt-accent); font-weight: 700; } .patrow .par { color: var(--rpt-muted); }
.calctx { font-size: 12px; color: var(--rpt-ink-soft); margin: 5px 0; } .calctx b { color: var(--rpt-ink); }
.caltl { margin: 9px 0 5px; } .caltllab { display: flex; justify-content: space-between; font-size: 8.5px; color: var(--rpt-muted); margin-bottom: 2px; }
.chglist { display: flex; flex-direction: column; gap: 4px; margin-top: 7px; }
.chgline { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.cdot { width: 8px; height: 8px; border-radius: 50%; flex: 0 0 auto; }
.cdot.g { background: var(--rpt-good); } .cdot.r { background: var(--rpt-bad); } .cdot.a { background: var(--rpt-warn); }
.chgline .cdt { font-family: ui-monospace, Consolas, monospace; font-size: 11px; color: var(--rpt-ink); min-width: 168px; flex: 0 0 auto; }
.chgline .cdesc { color: var(--rpt-ink-soft); }
.calsum { margin-top: 9px; background: var(--rpt-accent-soft); border: 1px solid var(--rpt-edge); border-left: 4px solid var(--rpt-accent); border-radius: 8px; padding: 7px 11px; font-size: 11.5px; color: var(--rpt-ink-soft); }
.calsum.mut { background: var(--rpt-surface-2); border-left-color: var(--rpt-edge); color: var(--rpt-muted); }
.cchip { display: inline-block; font-size: 9px; font-weight: 800; border-radius: 999px; padding: 2px 8px; margin-right: 5px; }
.cchip.g { background: var(--rpt-good-bg); color: var(--rpt-good); } .cchip.r { background: var(--rpt-bad-bg); color: var(--rpt-bad); } .cchip.a { background: var(--rpt-warn-bg); color: var(--rpt-warn); }
.assign { margin-top: 9px; border-top: 1px dashed var(--rpt-edge); padding-top: 8px; }
.assignh { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .03em; color: var(--rpt-muted); margin-bottom: 6px; }
/* round-17 #03 — assigned-activities proportion bar (Option A), one per dimension */
.acrow { margin: 7px 0; }
.acdimn { font-size: 10px; font-weight: 700; color: var(--rpt-ink-soft); margin-bottom: 4px; }
.acbar { display: flex; width: 100%; height: 26px; border-radius: 7px; overflow: hidden; border: 1px solid var(--rpt-edge); }
.acseg { display: flex; align-items: center; justify-content: center; color: #fff; font-size: 10px; font-weight: 800; white-space: nowrap; overflow: hidden; min-width: 0; }
.aclegend { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 6px; font-size: 10.5px; color: var(--rpt-ink-soft); }
.aclegend span { display: inline-flex; align-items: center; gap: 5px; }
.aclegend i { width: 9px; height: 9px; border-radius: 3px; flex: 0 0 auto; }
.acids { margin-top: 6px; font-size: 10.5px; color: var(--rpt-muted); } .acids .idlist { font-family: ui-monospace, Consolas, monospace; color: var(--rpt-ink-soft); }
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
.balbl { font-size: 11px; font-weight: 600; text-align: right; color: var(--rpt-ink-soft); min-width: 0; }
.balbl .bnm { display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.balbl .bacode { display: block; font-size: 9px; font-weight: 700; color: var(--rpt-muted); margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.baw { display: flex; align-items: center; gap: 10px; }
.babars { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; }
.brow { display: flex; align-items: center; gap: 6px; }
.blab { width: 30px; flex-shrink: 0; text-align: right; font-size: 8px; font-weight: 800; text-transform: uppercase; letter-spacing: .03em; color: var(--rpt-muted); }
.blab.r1 { color: var(--rpt-accent); }
.btrack { position: relative; flex: 1; min-width: 0; display: flex; align-items: center; }
.baseg { height: 14px; border-radius: 4px; min-width: 2px; box-sizing: border-box; }
.baseg.b0 { background: var(--rpt-hair-strong); }
.baseg.b1 { background: var(--rpt-accent); }
.baseg.b0.rem { background: var(--rpt-bad); }
.baseg.b1.add { background: var(--rpt-good); }
.bval { position: absolute; font-size: 9px; font-weight: 800; white-space: nowrap; pointer-events: none; }
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
/* ── round-15 Calendar (Option A: section digest + brief + P6 ledger) — mirrors the screen rc-cal* */
.rc-mut { color: var(--rpt-muted); }
.rc-caldigest { display: flex; justify-content: space-between; gap: 14px; flex-wrap: wrap; align-items: center; background: var(--rpt-surface-2); border: 1px solid var(--rpt-edge); border-radius: 9px; padding: 8px 13px; margin-bottom: 11px; font-size: 12px; color: var(--rpt-ink); }
.rc-callegend { display: flex; gap: 12px; flex-wrap: wrap; font-size: 10px; color: var(--rpt-muted); }
.rc-callegend i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 4px; vertical-align: middle; }
.rc-callegend i.g { background: var(--rpt-good); } .rc-callegend i.r { background: var(--rpt-bad); } .rc-callegend i.a { background: var(--rpt-warn); }
.rc-calcard { border: 1px solid var(--rpt-edge); border-radius: 11px; padding: 11px 14px; margin-bottom: 11px; page-break-inside: avoid; }
.rc-calhead { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; margin-bottom: 3px; page-break-after: avoid; break-after: avoid; }
.rc-calname { font-size: 13.5px; font-weight: 800; color: var(--rpt-ink); }
.rc-calmeta { font-size: 10.5px; color: var(--rpt-muted); margin-left: auto; }
.rc-caltag { font-size: 8.5px; font-weight: 800; padding: 2px 8px; border-radius: 6px; }
.rc-caltag.chg { background: var(--rpt-warn-bg); color: var(--rpt-warn); }
.rc-caltag.add { background: var(--rpt-good-bg); color: var(--rpt-good); }
.rc-caltag.rem { background: var(--rpt-bad-bg); color: var(--rpt-bad); }
.rc-caltag.ren { background: var(--rpt-accent-soft); color: var(--rpt-accent); }
.rc-calbrief { font-size: 12.5px; line-height: 1.5; margin: 4px 0; color: var(--rpt-ink); page-break-after: avoid; break-after: avoid; }
.rc-hl-g { color: var(--rpt-good); font-weight: 700; } .rc-hl-r { color: var(--rpt-bad); font-weight: 700; } .rc-hl-a { color: var(--rpt-warn); font-weight: 700; }
.rc-calctx { font-size: 11.5px; color: var(--rpt-ink-soft); margin: 5px 0; } .rc-calctx b { color: var(--rpt-ink); }
.rc-flag { color: var(--rpt-warn); font-weight: 700; }
.rc-ldg { width: 100%; border-collapse: collapse; margin: 9px 0 4px; font-size: 11.5px; page-break-inside: avoid; }
.rc-ldg th { text-align: left; font-size: 9px; letter-spacing: .04em; text-transform: uppercase; color: var(--rpt-muted); font-weight: 800; padding: 6px 10px; border-bottom: 1px solid var(--rpt-edge); }
.rc-ldg td { padding: 6px 10px; border-bottom: 1px solid var(--rpt-hair); vertical-align: middle; }
.rc-ldg .rc-lattr { color: var(--rpt-ink-soft); font-weight: 600; width: 32%; }
.rc-ldg .rc-lrev { text-align: center; width: 19%; font-variant-numeric: tabular-nums; color: var(--rpt-ink); }
.rc-ldg .rc-lchg { text-align: right; width: 30%; }
.rc-ldg tr.rc-lband td { background: var(--rpt-surface-2); color: var(--rpt-ink-soft); font-weight: 800; font-size: 9px; letter-spacing: .04em; text-transform: uppercase; }
.rc-ldg tr.rc-lident td { color: var(--rpt-muted); font-style: italic; }
.rc-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 7px; vertical-align: 1px; }
.rc-dot.g { background: var(--rpt-good); } .rc-dot.r { background: var(--rpt-bad); } .rc-dot.a { background: var(--rpt-warn); }
.rc-chg-g { color: var(--rpt-good); font-weight: 700; } .rc-chg-r { color: var(--rpt-bad); font-weight: 700; }
.rc-chg-a { color: var(--rpt-warn); font-weight: 700; } .rc-chg-n { color: var(--rpt-muted); }
.rc-calunchanged { padding: 9px 14px; color: var(--rpt-muted); font-size: 12px; background: var(--rpt-surface-2); border: 1px dashed var(--rpt-edge); border-radius: 9px; margin-top: 4px; }
.rc-calunchanged b { color: var(--rpt-ink-soft); }
/* round-16 #03a — dropped-empty-added-calendars note */
.rc-caldrop { padding: 8px 13px; color: var(--rpt-muted); font-size: 11px; background: var(--rpt-surface-2); border: 1px dashed var(--rpt-edge); border-radius: 9px; margin-bottom: 11px; }
.rc-caldrop b { color: var(--rpt-ink-soft); }
/* round-16 #03c — a new/removed calendar's own non-working days, listed as a Date | Status table */
.rc-nwtbl { margin-top: 9px; border-top: 1px dashed var(--rpt-edge); padding-top: 8px; page-break-inside: avoid; }
.rc-nwh { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .03em; color: var(--rpt-muted); margin-bottom: 4px; }
.rc-nwh .rc-mut { font-weight: 600; text-transform: none; letter-spacing: 0; }
.rc-ldg.rc-nwld { margin-top: 4px; } .rc-ldg.rc-nwld .rc-lattr { width: 60%; font-weight: 600; }
.rc-ldg.rc-nwld .rc-lchg { text-align: left; width: 40%; }
/* round-18 #02 — highlight NEW non-working days (red) and REDUCED-hours periods (amber) */
.rc-ldg tr.rc-hi-new td { background: var(--rpt-bad-bg); box-shadow: inset 3px 0 0 var(--rpt-bad); }
.rc-ldg tr.rc-hi-red td { background: var(--rpt-warn-bg); box-shadow: inset 3px 0 0 var(--rpt-warn); }
.rc-flag { font-size: 8px; font-weight: 800; letter-spacing: .3px; padding: 1px 6px; border-radius: 20px; margin-left: 6px; text-transform: uppercase; }
.rc-flag.new { background: var(--rpt-bad); color: #fff; } .rc-flag.red { background: var(--rpt-warn); color: #fff; }
.rc-nwtbl.new { border: 1px solid var(--rpt-bad); background: var(--rpt-bad-bg); border-radius: 9px; padding: 9px 12px; }
.rc-nwtbl.new .rc-nwh { color: var(--rpt-bad); }
.rc-nwtbl.rem { background: var(--rpt-surface-2); }
/* round-18 #01 — assigned activities relocated to a full-width panel at the bottom of the card, dimension as pills */
.rc-assignpanel { margin-top: 11px; border: 1px solid var(--rpt-edge); border-radius: 10px; background: var(--rpt-surface); padding: 10px 12px; page-break-inside: avoid; }
.rc-assignhead { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
.rc-assignt { font-size: 9.5px; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; color: var(--rpt-ink-soft); }
.rc-assigntot { font-size: 10px; color: var(--rpt-muted); margin-left: auto; }
.rc-dimtabs { display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 8px; }
.rc-dimtab { font-size: 10px; font-weight: 700; padding: 3px 9px; border-radius: 20px; border: 1px solid var(--rpt-edge); background: var(--rpt-surface); color: var(--rpt-muted); }
.rc-dimtab.on { background: var(--rpt-accent-bg, var(--rpt-surface-2)); border-color: var(--rpt-accent); color: var(--rpt-accent); }
/* ── round-15 Manpower (labour man-hours, difference-first) — NEUTRAL blue(+)/violet(−), never good/bad */
.rc-mp-herorow { display: flex; align-items: center; gap: 26px; flex-wrap: wrap; margin: 6px 0 4px; }
.rc-mp-big { font-size: 46px; font-weight: 800; letter-spacing: -1.2px; line-height: 1; font-variant-numeric: tabular-nums; color: var(--rpt-muted); }
.rc-mp-big.up { color: var(--rpt-accent); } .rc-mp-big.down { color: var(--rpt-series-4); } .rc-mp-big.zero { color: var(--rpt-muted); }
.rc-mp-biglbl { font-size: 11.5px; font-weight: 700; color: var(--rpt-muted); letter-spacing: 0; margin-top: 7px; }
.rc-mp-chips { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.rc-mp-chip { background: var(--rpt-surface); border: 1px solid var(--rpt-edge); border-radius: 10px; padding: 8px 13px; min-width: 104px; }
.rc-mp-arrow { color: var(--rpt-muted); font-size: 20px; }
.rc-k { font-size: 9.5px; color: var(--rpt-muted); font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }
.rc-v { font-size: 18px; font-weight: 800; font-variant-numeric: tabular-nums; margin-top: 5px; line-height: 1; color: var(--rpt-ink); }
.rc-v.soft { color: var(--rpt-ink-soft); } .rc-v.up { color: var(--rpt-accent); } .rc-v.down { color: var(--rpt-series-4); } .rc-v.zero { color: var(--rpt-muted); }
.rc-cap { margin-top: 11px; font-size: 11px; color: var(--rpt-muted); background: var(--rpt-surface); border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 8px 11px; } .rc-cap b { color: var(--rpt-ink); }
.rc-tdiv { padding: 2px 2px 4px 0; }
.rc-trow { display: grid; grid-template-columns: 160px 1fr 92px; gap: 10px; align-items: center; margin: 6px 0; }
.rc-tn { font-size: 11.5px; font-weight: 600; text-align: right; color: var(--rpt-ink); min-width: 0; }
.rc-tn small { display: block; color: var(--rpt-muted); font-weight: 600; font-size: 9px; }
.rc-tbar { position: relative; height: 20px; background: var(--rpt-surface-2); border-radius: 5px; }
.rc-tmid { position: absolute; left: 50%; top: -3px; bottom: -3px; width: 1px; background: var(--rpt-edge); }
.rc-tfill { position: absolute; top: 3px; height: 14px; border-radius: 3px; }
.rc-tval { font-size: 11.5px; font-weight: 800; font-variant-numeric: tabular-nums; }
.rc-tval.up { color: var(--rpt-accent); } .rc-tval.down { color: var(--rpt-series-4); } .rc-tval.zero { color: var(--rpt-muted); }
.rc-d { font-weight: 700; } .rc-d.up { color: var(--rpt-accent); } .rc-d.down { color: var(--rpt-series-4); } .rc-d.zero { color: var(--rpt-muted); }
.rc-other { display: flex; gap: 12px; flex-wrap: wrap; }
.rc-obox { flex: 1; min-width: 150px; border: 1px solid var(--rpt-edge); border-radius: 10px; padding: 10px 13px; background: var(--rpt-surface); }
.rc-ov { font-size: 16px; font-weight: 800; font-variant-numeric: tabular-nums; margin-top: 4px; color: var(--rpt-ink); }
.rc-ou { font-size: 10.5px; color: var(--rpt-muted); margin-top: 3px; }
.rc-warn { margin-top: 9px; font-size: 10.5px; color: var(--rpt-warn); background: var(--rpt-warn-bg); border-radius: 8px; padding: 7px 11px; }
'''
