"""Render the redesigned Baseline Narrative Report (a :class:`NarrativeDoc` dict) to HTML.

Used both for the on-screen tab and as the source for the PDF export (Chrome → PDF
via :func:`page_html`). ONE renderer, ONE visual spec — the approved design is captured
pixel-for-pixel in ``mockups/narrative_full.html`` and this module reproduces it exactly:

  * A4 portrait pages, each framed by a double 1px border (``.b1`` outside ``.b2``).
  * Page furniture on every page: a 3-logo header band (``.rhead``) and a centred
    page-number footer (``.rfoot``). Front matter (cover + table of contents) is
    unnumbered; body page-numbering starts at Section 1.
  * Body font Times New Roman 12; section headings navy ``#1F4E79`` Calibri Light.
  * All charts are native HTML/CSS (never pictures): horizontal value bars, stacked
    green/red calendar histograms, box org-charts, two-per-row code tables.

This renderer draws STRAIGHT FROM THE DOC MODEL — every number, name, row, tree node
and bar comes as-is from the section payload; nothing is re-derived here. The producer
(:mod:`p6_narrative.report`) emits exactly the ten approved sections (renumbered 1..N):

  1  overview     {paragraphs:[str,str], breakdown:[{world,count}], total}
  2  image        {image:dataURL, caption?}                      (omitted when no layout)
  3  keyvals      {rows:[{k,v}]}
  4  ms_table     {columns, rows:[[name, date_str], …]}          (Major Milestones)
  5  ms_table     {columns, rows:[[name, date_str], …]}          (Key Dates)
  6  value_bars   {total, unit?, rows:[{name, amount, pct}]}
  7  scope        {total, unit?, codes:[names in order], narrative,
                   disciplines:[{name, cost, pct}],                       (7.1  pct of total)
                   cascade:[{name, cost, pct, count?, each?, children?:[…]}]} (7.2 N-level tree;
                       pct = share of PARENT; leaf = no children; identical siblings grouped)
  8  table        {view:'calendars', header:{calendar_count, activity_count},
                   dashboard:{…tiles, no shutdown…},
                   calendars:[{name, monthly:[{label, working_days, nonworking_days}], …}],
                   holidays:[{date, description}], hours_profiles:[{name, hours, sub}]}
  9  wbs_tree     {overview:{name, children:[{name}]},
                   branches:[{name, columns:[[l2, [[l3, [l4,…]], …]], …], depth}]}
 10  codes        {tables:[{dimension, rows:[{code, description}]}]}

``meta`` carries the page furniture: project_name, location, contract_type,
contract_value, data_date, revision, logos{owner,consultant,contractor}.
"""
import html as _h
import math

_ARROW = '➢'         # ➢ building bullet
_CHECK = '✓'         # ✓ element bullet
_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
# Shared DISTINCT discipline colour ramp — each discipline reads in its own hue (navy,
# green, amber, purple, red, teal, mauve), cycled if a chart has more segments than
# colours. Used by BOTH the §6 Contract-Value doughnut and the §7.1 composition bar so a
# discipline is the SAME colour in both sections. Any discipline literally named
# "Unclassified" / "Other" is forced to grey regardless of its position in the list.
_RAMP = ['1F4E79', '2E9E5B', 'E8A33D', '7A5AA6', 'C0504D', '4BACC6', 'B07AA1']
_GREY = '9AA4B0'


def _disc_color(name, i):
    """Colour for a discipline / type-of-work segment: grey for Unclassified / Other,
    otherwise the distinct ramp indexed by its order in the list (so the same discipline
    keeps the same colour across the §6 doughnut and the §7.1 composition bar)."""
    if str(name or '').strip().lower() in ('unclassified', 'other'):
        return _GREY
    return _RAMP[i % len(_RAMP)]


def _esc(x):
    return _h.escape('' if x is None else str(x))


def _clip(s, n):
    """Trim a label to n chars with an ellipsis (keeps on-chart text from overrunning)."""
    s = '' if s is None else str(s)
    return s if len(s) <= n else s[:n - 1] + '…'


def _num(v):
    """Group-format an integer-ish value ('2,507'); pass through anything else."""
    try:
        return format(int(round(float(v))), ',')
    except (TypeError, ValueError):
        return _esc(v)


def _fmt_full(v, cur=''):
    try:
        return '%s%s' % (cur, format(float(v), ',.0f'))
    except (TypeError, ValueError):
        return _esc(v)


def _fmt_abbrev(v, cur=''):
    """Compact money: 72,500,000 → 'USD 72.5M', trailing zeros stripped."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return _esc(v)
    a = abs(f)
    if a >= 1e9:
        s = ('%.2f' % (f / 1e9)).rstrip('0').rstrip('.') + 'B'
    elif a >= 1e6:
        s = ('%.2f' % (f / 1e6)).rstrip('0').rstrip('.') + 'M'
    elif a >= 1e3:
        s = ('%.1f' % (f / 1e3)).rstrip('0').rstrip('.') + 'K'
    else:
        s = format(f, ',.0f')
    return '%s%s' % (cur, s)


def _fmt_pct(p):
    try:
        f = float(p)
    except (TypeError, ValueError):
        return _esc(p)
    return ('%d' % f) if f == int(f) else ('%.1f' % f)


def _currency_prefix(meta, payload=None):
    """Best-available currency token ('USD ') for the money labels, or ''."""
    for src in (payload or {}, meta or {}):
        for key in ('currency', 'unit'):
            tok = str(src.get(key) or '').strip().split(' ')[0] if src.get(key) else ''
            if tok and tok.isalpha() and len(tok) <= 4:
                return tok.upper() + ' '
    return ''


# ── page furniture ────────────────────────────────────────────────────────────
def _rhead(meta):
    """The repeating 3-logo header band. Real logo data-URLs when present, else the
    dashed placeholder boxes from the approved mockup."""
    logos = (meta or {}).get('logos') or {}
    cells = ''
    for key, label in (('owner', 'OWNER'), ('consultant', 'CONSULTANT'),
                       ('contractor', 'CONTRACTOR')):
        src = logos.get(key)
        if src:
            inner = '<img class="lgimg" src="%s" alt="%s logo">' % (_esc(src), _esc(key))
        else:
            inner = '<div class="box">%s<br>logo</div>' % label
        cells += '<div class="lg">%s</div>' % inner
    return '<div class="rhead">%s</div>' % cells


def _page(meta, body, footer=''):
    return ('<div class="page"><div class="b1"><div class="b2">%s%s'
            '<div class="rfoot">%s</div></div></div></div>'
            % (_rhead(meta), body, _esc(footer)))


# ── shared horizontal bar chart (§6 value + §7 disciplines) ───────────────────
def _bars(rows, name_key, value_fn):
    if not rows:
        return '<p class="note">No cost loading in the file.</p>'
    maxp = max((float(r.get('pct') or 0) for r in rows), default=0) or 1.0
    out = ''
    for r in rows:
        pct = float(r.get('pct') or 0)
        width = max(pct / maxp * 100.0, 0.0)
        label = value_fn(r)
        # Wide bars carry the value inside the fill (white); short bars would clip it, so the
        # value sits just to the RIGHT of the fill in dark text (readable on the light track).
        if width >= 30:
            fill = '<div class="fill" style="width:%.4g%%">%s</div>' % (width, _esc(label))
        else:
            fill = ('<div class="fill" style="width:%.4g%%"></div>'
                    '<span class="val" style="left:calc(%.4g%% + 8px)">%s</span>'
                    % (width, width, _esc(label)))
        pct_over_fill = width >= 99.5
        pcls = ' style="color:#dbe6f2"' if pct_over_fill else ''
        out += ('<div class="bar"><div class="lab">%s</div>'
                '<div class="track">%s'
                '<div class="pct"%s>%s%%</div></div></div>'
                % (_esc(r.get(name_key)), fill, pcls, _fmt_pct(pct)))
    return out


# ── shared SVG chart primitives (doughnut + composition bar) ──────────────────
def _polar(cx, cy, r, deg):
    """Point on a circle, angle in degrees measured CLOCKWISE from 12 o'clock."""
    t = math.radians(deg - 90.0)
    return (cx + r * math.cos(t), cy + r * math.sin(t))


def _arc_path(cx, cy, R, ri, a0, a1):
    """SVG path 'd' for an annular sector (doughnut slice) from a0 to a1 (deg, clockwise
    from top). Outer arc a0→a1, inner arc a1→a0."""
    large = 1 if (a1 - a0) > 180 else 0
    ox0, oy0 = _polar(cx, cy, R, a0)
    ox1, oy1 = _polar(cx, cy, R, a1)
    ix1, iy1 = _polar(cx, cy, ri, a1)
    ix0, iy0 = _polar(cx, cy, ri, a0)
    return ('M %.2f %.2f A %.2f %.2f 0 %d 1 %.2f %.2f L %.2f %.2f A %.2f %.2f 0 %d 0 %.2f %.2f Z'
            % (ox0, oy0, R, R, large, ox1, oy1, ix1, iy1, ri, ri, large, ix0, iy0))


def _chart_legend(rows, value_fn):
    """A wrapping swatch legend under a chart: colour · bold name · muted value."""
    items = ''
    for i, r in enumerate(rows):
        items += ('<span style="display:inline-flex;align-items:center;gap:6px">'
                  '<i style="width:11px;height:11px;border-radius:3px;background:#%s;'
                  'display:inline-block;flex:0 0 auto"></i><b>%s</b>'
                  '<span style="color:#5a6672">&nbsp;%s</span></span>'
                  % (_disc_color(r.get('name'), i), _esc(r.get('name')), _esc(value_fn(r))))
    return ('<div style="display:flex;flex-wrap:wrap;gap:5px 18px;margin-top:9px;'
            'font-family:Calibri,sans-serif;font-size:11px;color:#33404d">%s</div>' % items)


# ── SVG doughnut (§6 Contract Value) ──────────────────────────────────────────
def _doughnut(rows, cap, center_big, value_fn):
    """An SVG doughnut of the value distribution by type of work: the dominant slice is
    labelled DIRECTLY on the ring (no leader), each small slice gets an external % + a
    leader arrow (Excel-style) laddered on the right, and the grouped total sits in the
    centre hole. A wrapping amount legend follows. Crisp vector for PDF/screen; the Word
    twin (``docx_native.add_doughnut``) draws the identical layout as native editable
    shapes, so §6 reads the same in Word, PDF and HTML."""
    rows = [r for r in rows if r]
    if not rows:
        return '<p class="note">No cost loading in the file.</p>'
    total_pct = sum(float(r.get('pct') or 0) for r in rows) or 100.0
    W, H, cx, cy, R, ri = 760, 330, 205, 165, 124, 73
    body, smalls, acc = '', [], 0.0
    for i, r in enumerate(rows):
        col = _disc_color(r.get('name'), i)
        p = float(r.get('pct') or 0)
        a0 = acc / total_pct * 360.0
        a1 = (acc + p) / total_pct * 360.0
        acc += p
        mid = (a0 + a1) / 2.0
        body += ('<path d="%s" fill="#%s" stroke="#fff" stroke-width="2"/>'
                 % (_arc_path(cx, cy, R, ri, a0, a1), col))
        if p >= 15:                                    # dominant slice → label ON the ring
            lx, ly = _polar(cx, cy, (R + ri) / 2.0, mid)
            body += ('<text x="%.1f" y="%.1f" text-anchor="middle" fill="#fff" '
                     'font-family="Calibri,sans-serif" font-size="15" font-weight="700">%s</text>'
                     '<text x="%.1f" y="%.1f" text-anchor="middle" fill="#fff" '
                     'font-family="Calibri,sans-serif" font-size="17" font-weight="700">%s%%</text>'
                     % (lx, ly - 5, _esc(_clip(r.get('name'), 18)), lx, ly + 15, _fmt_pct(p)))
        else:
            smalls.append((r, col, mid))
    # centre hole — cap + grouped total
    body += ('<circle cx="%d" cy="%d" r="%d" fill="#fff"/>'
             '<text x="%d" y="%d" text-anchor="middle" fill="#8a93a0" '
             'font-family="Calibri,sans-serif" font-size="10.5" font-weight="700">%s</text>'
             '<text x="%d" y="%d" text-anchor="middle" fill="#1F4E79" '
             'font-family="Calibri,sans-serif" font-size="16" font-weight="700">%s</text>'
             % (cx, cy, ri - 1, cx, cy - 9, _esc(cap), cx, cy + 14, _esc(center_big)))
    # external label ladder on the right for the small slices (Excel-style leader arrows)
    if smalls:
        chan_x, txt_x, top = W - 236, W - 236 + 14, 46
        gap = min(50.0, (H - top - 14) / max(len(smalls) - 1, 1))
        for j, (r, col, mid) in enumerate(smalls):
            ly = top + j * gap
            px, py = _polar(cx, cy, R, mid)
            sx, sy = _polar(cx, cy, R + 14, mid)
            body += ('<path d="M %.1f %.1f L %.1f %.1f L %d %.1f L %d %.1f" fill="none" '
                     'stroke="#9aa4ad" stroke-width="1.3"/>'
                     '<circle cx="%.1f" cy="%.1f" r="2.6" fill="#%s"/>'
                     '<rect x="%d" y="%.1f" width="8" height="8" rx="2" fill="#%s"/>'
                     '<text x="%d" y="%.1f" fill="#33404d" font-family="Calibri,sans-serif" '
                     'font-size="13" dominant-baseline="middle">'
                     '<tspan font-weight="700" fill="#1a1d21">%s </tspan>'
                     '<tspan font-weight="700" fill="#%s">%s%%</tspan></text>'
                     % (px, py, sx, sy, chan_x, ly, txt_x - 4, ly, px, py, col,
                        txt_x - 4, ly - 10, col, txt_x + 9, ly,
                        _esc(_clip(r.get('name'), 16)), col, _fmt_pct(r.get('pct'))))
    svg = ('<svg viewBox="0 0 %d %d" style="width:100%%;max-width:%dpx;display:block;'
           'margin:2px auto">%s</svg>' % (W, H, W, body))
    return '<div class="dnutfig">%s%s</div>' % (svg, _chart_legend(rows, value_fn))


# ── SVG 100% composition bar (§7.1 scope by discipline) ───────────────────────
def _compbar(rows):
    """An SVG 100% composition bar: one distinct-colour segment per discipline (width = its
    share of contract value). A wide segment carries its label inside; a medium one shows
    the pct inside; a segment too thin for text gets its % spread across the top with an
    angled leader down to the segment (so the small shares never collide). A swatch legend
    follows. Crisp vector for PDF/screen; the Word twin (``docx_native.add_composition_bar``)
    draws the identical layout as native editable shapes."""
    rows = [r for r in rows if r]
    if not rows:
        return '<p class="note">No cost loading in the file.</p>'
    total_pct = sum(float(r.get('pct') or 0) for r in rows) or 100.0
    W, H, x0, y0, bh = 760, 104, 8, 60, 40
    bw, n = W - 2 * x0, len(rows)
    body = '<rect x="%d" y="%d" width="%d" height="%d" rx="6" fill="#eef1f5"/>' % (x0, y0, bw, bh)
    smalls, acc = [], 0.0
    for i, r in enumerate(rows):
        col = _disc_color(r.get('name'), i)
        p = float(r.get('pct') or 0)
        w = p / total_pct * bw
        x = x0 + acc / total_pct * bw
        acc += p
        rx = 6 if (i == 0 or i == n - 1) else 0
        body += ('<rect x="%.2f" y="%d" width="%.2f" height="%d" rx="%d" fill="#%s" '
                 'stroke="#fff" stroke-width="1"/>' % (x, y0, max(w, 0.8), bh, rx, col))
        if w >= 150:                                   # wide → name + pct inside (white)
            body += ('<text x="%.2f" y="%d" text-anchor="middle" dominant-baseline="middle" '
                     'fill="#fff" font-family="Calibri,sans-serif" font-size="15" '
                     'font-weight="700">%s %s%%</text>'
                     % (x + w / 2.0, y0 + bh // 2 + 1, _esc(_clip(r.get('name'), 22)), _fmt_pct(p)))
        elif w >= 34:                                  # medium → pct only inside (white)
            body += ('<text x="%.2f" y="%d" text-anchor="middle" dominant-baseline="middle" '
                     'fill="#fff" font-family="Calibri,sans-serif" font-size="12" '
                     'font-weight="700">%s%%</text>' % (x + w / 2.0, y0 + bh // 2 + 1, _fmt_pct(p)))
        else:                                          # thin → external spread label + leader
            smalls.append((r, col, x + w / 2.0))
    if smalls:
        # spread just the % (segment colour identifies the discipline; the legend below carries
        # the names) — pct-only keeps the crowded small shares from overlapping each other.
        sx0, sx1, lab_y, m = x0 + bw * 0.34, W - 30, 18, len(smalls)
        for j, (r, col, seg_cx) in enumerate(smalls):
            lx = (sx0 + (sx1 - sx0) * j / (m - 1)) if m > 1 else (sx0 + sx1) / 2.0
            body += ('<path d="M %.1f %d L %.1f %d L %.1f %d" fill="none" stroke="#%s" '
                     'stroke-width="1.2"/>'
                     '<text x="%.1f" y="%d" text-anchor="middle" fill="#%s" '
                     'font-family="Calibri,sans-serif" font-size="12" font-weight="700" '
                     'dominant-baseline="middle">%s%%</text>'
                     % (lx, lab_y + 6, lx, lab_y + 16, seg_cx, y0 - 2, col,
                        lx, lab_y, col, _fmt_pct(r.get('pct'))))
    svg = ('<svg viewBox="0 0 %d %d" style="width:100%%;max-width:%dpx;display:block;'
           'margin:4px auto">%s</svg>' % (W, H, W, body))
    return ('<div class="compfig">%s%s</div>'
            % (svg, _chart_legend(rows, lambda r: '%s%%' % _fmt_pct(r.get('pct')))))


# ── §1 Project Overview ───────────────────────────────────────────────────────
def _overview(p, number, title, meta, cur):
    paras = ''.join(
        '<p data-section="%s" data-field="paragraphs.%d" data-editable="1">%s</p>'
        % (_esc(number), i, _esc(t)) for i, t in enumerate(p.get('paragraphs') or []))
    breakdown = p.get('breakdown') or []
    tiles = ''.join(
        '<div class="tile"><div class="n">%s</div><div class="l">%s</div></div>'
        % (_num(b.get('count')), _esc(b.get('world'))) for b in breakdown)
    total = ('<p style="margin-top:12px;font-size:12.5px">Total: '
             '<b style="color:#1F4E79">%s</b> baseline activities across %d major scopes.</p>'
             % (_num(p.get('total')), len(breakdown)))
    return ('%s<div class="subblue">Baseline composition</div>'
            '<div class="tiles">%s</div>%s' % (paras, tiles, total))


# ── §2 Project Layout ─────────────────────────────────────────────────────────
def _image(p, number, title, meta, cur):
    img = p.get('image')
    cap = p.get('caption') or 'Project general layout'
    if img:
        # a real layout drawing → figure + caption
        fig = ('<img src="%s" alt="%s" style="max-width:100%%;display:block;margin:0 auto;'
               'border:1px solid #b9c6d3;border-radius:6px">' % (_esc(img), _esc(cap)))
        return ('%s<div style="text-align:center;font-size:10.5px;color:#5a5f66;'
                'font-style:italic;margin-top:5px">Figure 1 &mdash; %s</div>'
                % (fig, _esc(cap)))
    # no drawing attached → a clean framed placeholder box (dashed, soft) carrying the
    # payload's own guidance text — never a broken / empty figure.
    ph = (p.get('placeholder')
          or 'No project layout drawing was attached. Add one in the report setup to '
             'show the project general arrangement here.')
    return ('<div class="ph-box"><div class="ph-ico">&#128506;</div>'
            '<div class="ph-txt">%s</div></div>' % _esc(ph))


# ── §3 Project Brief ──────────────────────────────────────────────────────────
def _keyvals(p, number, title, meta, cur):
    rows = ''.join('<tr><td class="k">%s</td><td>%s</td></tr>'
                   % (_esc(r.get('k')), _esc(r.get('v'))) for r in (p.get('rows') or []))
    if not rows:
        rows = '<tr><td colspan="2" class="note">&mdash;</td></tr>'
    return ('<p>The key contractual and programme data for the project, as recorded in '
            'the baseline schedule.</p><table class="kv">%s</table>' % rows)


# ── §4 / §5 milestone + key-date tables ───────────────────────────────────────
def _ms_table(p, number, title, meta, cur):
    is_keydates = 'key date' in (title or '').lower()
    intro = ('All Start and Finish milestones defined in the baseline schedule, in '
             'chronological order.' if is_keydates else
             'The major milestones defined in the baseline schedule (Start and Finish), '
             'in chronological order.')
    cols = p.get('columns') or ['Milestone', 'Date']
    head = '<tr>%s</tr>' % ''.join(
        '<th%s>%s</th>' % (' style="width:34%"' if i else '', _esc(c))
        for i, c in enumerate(cols))
    rows = p.get('rows') or []
    body = ''.join('<tr><td>%s</td><td>%s</td></tr>'
                   % (_esc(r[0] if len(r) > 0 else ''), _esc(r[1] if len(r) > 1 else ''))
                   for r in rows)
    if not body:
        body = ('<tr><td colspan="%d" class="note">No Start/Finish milestones defined.</td></tr>'
                % max(len(cols), 1))
    return '<p>%s</p><table class="dt">%s%s</table>' % (intro, head, body)


# ── §6 Contract Value ─────────────────────────────────────────────────────────
def _value_bars(p, number, title, meta, cur):
    cur = _currency_prefix(meta, p) or cur
    total = p.get('total')
    banner = ('<div class="banner"><span class="l">Total Contract Value</span>'
              '<span class="v">%s</span></div>' % _fmt_full(total, cur))
    # A doughnut of the value distribution by type of work: the grouped total sits in the
    # centre hole (currency in the small cap), each type is a colour-ramp segment, and the
    # legend carries the EXACT contract amount per type (grouped, matches the banner total).
    cap = ('TOTAL (%s)' % cur.strip()) if cur.strip() else 'TOTAL'
    dnut = _doughnut(p.get('rows') or [], cap, _num(total),
                     lambda r: _fmt_full(r.get('amount'), cur))
    return ('<p>The contract value and its distribution by type of work (the discipline '
            'activity code), from cost loading.</p>%s%s' % (banner, dnut))


# ── §6 Scope of Work (6.1 discipline shares + narrative, 6.2 by area/structure) ─
_CASC_MARK = ['➢', '▸', '–', '·']   # ➢ ▸ – ·  (by depth)


def _casc_html(nodes, cur, depth):
    """Render a scope cascade tree recursively: each non-leaf node is a heading line
    (marker by depth, name — cost at level 0, '· N grouped' when merged, pct%); each leaf
    (no children) is a '• name' bullet. Indented by depth."""
    out = ''
    for n in (nodes or []):
        kids = n.get('children') or []
        indent = depth * 16
        cnt = n.get('count')
        qty = (' &middot; %d grouped' % cnt) if (cnt and cnt > 1) else ''
        if not kids:
            out += ('<p class="wt-item" style="margin-left:%dpx"><span class="wt-b">&bull;</span> %s</p>'
                    % (indent, _esc(n.get('name'))))
            continue
        mk = _CASC_MARK[min(depth, len(_CASC_MARK) - 1)]
        money = (' &mdash; %s' % _fmt_full(n.get('cost'), cur)) if depth == 0 else ''
        pct = n.get('pct')
        pct_txt = (' (%s%%)' % _fmt_pct(pct)) if pct is not None else ''
        color = '#1F4E79' if depth == 0 else '#14324f'
        fs = 12.5 if depth == 0 else 11
        out += ('<p style="margin:%s 0 3px %dpx;font-family:Calibri,sans-serif;font-weight:700;'
                'color:%s;font-size:%gpx">%s&nbsp;%s%s%s%s</p>'
                % ('7px' if depth == 0 else '3px', indent, color, fs, mk,
                   _esc(n.get('name')), money, qty, pct_txt))
        out += _casc_html(kids, cur, depth + 1)
    return out


def _scope(p, number, title, meta, cur):
    cur = _currency_prefix(meta, p) or cur

    def _subhead(k, name, tail):
        return ('<div class="sub">%s.%d &middot; %s '
                '<span style="font-weight:400;font-size:9.5px;color:#8a93a0;'
                'text-transform:none;letter-spacing:0">&mdash; %s</span></div>'
                % (_esc(number), k, _esc(name), tail))

    codes = p.get('codes') or []
    codes_txt = (' &rarr; '.join(_esc(c) for c in codes)) if codes else 'the picked activity codes'
    out = ('<p>The scope is analysed by cross-filtering the picked activity codes, '
           'cost-weighted: %s.</p>' % codes_txt)

    # {number}.1 — scope overview: 100% composition bar of discipline shares + narrative
    out += (_subhead(1, 'Scope overview', 'by discipline')
            + _compbar(p.get('disciplines') or []))

    # editable auto-narrative callout (navy left-rule box)
    narrative = p.get('narrative')
    if narrative:
        out += ('<p data-section="%s" data-field="narrative" data-editable="1" '
                'style="border-left:3px solid #1F4E79;background:#f2f6fb;'
                'padding:9px 13px;margin:12px 0;border-radius:0 5px 5px 0;'
                'text-align:justify">%s</p>' % (_esc(number), _esc(narrative)))

    # {number}.2 — the N-level cross-filtered cascade the planner picked (rendered recursively:
    # ➢/▸/– heading per non-leaf level, "• …" bullet per deepest leaf, indented by depth)
    out += _subhead(2, 'Detailed scope by activity codes',
                    'cross-filtered through the picked codes, cost-weighted')
    cascade = p.get('cascade') or []
    if not cascade:
        out += '<p class="note">No activity-code breakdown available.</p>'
    else:
        out += _casc_html(cascade, cur, 0)
    return out


# ── §11 Sequence of Work (dependency-derived chevron flows) ────────────────────
# The same blue ramp the native Word chevrons use (docx_native._SEQ_PALETTE_HEX), so the
# screen, PDF and Word chevrons read identically.
_SEQ_COLORS = ['1F4E79', '2E75B6', '4472C4', '5B9BD5', '41719C', '8FAADC']


def _chevrons(labels):
    """An SVG chevron flow laid out by :func:`p6_narrative.util.chevron_layout`: a home-plate
    first step then chevrons, blue ramp, white bold labels — word-wrapped (and the font shrunk
    when needed) so text is NEVER truncated, and flowing onto MULTIPLE ROWS when one row would
    exceed the text column. The native Word twin (``docx_native.add_chevron_flow``) draws the
    SAME layout, so screen, PDF and Word read identically."""
    from p6_narrative.util import chevron_layout
    lay = chevron_layout(labels)
    rows = lay['rows']
    if not rows:
        return ''
    W, H, notch = lay['width'], lay['height'], 14
    body = ''
    for row in rows:
        for it in row:
            x, y, w, h = it['x'], it['y'], it['w'], it['h']
            col = _SEQ_COLORS[it['i'] % len(_SEQ_COLORS)]
            if it['kind'] == 'home':                   # home plate — flat left, pointed right
                pts = '%.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f' % (
                    x, y, x + w - notch, y, x + w, y + h / 2.0, x + w - notch, y + h, x, y + h)
                cx = x + (w - notch) / 2.0
            else:                                      # chevron — pointed both sides
                pts = '%.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f' % (
                    x, y, x + w - notch, y, x + w, y + h / 2.0, x + w - notch, y + h,
                    x, y + h, x + notch, y + h / 2.0)
                cx = x + notch + (w - notch) / 2.0
            body += ('<polygon points="%s" fill="#%s" stroke="#fff" stroke-width="1.5"/>'
                     % (pts, col))
            lines, fs = it['lines'], it['font_px']
            lh = fs * 1.25
            cy0 = y + h / 2.0 - (len(lines) - 1) * lh / 2.0
            for j, ln in enumerate(lines):
                body += ('<text x="%.1f" y="%.1f" text-anchor="middle" '
                         'dominant-baseline="middle" fill="#fff" font-family="Calibri,sans-serif" '
                         'font-size="%.1f" font-weight="700">%s</text>'
                         % (cx, cy0 + j * lh, fs, _esc(ln)))
    return ('<div class="seqflow"><svg viewBox="0 0 %.1f %.1f" style="width:100%%;max-width:%.0fpx;'
            'display:block">%s</svg></div>' % (W, H, W, body))


def _seqflow(p, number, title, meta, cur):
    analyses = (p or {}).get('analyses') or []
    if not analyses:
        return ('<p class="note">No sequence-of-work analysis could be derived from the '
                'schedule.</p>')
    out = ('<p>The execution sequence of work is read directly from the schedule’s own '
           'dependency logic — the links between the activities — rather than assumed. Each '
           'analysis below sequences one or two activity codes; where several structures share '
           'the same sequence they are shown once rather than duplicated.</p>')
    for i, a in enumerate(analyses, 1):
        atitle = a.get('title') or ('Analysis %d' % i)
        out += ('<div class="sub">%s.%d &middot; %s</div>' % (_esc(number), i, _esc(atitle)))
        narr = a.get('narrative')
        if narr:
            out += ('<p style="border-left:3px solid #1F4E79;background:#f2f6fb;'
                    'padding:9px 13px;margin:12px 0;border-radius:0 5px 5px 0;'
                    'text-align:justify">%s</p>' % _esc(narr))
        if a.get('kind') == 'single':
            steps = a.get('steps') or []
            if steps:
                out += _chevrons([s.get('name') for s in steps])
            else:
                out += '<p class="note">No ordered sequence could be derived for this code.</p>'
        else:
            groups = a.get('groups') or []
            if not groups:
                out += ('<p class="note">No grouped sequence could be derived for these '
                        'codes.</p>')
            for g in groups:
                cnt = g.get('count') or 0
                suffix = (' (&times;%d)' % cnt) if cnt > 1 else ''
                out += ('<p class="seq-glabel">&#10146;&nbsp;%s%s</p>'
                        % (_esc(g.get('label')), suffix))
                out += _chevrons([s.get('name') for s in (g.get('steps') or [])])
            nc = a.get('no_code')
            if nc:
                codes = a.get('codes') or ['', '']
                scode = codes[1] if len(codes) > 1 else 'this code'
                names = ', '.join(_esc(x) for x in nc[:-1])
                names = (names + ' and ' + _esc(nc[-1])) if len(nc) > 1 else _esc(nc[0])
                out += ('<p class="note">%s carry no %s coding and are delivered under other '
                        'scopes rather than the sequence above.</p>' % (names, _esc(scode)))
    return out


# ── §8 Project Calendars & Holidays ───────────────────────────────────────────
_DASH_TILES = [
    ('total_calendar_days', 'Total Calendar Days'),
    ('total_working_days', 'Working Days'),
    ('total_nonworking_days', 'Non-Working Days'),
    ('total_holidays', 'Holidays'),
    ('avg_working_days_per_month', 'Avg Work Days / Month'),
    ('avg_working_hours_per_day', 'Avg Work Hours / Day'),
]


def _cal_months(cal):
    """Normalise one calendar's monthly working/non-working series."""
    months = cal.get('monthly')
    if months:
        return [{'label': m.get('label'),
                 'working': int(m.get('working_days') or 0),
                 'nonworking': int(m.get('nonworking_days') or 0)} for m in months]
    wd = cal.get('net_working_days') or []
    nwd = cal.get('nonworking_days') or []
    labels = cal.get('months') or _MONTHS
    out = []
    for i, w in enumerate(wd):
        out.append({'label': labels[i] if i < len(labels) else '',
                    'working': int(w or 0),
                    'nonworking': int(nwd[i]) if i < len(nwd) else 0})
    return out


def _cal_hist(cal):
    months = _cal_months(cal)
    if not months:
        return ''
    maxtot = max((m['working'] + m['nonworking'] for m in months), default=0) or 1
    HH = 34.0
    cols = ''
    for m in months:
        w, nw = m['working'], m['nonworking']
        gh = HH * w / maxtot
        rh = HH * nw / maxtot
        cols += ('<div class="col"><div class="v">%d</div>'
                 '<div class="bstack">'
                 '<div class="rseg" style="height:%.1fpx"></div>'
                 '<div class="gseg" style="height:%.1fpx"></div></div>'
                 '<div class="m">%s</div></div>'
                 % (w, rh, gh, _esc(m['label'])))
    name = cal.get('name') or '—'
    acts = cal.get('activity_count')
    meta_txt = ' &mdash; %s activities' % _num(acts) if acts else ''
    return ('<div class="calfig"><div class="calname">%s%s</div>'
            '<div class="hist">%s</div></div>'
            % (_esc(name), meta_txt, cols))


def _calendars(p, number, title, meta, cur):
    header = p.get('header') or {}
    ccount = header.get('calendar_count')
    acount = header.get('activity_count')
    lead = ('<p style="font-size:11px;color:#5a6672">%s calendars assigned to activities '
            '&middot; %s activities.</p>' % (_num(ccount), _num(acount)))

    # 8.1 dashboard tiles (no shutdown-periods tile)
    dash = p.get('dashboard') or {}
    tiles = [(lbl, dash.get(key)) for key, lbl in _DASH_TILES if dash.get(key) is not None]
    trows = ''
    for i in range(0, len(tiles), 4):
        cells = ''.join('<div class="tile stat"><div class="n">%s</div>'
                        '<div class="l">%s</div></div>' % (_num(v), _esc(lbl))
                        for lbl, v in tiles[i:i + 4])
        style = ' style="margin-top:8px"' if i else ''
        trows += '<div class="tiles"%s>%s</div>' % (style, cells)
    dash_block = ('<div class="sub">%s.1 &middot; Executive Dashboard</div>%s'
                  % (_esc(number), trows)) if trows else ''

    # 8.2 one stacked histogram per assigned calendar
    hists = ''.join(_cal_hist(c) for c in (p.get('calendars') or []))
    hist_block = ''
    if hists:
        legend = ('<div class="callegend"><span><i style="background:#1f7a3d"></i>Working days'
                  '</span><span><i style="background:#b23030"></i>Non-working days</span></div>')
        hist_block = ('<div class="sub">%s.2 &middot; Calendar Timeline '
                      '<span style="font-weight:400;font-size:9.5px;color:#8a93a0;'
                      'text-transform:none;letter-spacing:0">&mdash; net working vs non-working '
                      'days per month, per calendar, across the baseline schedule</span></div>'
                      '%s%s' % (_esc(number), legend, hists))

    # 8.3 holidays (Date | Description only)
    hols = p.get('holidays') or []
    hol_block = ''
    if hols:
        hrows = ''.join('<tr><td>%s</td><td>%s</td></tr>'
                        % (_esc(h.get('date')), _esc(h.get('description'))) for h in hols)
        hol_block = ('<div class="sub">%s.3 &middot; Holidays</div>'
                     '<table class="dt"><tr><th style="width:26%%">Date</th>'
                     '<th>Description</th></tr>%s</table>' % (_esc(number), hrows))

    # 8.4 working-hours profile cards
    profs = p.get('hours_profiles') or []
    prof_block = ''
    if profs:
        cards = ''
        for pf in profs:
            sub = pf.get('sub') or pf.get('name') or ''
            cards += ('<div class="tile stat"><div class="n" style="font-size:13px">%s</div>'
                      '<div class="l">%s</div></div>' % (_esc(pf.get('hours')), _esc(sub)))
        prof_block = ('<div class="sub">%s.4 &middot; Working Hours Profile</div>'
                      '<div class="tiles">%s</div>' % (_esc(number), cards))

    return lead + dash_block + hist_block + hol_block + prof_block


# ── §9 Work Breakdown Structure ───────────────────────────────────────────────
# Per-level box palette (navy → blue), shared by the vertical CSS tree (.wt .lvN)
# and the horizontal inline-SVG tree: (fill, text, border), hex without '#'.
_WBS_LV = {
    0: ('1F4E79', 'ffffff', '1F4E79'),
    1: ('BCD3EA', '12324d', '9cbcdd'),
    2: ('DEEAF6', '14324f', '9cbcdd'),
    3: ('eef4fb', '1f4e79', '9cbcdd'),
    4: ('ffffff', '33414d', 'd3ddea'),
}


def _wbs_split(node):
    """A WBS node is either a bare name (a leaf) or a ``[name, [children…]]`` pair."""
    if isinstance(node, (list, tuple)):
        return (node[0] if len(node) > 0 else ''), (node[1] if len(node) > 1 else [])
    return node, []


def _wbs_norm(node, level):
    """Normalise a raw payload node into ``{name, level, children:[…]}`` (pre-order)."""
    name, kids = _wbs_split(node)
    return {'name': name, 'level': level,
            'children': [_wbs_norm(k, level + 1) for k in (kids or [])]}


def _wbs_metrics(root):
    """(node_count, max_label_len, level_span) for a normalised subtree — the three
    signals the adaptive orientation is chosen from (never hard-coded)."""
    cnt = ml = mlev = 0
    stack = [root]
    while stack:
        n = stack.pop()
        cnt += 1
        ml = max(ml, len(str(n['name'] or '')))
        mlev = max(mlev, n['level'])
        stack.extend(n['children'])
    return cnt, ml, (mlev - root['level'] + 1)


def _wbs_use_horizontal(root):
    """HORIZONTAL (compact left→right org-chart) only when the branch is small AND
    short-labelled AND shallow — otherwise VERTICAL indented stack, so a long label
    is never clipped and a wide branch never overflows the page."""
    cnt, ml, levels = _wbs_metrics(root)
    return cnt > 1 and cnt <= 10 and ml <= 24 and levels <= 3


def _wbs_vtree(root):
    """The VERTICAL indented tree (kept from the approved design) — nested ``<ul>``/
    ``<li>`` rendered by the ``.wt`` CSS (orthogonal elbow connectors via ::before/
    ::after). Level colours come from the ``.wt .lvN`` classes."""
    def _li(n):
        inner = '<span class="bx lv%d">%s</span>' % (min(n['level'], 4), _esc(n['name']))
        if n['children']:
            inner += '<ul>%s</ul>' % ''.join('<li>%s</li>' % _li(c) for c in n['children'])
        return inner
    return '<div class="wt"><ul><li>%s</li></ul></div>' % _li(root)


def _wbs_svg(root):
    """The HORIZONTAL left→right tidy tree, drawn as an inline SVG we compute so the
    layout + connectors are exact and never overlap or clip.

    Layout math (tidy tree): x = depth*COL_W (depth from the branch root = 0); each
    leaf takes the next Y slot; a parent's Y = the midpoint of its children's Y span.
    Connector per parent: from the parent's right edge a short horizontal segment to a
    vertical BUS line (spanning first→last child centre-Y), then a horizontal STUB from
    the bus to each child's left edge — one clean orthogonal elbow per real link, no
    diagonals, siblings aligned. The canvas grows to fit every box."""
    ROW_H, BOX_H = 30.0, 23.0
    CHAR_W, PAD_X, GAP_X, MARGIN = 6.2, 22.0, 26.0, 6.0
    _, maxlen, _ = _wbs_metrics(root)
    BOX_W = min(max(maxlen * CHAR_W + PAD_X, 64.0), 176.0)
    COL_W = BOX_W + GAP_X
    root_level = root['level']
    cursor = [MARGIN + BOX_H / 2.0]

    def _assign(n):
        n['_x'] = MARGIN + (n['level'] - root_level) * COL_W        # left edge
        if n['children']:
            for c in n['children']:
                _assign(c)
            n['_y'] = (n['children'][0]['_y'] + n['children'][-1]['_y']) / 2.0
        else:
            n['_y'] = cursor[0]
            cursor[0] += ROW_H
    _assign(root)

    nodes, elbows, maxx, maxy = [], [], [0.0], [0.0]

    def _walk(n):
        nodes.append(n)
        maxx[0] = max(maxx[0], n['_x'] + BOX_W)
        maxy[0] = max(maxy[0], n['_y'] + BOX_H / 2.0)
        if n['children']:
            bus_x = n['_x'] + BOX_W + GAP_X / 2.0
            ys = [c['_y'] for c in n['children']]
            d = 'M%.1f,%.1f H%.1f' % (n['_x'] + BOX_W, n['_y'], bus_x)
            if len(ys) > 1:
                d += ' M%.1f,%.1f V%.1f' % (bus_x, min(ys), max(ys))
            for c in n['children']:
                d += ' M%.1f,%.1f H%.1f' % (bus_x, c['_y'], c['_x'])
            elbows.append(d)
            for c in n['children']:
                _walk(c)
    _walk(root)

    W, H = maxx[0] + MARGIN, maxy[0] + MARGIN
    paths = ''.join('<path d="%s" fill="none" stroke="#9cbcdd" stroke-width="1.5" '
                    'stroke-linecap="square"/>' % d for d in elbows)
    boxes = ''
    for n in nodes:
        fill, txt, brd = _WBS_LV[min(n['level'], 4)]
        boxes += ('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="5" fill="#%s" '
                  'stroke="#%s" stroke-width="1"/>'
                  '<text x="%.1f" y="%.1f" text-anchor="middle" dominant-baseline="central" '
                  'font-family="Calibri,Arial,sans-serif" font-size="10.5" font-weight="700" '
                  'fill="#%s">%s</text>'
                  % (n['_x'], n['_y'] - BOX_H / 2.0, BOX_W, BOX_H, fill, brd,
                     n['_x'] + BOX_W / 2.0, n['_y'], txt, _esc(n['name'])))
    return ('<div class="wsvg"><svg viewBox="0 0 %.1f %.1f" width="%.1f" height="%.1f" '
            'xmlns="http://www.w3.org/2000/svg" style="max-width:100%%;height:auto" '
            'font-family="Calibri,Arial,sans-serif">%s%s</svg></div>' % (W, H, W, H, paths, boxes))


def _wbs_tree(p, number, title, meta, cur):
    intro = ('<p>The project WBS is presented below as a hierarchical tree &mdash; the '
             'project root, each major branch, then every branch expanded to its full depth. '
             'The layout adapts per branch: a small, short-labelled branch is drawn as a '
             'compact left-to-right org-chart (parent on the left, its children stacked in a '
             'column to the right, joined by clean orthogonal connectors), while a branch '
             'with many children or long labels keeps the vertical indented stack so no '
             'label is ever clipped.</p>')

    def _block(root, sub):
        tree = _wbs_svg(root) if _wbs_use_horizontal(root) else _wbs_vtree(root)
        return '<div class="sub">%s</div>%s' % (sub, tree)

    # number.1 · WBS Overview — project root (lv0) → each major branch (lv1). Always
    # VERTICAL (10 long-named majors would clip or overflow horizontally).
    overview = p.get('overview') or {}
    ov_root = {'name': overview.get('name'), 'level': 0,
               'children': [{'name': c.get('name'), 'level': 1, 'children': []}
                            for c in (overview.get('children') or [])]}
    out = intro + '<div class="sub">%s.1 &middot; WBS Overview</div>%s' % (
        _esc(number), _wbs_vtree(ov_root))

    # number.n · <branch> — breakdown — branch root (lv1) → L2 → L3 → L4, orientation
    # chosen per branch.
    for i, br in enumerate(p.get('branches') or [], 1):
        root = {'name': br.get('name'), 'level': 1,
                'children': [_wbs_norm(c, 2) for c in (br.get('columns') or [])]}
        out += _block(root, '%s.%d &middot; %s &mdash; breakdown'
                      % (_esc(number), i + 1, _esc(br.get('name'))))
    return out


# ── §10 Activity Codes ────────────────────────────────────────────────────────
def _codes(p, number, title, meta, cur):
    tables = [t for t in (p.get('tables') or []) if t.get('rows')]
    if not tables:
        return ('<p>The baseline uses the following activity-code structures.</p>'
                '<p class="note">No activity codes in the file.</p>')
    out = ('<p>The baseline uses the following activity-code structures. Each code and its '
           'values is listed below.</p>')
    # two tables per row
    for i in range(0, len(tables), 2):
        pair = tables[i:i + 2]
        cells = ''
        for j, t in enumerate(pair):
            rows = ''.join('<tr><td class="cv">%s</td><td>%s</td></tr>'
                           % (_esc(r.get('code')), _esc(r.get('description')))
                           for r in (t.get('rows') or []))
            cells += ('<div><div class="ct">%d &middot; %s</div>'
                      '<table class="codetbl"><tr><th style="width:40%%">Code Value</th>'
                      '<th>Description</th></tr>%s</table></div>'
                      % (i + j + 1, _esc(t.get('dimension')), rows))
        out += '<div class="codes">%s</div>' % cells
    return out


# ── §12 Activity IDs ──────────────────────────────────────────────────────────
def _actid_count(v):
    try:
        return '{:,}'.format(int(v))
    except (TypeError, ValueError):
        return '' if v is None else str(v)


def _actids(p, number, title, meta, cur):
    """Screen/PDF twin of the native Word §12 (``docx_writer._render_activity_ids``): the intro,
    then 12.1 the colour-coded ID anatomy (role-shaded breakdown table + role legend), then one
    breakdown block per ID type — the sample-ID box, the role-shaded code/meaning table and a
    green ✓ note. Colours = the same role hex as Word. None-safe."""
    from p6_narrative.actids import ROLE_HEX, ROLE_NAME, ANATOMY_INTRO, INTRO
    p = p or {}
    anatomy = p.get('anatomy')
    blocks = p.get('blocks') or []
    if not (anatomy or blocks):
        return '<p class="note">No structured Activity IDs could be read from the schedule.</p>'

    def _table(cols):
        cols = list(cols or [])
        codes = ''.join(
            '<td class="acode" style="background:#%s">%s</td>'
            % (ROLE_HEX.get(c.get('role'), ROLE_HEX['other']), _esc(c.get('code')))
            for c in cols)
        means = ''.join('<td class="amean">%s</td>' % _esc(c.get('meaning')) for c in cols)
        return '<table class="actidtbl"><tr>%s</tr><tr>%s</tr></table>' % (codes, means)

    out = '<p>%s</p>' % _esc(p.get('intro') or INTRO)

    # 12.1 — how to read an Activity ID (the colour-coded anatomy + role legend)
    out += '<div class="sub">%s.1 &middot; How to read an Activity ID</div>' % _esc(number)
    out += '<p>%s</p>' % _esc(ANATOMY_INTRO)
    if anatomy and anatomy.get('cols'):
        out += ('<div class="actidblk"><p class="actidex">Example:&nbsp; %s</p>%s'
                % (_esc(anatomy.get('sample')), _table(anatomy.get('cols'))))
        chips = ''.join(
            '<span class="actidchip" style="background:#%s"></span>'
            '<span class="actidlbl">%s</span>' % (ROLE_HEX[r], _esc(ROLE_NAME[r]))
            for r in ('stage', 'work', 'area', 'serial'))
        out += '<div class="actidlegend">%s</div></div>' % chips
    else:
        out += '<p class="note">No representative Activity ID could be derived for the anatomy.</p>'

    # 12.2 … — one breakdown block per ID type (block index starts at 2, as the mock does)
    for bi, blk in enumerate(blocks, start=2):
        out += ('<div class="sub">%s.%d &middot; %s ID</div>'
                % (_esc(number), bi, _esc(blk.get('title') or '—')))
        out += ('<div class="actidblk"><div class="actidbox">%s</div>%s'
                '<div class="actidnote">&#10003;&nbsp; %s&nbsp; (%s activities)</div></div>'
                % (_esc(blk.get('sample')), _table(blk.get('cols')),
                   _esc(blk.get('note') or ''), _actid_count(blk.get('count'))))
    return out


# ── §13 Resource Loading + §14 Material Resources ─────────────────────────────
def _wnum(v):
    try:
        return '{:,.0f}'.format(round(float(v or 0)))
    except Exception:
        return '0'


def _res_hist(labels, values, color):
    """A single-series vertical histogram with a value label above each bar — the resource
    twin of the §8 calendar histogram (``_cal_hist``), reused for manpower/equipment/material."""
    labels = labels or []
    values = values or []
    if not labels or not values:
        return ''
    mx = max(values) or 1
    HH = 44.0
    cols = ''
    for lab, v in zip(labels, values):
        h = HH * (float(v) / mx) if mx else 0.0
        cols += ('<div class="col"><div class="v">%s</div>'
                 '<div class="bstack"><div class="rbar" style="height:%.1fpx;background:#%s"></div>'
                 '</div><div class="m">%s</div></div>'
                 % (_esc(_wnum(v)), h, _esc(color or '1F4E79'), _esc(lab)))
    return '<div class="hist reshist">%s</div>' % cols


def _resload(p, number, title, meta, cur):
    """§13 — Manpower (man-hours AND headcount histograms) + Equipment (machines on site), each
    a labelled histogram with a per-resource totals table. Twin of ``docx._render_resload``."""
    p = p or {}
    if not p.get('available'):
        return ('<p class="note">This schedule carries no manpower or equipment loading in '
                'its baseline resource assignments.</p>')
    out = ['<p>%s</p>' % _esc(p.get('intro') or '')]
    for i, g in enumerate(p.get('groups') or [], 1):
        out.append('<div class="sub">%s.%d &middot; %s</div>'
                   % (_esc(number), i, _esc(g.get('title'))))
        out.append('<p class="rescap">%s Total budgeted %s %s across %s.</p>'
                   % (_esc(g.get('basis_note') or ''), _esc(g.get('total_label')),
                      _esc(g.get('total_unit')), _esc(g.get('window'))))
        for ch in (g.get('charts') or []):
            pu = (' ' + ch['peak_unit']) if ch.get('peak_unit') else ''
            peak = 'Peak %s%s in %s.' % (_wnum(ch.get('peak_val')), _esc(pu),
                                         _esc(ch.get('peak_label')))
            out.append('<div class="calfig"><div class="calname">%s</div>%s'
                       '<div class="rescap">%s</div></div>'
                       % (_esc(ch.get('chart_title')),
                          _res_hist(ch.get('span'), ch.get('values'), ch.get('color')), peak))
        heads = g.get('row_headers') or ['Resource', 'Total', 'Peak']
        thead = '<tr>%s</tr>' % ''.join(
            '<th%s>%s</th>' % (' class="num"' if j else '', _esc(h))
            for j, h in enumerate(heads))
        body = ''.join('<tr><td>%s</td><td class="num">%s</td><td class="num">%s</td></tr>'
                       % (_esc(r[0] if len(r) > 0 else ''), _esc(r[1] if len(r) > 1 else ''),
                          _esc(r[2] if len(r) > 2 else '')) for r in (g.get('rows') or []))
        out.append('<table class="dt">%s%s</table>' % (thead, body))
    return ''.join(out)


def _materials(p, number, title, meta, cur):
    """§14 — one labelled monthly-quantity histogram per material resource (top by total),
    each in its own unit, then a full totals table and the cost-model note. Never mixes units.
    Twin of ``docx_writer._render_materials``."""
    p = p or {}
    if not p.get('available'):
        return ('<p class="note">This schedule carries no unit-bearing material resources in '
                'its baseline.</p>')
    out = ['<p>%s</p>' % _esc(p.get('intro') or '')]
    cap = ''
    if (p.get('total_n') or 0) > (p.get('charted_n') or 0):
        cap = ' (top %d of %d by total)' % (p.get('charted_n'), p.get('total_n'))
    out.append('<div class="sub">%s.1 &middot; Monthly quantity per material%s</div>'
               % (_esc(number), _esc(cap)))
    for m in (p.get('charts') or []):
        out.append('<div class="calfig"><div class="calname">%s &mdash; %s (total %s %s)</div>%s'
                   '<div class="rescap">Peak %s %s in %s.</div></div>'
                   % (_esc(m.get('name')), _esc(m.get('unit')), _esc(_wnum(m.get('total'))),
                      _esc(m.get('unit')),
                      _res_hist(m.get('span'), m.get('values'), m.get('color')),
                      _esc(_wnum(m.get('peak_val'))), _esc(m.get('unit')),
                      _esc(m.get('peak_label'))))
    heads = p.get('table_headers') or ['Material resource', 'Unit', 'Total Quantity']
    thead = '<tr>%s</tr>' % ''.join(
        '<th%s>%s</th>' % (' class="num"' if j == 2 else '', _esc(h))
        for j, h in enumerate(heads))
    body = ''.join('<tr><td>%s</td><td>%s</td><td class="num">%s</td></tr>'
                   % (_esc(r[0] if len(r) > 0 else ''), _esc(r[1] if len(r) > 1 else ''),
                      _esc(r[2] if len(r) > 2 else '')) for r in (p.get('table_rows') or []))
    out.append('<div class="sub">%s.2 &middot; Materials Major Quantities</div>' % _esc(number))
    out.append('<table class="dt">%s%s</table>' % (thead, body))
    exc = p.get('excluded')
    if exc:
        out.append('<p class="note">%s unit-less &ldquo;material&rdquo; assignments '
                   '(total %s) are the cost model &mdash; the contract value &mdash; and are '
                   'reported in the cost sections, not charted as physical quantities.</p>'
                   % (_esc(exc.get('n')), _esc(exc.get('total_label'))))
    return ''.join(out)


_RENDER = {
    'overview': _overview,
    'image': _image,
    'keyvals': _keyvals,
    'ms_table': _ms_table,
    'value_bars': _value_bars,
    'scope': _scope,
    'wbs_tree': _wbs_tree,
    'codes': _codes,
    'sequence': _seqflow,
    'activity_ids': _actids,
    'resload': _resload,
    'materials': _materials,
}


def _section_body(s, meta, cur):
    kind = s.get('kind', '')
    payload = s.get('payload') or {}
    number = s.get('number', '')
    title = s.get('title', '')
    if kind == 'table' and payload.get('view') == 'calendars':
        return _calendars(payload, number, title, meta, cur)
    render = _RENDER.get(kind)
    if not render:
        return ''
    return render(payload, number, title, meta, cur)


def _section_page(s, meta, cur, footer):
    number = s.get('number', '')
    title = s.get('title', '')
    head = '<h1 class="sec">%s) %s</h1>' % (_esc(number), _esc(title))
    body = _section_body(s, meta, cur)
    # Wrap the heading + body in an addressable section block so the interactive
    # layer (Report-Contents selection, in-place prose editing, reorder/hide) can
    # target each section by its number. Purely semantic — no visual change.
    inner = ('<section class="sec" data-section="%s">%s%s</section>'
             % (_esc(number), head, body))
    return _page(meta, inner, footer)


# ── cover + table of contents ─────────────────────────────────────────────────
def _cover(meta):
    project = _esc(meta.get('project_name') or 'Project')
    lines = ('<div style="font-family:Calibri,sans-serif;color:#1F4E79;font-weight:700;'
             'font-size:22px">BASELINE</div>'
             '<div style="font-family:Calibri,sans-serif;color:#1F4E79;font-weight:700;'
             'font-size:30px;margin-top:4px">NARRATIVE REPORT</div>'
             '<div style="font-size:20px;margin-top:26px">%s</div>' % project)
    loc = meta.get('location')
    if loc:
        lines += ('<div style="font-size:14px;color:#8a95a1;margin-top:6px">%s</div>'
                  % _esc(loc))
    dd = meta.get('data_date')
    rev = meta.get('revision')
    sub = ''
    if dd:
        sub = 'Data date: %s' % _esc(dd)
    if rev:
        sub += ('%sRev. %s' % ('&nbsp;&nbsp;&middot;&nbsp;&nbsp;' if sub else '', _esc(rev)))
    if sub:
        lines += ('<div style="font-size:12px;color:#8a95a1;margin-top:16px">%s</div>' % sub)
    body = '<div style="margin-top:60mm" class="cover-t">%s</div>' % lines
    return _page(meta, body, '')


_TOC_GROUPS = [
    ('PROJECT DEFINITION', ('Project Overview', 'Project Layout', 'Project Brief')),
    ('BASELINE TARGETS', ('Major Milestones', 'Key Dates', 'Contract Value')),
    ('SCOPE & STRUCTURE', ('Scope of Work', 'Project Calendars & Holidays',
                           'Work Breakdown Structure', 'Activity Codes',
                           'Sequence of Work', 'Activity IDs')),
]


def _toc(meta, paged, page_map=None):
    """``paged`` = [(section, page_number), …] in body order.

    ``page_map`` (optional) maps a section's number → its real physical page in the
    exported PDF (found by the two-pass export). When supplied, the TOC prints those
    real page numbers instead of the section ordinal — so a section that overflowed
    onto a later sheet still lists the page you actually turn to."""
    grp_hdr = ('<div style="font-family:Calibri,sans-serif;font-size:11px;color:#8a95a1;'
               'font-weight:700;letter-spacing:.06em;margin:16px 0 5px;border-bottom:'
               '1px solid #e2e8ef;padding-bottom:3px">%s</div>')
    item = ('<div class="toc-i" style="display:flex;font-size:13px;padding:5px 0">'
            '<span style="color:#1F4E79;font-weight:700;width:34px">%s)</span>'
            '<span>%s</span><span style="flex:1;border-bottom:1.4px dotted #9aa4b0;'
            'margin:0 8px;transform:translateY(-4px)"></span><span>%s</span></div>')

    def _pg(s, pg):
        if page_map:
            v = page_map.get(str(s.get('number')))
            if v:
                return v
        return pg

    by_title = {s.get('title'): (s, pg) for s, pg in paged}
    used = set()
    out = ''
    for label, titles in _TOC_GROUPS:
        rows = ''
        for t in titles:
            if t in by_title:
                s, pg = by_title[t]
                used.add(t)
                rows += item % (_esc(s.get('number')), _esc(s.get('title')), _pg(s, pg))
        if rows:
            out += (grp_hdr % _h.escape(label)) + rows
    # any section not covered by a named group (defensive) → an "OTHER" trailer
    extra = ''
    for s, pg in paged:
        if s.get('title') not in used:
            extra += item % (_esc(s.get('number')), _esc(s.get('title')), _pg(s, pg))
    if extra:
        out += (grp_hdr % 'OTHER') + extra
    body = ('<div style="text-align:center;font-family:\'Calibri Light\',Calibri,sans-serif;'
            'color:#1F4E79;font-weight:700;font-size:24px;margin-bottom:6px">'
            'Table of Contents</div>'
            '<div style="height:2px;width:120px;background:#1F4E79;margin:0 auto 22px"></div>'
            '%s' % out)
    return _page(meta, body, '')


# ── public API ────────────────────────────────────────────────────────────────
def render_narrative_html(doc, seq_style=None, page_map=None):
    """Render the narrative ``doc`` (dict) to a self-contained HTML string.

    ``seq_style`` is accepted for signature compatibility with the export path; the
    redesigned report has a single fixed layout, so it is unused. ``page_map`` (optional)
    maps a section number → its real physical page in the exported PDF; when supplied the
    Table of Contents prints those real page numbers instead of the section ordinal (the
    two-pass PDF export in ``server.py`` fills it on the second pass)."""
    doc = doc or {}
    meta = doc.get('meta') or {}
    cur = _currency_prefix(meta)
    sections = [s for s in (doc.get('sections') or []) if s]
    paged = [(s, i) for i, s in enumerate(sections, 1)]     # body page numbering from 1

    pages = [_cover(meta), _toc(meta, paged, page_map)]
    for s, pg in paged:
        pages.append(_section_page(s, meta, cur, pg))
    return '<style>%s</style>%s' % (_CSS, ''.join(pages))


def page_html(doc, page_map=None):
    """Full standalone HTML page (Chrome → PDF source). ``page_map`` is threaded to the
    TOC so the two-pass export can stamp real physical page numbers on the second pass."""
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<title>Baseline Narrative Report</title></head><body>'
            + render_narrative_html(doc, page_map=page_map) + '</body></html>')


# ── the approved visual spec (mockups/narrative_full.html), verbatim + the native
#    stacked-histogram / logo-image additions the live payload needs. ───────────
_CSS = """
@page { size: A4 portrait; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: 'Times New Roman', Georgia, serif; color: #1a1d21; background:#8a9099; }
.page { width: 210mm; min-height: 297mm; background:#fff; margin: 0 auto; page-break-after: always; padding: 9mm; }
.b1 { border: 1px solid #000; min-height: 279mm; padding: 2.2mm; }
.b2 { border: 1px solid #000; min-height: 274mm; padding: 8mm 9mm; position: relative; }
.rhead { display:flex; border-bottom: 1.2px solid #cbd8e2; padding-bottom: 7px; margin-bottom: 14px; }
.rhead .lg { flex:1; text-align:center; padding: 0 5px; display:flex; align-items:center; justify-content:center; }
.rhead .box { border:1px dashed #c2ccd6; color:#aab4bf; font-size:9px; padding:11px 3px; background:#fafcfe; font-family:Calibri,sans-serif; width:100%; }
.rhead .lgimg { max-height:46px; max-width:100%; object-fit:contain; }
.rfoot { position:absolute; left:9mm; right:9mm; bottom:5mm; text-align:center; color:#8a95a1; font-size:10px; font-family:Calibri,sans-serif; }
h1.sec { font-family:'Calibri Light',Calibri,sans-serif; color:#1F4E79; font-weight:700; font-size:20px; margin:2px 0 12px; break-after:avoid; page-break-after:avoid; }
.sub, .subblue, .subctr { break-after:avoid; page-break-after:avoid; }
h1.sec + *, .sub + *, .subblue + *, .subctr + * { break-before:avoid; page-break-before:avoid; }
p { font-size:13px; line-height:1.55; margin:0 0 11px; }
.note { color:#9aa4b0; font-size:10.5px; font-style:italic; margin-top:10px; }
.ph-box { border:1.5px dashed #b9c6d3; background:#f7fafd; border-radius:8px; padding:34px 26px; text-align:center; margin:12px 0; }
.ph-ico { font-size:34px; line-height:1; margin-bottom:10px; color:#9fb2c8; font-family:'Segoe UI Emoji',Calibri,sans-serif; }
.ph-txt { font-size:12.5px; color:#5a6672; max-width:74%; margin:0 auto; line-height:1.6; font-family:'Times New Roman',Georgia,serif; }
.sub { font-family:Calibri,sans-serif; font-size:12px; text-transform:uppercase; letter-spacing:1px; color:#17457a; border-bottom:1px solid #dbe1e8; padding-bottom:4px; margin:16px 0 12px; font-weight:700; }
.subblue { font-family:Calibri,sans-serif; font-size:11px; font-weight:700; color:#1F4E79; text-transform:uppercase; letter-spacing:.03em; margin:6px 0 8px; }
table { border-collapse: collapse; }
.kv { width:100%; font-size:12px; break-inside:avoid; page-break-inside:avoid; }
.kv td { border:1px solid #cbd8e2; padding:7px 11px; }
.kv td.k { width:36%; background:#eef3f9; color:#1F4E79; font-weight:700; }
.dt { width:100%; font-size:12px; break-inside:avoid; page-break-inside:avoid; }
.dt th { background:#26517d; color:#fff; text-align:center; vertical-align:middle; padding:6px 9px; font-size:10.5px; font-family:Calibri,sans-serif; overflow-wrap:anywhere; }
.dt td { border:1px solid #dbe3ec; padding:6px 9px; text-align:center; vertical-align:middle; overflow-wrap:anywhere; word-break:break-word; }
.dt tr:nth-child(even) td { background:#f7f9fb; }
.r { text-align:right; }
.tiles { display:flex; gap:8px; }
.tile { flex:1; border:1px solid #b9d1ea; background:#DEEAF6; border-radius:7px; padding:9px 6px; text-align:center; }
.tile.stat { background:#f2f5f8; border-color:#d7e0ea; }
.tile .n { font-size:18px; font-weight:800; color:#1F4E79; font-family:Calibri,sans-serif; }
.tile .l { font-size:9px; color:#4a5560; margin-top:2px; font-family:Calibri,sans-serif; }
.bar { display:flex; align-items:center; gap:10px; margin-bottom:9px; }
.bar .lab { width:130px; text-align:right; font-size:12px; font-weight:700; color:#14324f; }
.bar .track { flex:1; position:relative; background:#eef2f6; border-radius:4px; height:24px; }
.bar .fill { position:absolute; left:0; top:0; bottom:0; background:#1F4E79; border-radius:4px; display:flex; align-items:center; padding-left:9px; color:#fff; font-size:10.5px; font-weight:700; font-family:Calibri,sans-serif; white-space:nowrap; }
.bar .pct { position:absolute; right:8px; top:0; bottom:0; display:flex; align-items:center; font-size:10.5px; font-weight:700; color:#5a6672; font-family:Calibri,sans-serif; }
.bar .val { position:absolute; top:0; bottom:0; display:flex; align-items:center; font-size:10.5px; font-weight:700; color:#14324f; font-family:Calibri,sans-serif; white-space:nowrap; }
.dnutwrap { display:flex; align-items:center; gap:24px; margin:8px 0 4px; }
.dnut { position:relative; width:168px; height:168px; border-radius:50%; flex:0 0 auto; }
.dnut-hole { position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); width:104px; height:104px; background:#fff; border-radius:50%; display:flex; flex-direction:column; align-items:center; justify-content:center; box-shadow:0 0 0 1px #e2e8ef inset; }
.dnut-cap { font-family:Calibri,sans-serif; font-size:9px; letter-spacing:.05em; color:#8a95a1; text-transform:uppercase; }
.dnut-tot { font-family:Calibri,sans-serif; font-size:15px; font-weight:800; color:#1F4E79; margin-top:2px; }
.dnut-legend { flex:1; min-width:0; }
.dl-row { display:flex; align-items:center; font-size:11px; padding:3px 0; border-bottom:1px solid #eef2f6; }
.dl-sw { width:11px; height:11px; border-radius:2px; flex:0 0 auto; margin-right:8px; }
.dl-name { flex:1; color:#14324f; font-weight:700; }
.dl-amt { color:#5a6672; font-family:Calibri,sans-serif; font-size:10.5px; margin:0 12px; white-space:nowrap; }
.dl-pct { width:44px; text-align:right; font-family:Calibri,sans-serif; font-weight:700; color:#1F4E79; }
.compbar { display:flex; height:30px; border-radius:6px; overflow:hidden; border:1px solid #cbd8e2; margin:4px 0 8px; }
.compseg { display:flex; align-items:center; justify-content:center; color:#fff; font-family:Calibri,sans-serif; font-size:10.5px; font-weight:700; white-space:nowrap; overflow:hidden; min-width:0; text-shadow:0 1px 1px rgba(0,0,0,.35); }
.complegend { font-size:10px; color:#5b6472; font-family:Calibri,sans-serif; line-height:1.9; }
.complegend .cl-i { display:inline-flex; align-items:center; gap:4px; }
.complegend .cl-i i { width:10px; height:10px; border-radius:2px; display:inline-block; }
.seqflow { margin:3px 0 12px; break-inside:avoid; page-break-inside:avoid; }
.dnutfig, .compfig, .calfig { break-inside:avoid; page-break-inside:avoid; }
.seq-glabel { font-family:Calibri,sans-serif; font-weight:700; color:#1F4E79; font-size:12.5px; margin:11px 0 3px; break-after:avoid; page-break-after:avoid; }
.seq-glabel + .seqflow { break-before:avoid; page-break-before:avoid; }
.banner { display:flex; justify-content:space-between; align-items:center; background:#1F4E79; color:#fff; border-radius:6px; padding:9px 14px; margin-bottom:12px; font-family:Calibri,sans-serif; }
.banner .l { font-size:11px; letter-spacing:.03em; text-transform:uppercase; }
.banner .v { font-size:18px; font-weight:800; }
.subctr { text-align:center; font-weight:700; font-size:13px; color:#14324f; text-decoration:underline; margin:14px 0 9px; }
.arw { font-size:13px; font-weight:700; margin:0 0 3px; }
.arw .a { color:#1F4E79; }
.chk { margin:0 0 1px; padding-left:24px; font-size:12.5px; }
.chk .c { color:#1f7a3d; }
.disc-name { font-size:12.5px; font-weight:700; color:#14324f; margin:6px 0 2px; padding-left:22px; }
.wt-item { font-size:12px; color:#33414d; margin:0 0 1px; padding-left:36px; line-height:1.45; }
.wt-item .wt-b { color:#1F4E79; font-weight:700; }
.callegend { display:flex; gap:14px; flex-wrap:wrap; margin:4px 0 10px; font-size:9.5px; color:#5b6472; font-family:Calibri,sans-serif; }
.callegend span { display:inline-flex; align-items:center; gap:4px; }
.callegend i { width:10px; height:10px; border-radius:2px; display:inline-block; }
.calname { font-size:11px; font-weight:700; color:#17457a; margin:6px 0 3px; font-family:Calibri,sans-serif; }
.hist { display:flex; align-items:flex-end; gap:7px; margin:2px 0 5px; padding:0 2px 3px; border-bottom:1px solid #e2e8ef; }
.hist .col { flex:1; text-align:center; }
.hist .v { font-size:9.5px; color:#17457a; font-weight:700; font-family:Calibri,sans-serif; }
.hist .bstack { display:flex; flex-direction:column; justify-content:flex-end; margin-top:3px; }
.hist .gseg { background:#1f7a3d; border-radius:0 0 3px 3px; }
.hist .rseg { background:#b23030; border-radius:3px 3px 0 0; }
.hist .m { font-size:8.5px; color:#8a95a1; margin-top:3px; font-family:Calibri,sans-serif; }
.reshist .rbar { border-radius:3px 3px 0 0; min-height:1px; }
.reshist .v { color:#17457a; }
.dt th.num, .dt td.num { text-align:center; }
.rescap { font-size:10px; color:#5b6472; margin:3px 0 9px; font-family:Calibri,sans-serif; }
.resload-fig { break-after:avoid; page-break-after:avoid; }
.wt ul{list-style:none;margin:0;padding-left:22px;}
.wt>ul{padding-left:0;}
.wt li{position:relative;padding:4px 0;}
.wt ul li::before{content:"";position:absolute;top:16px;left:-12px;width:12px;border-top:1.5px solid #9cbcdd;}
.wt ul li::after{content:"";position:absolute;top:0;left:-12px;height:100%;border-left:1.5px solid #9cbcdd;}
.wt ul li:last-child::after{height:16px;}
.wt .bx{display:inline-block;font-family:Calibri,sans-serif;font-weight:700;border-radius:5px;padding:5px 11px;font-size:10.5px;line-height:1.2;border:1px solid #9cbcdd;}
.wt .lv0{background:#1F4E79;color:#fff;border-color:#1F4E79;font-size:11.5px;padding:6px 14px;}
.wt .lv1{background:#BCD3EA;color:#12324d;}
.wt .lv2{background:#DEEAF6;color:#14324f;}
.wt .lv3{background:#eef4fb;color:#1f4e79;font-weight:600;}
.wt .lv4{background:#fff;color:#33414d;font-weight:400;border-color:#d3ddea;font-size:9.5px;}
.wt{break-inside:avoid;page-break-inside:avoid;}
.wsvg{margin:6px 0 14px;break-inside:avoid;page-break-inside:avoid;}
.wsvg svg{display:block;}
.codes { display:flex; gap:16px; margin-bottom:12px; }
.codes > div { flex:1; }
.ct { font-size:12px; font-weight:700; margin:0 0 5px; }
.codetbl { width:100%; font-size:11px; border-collapse:collapse; break-inside:avoid; page-break-inside:avoid; }
.codetbl th { background:#dbe5f1; border:1px solid #9fb2c8; padding:4px 7px; font-weight:700; color:#14324f; font-family:Calibri,sans-serif; font-size:10px; }
.codetbl td { border:1px solid #b9c6d3; padding:3px 8px; }
.codetbl td.cv { text-align:center; font-weight:600; }
.cover-t { text-align:center; }
/* §12 Activity IDs — role-coloured anatomy + per-type breakdown (twins the native Word §12) */
.actidblk { break-inside:avoid; page-break-inside:avoid; }
.actidtbl { border-collapse:collapse; table-layout:fixed; width:100%; margin:6px 0 4px; break-inside:avoid; page-break-inside:avoid; }
.actidtbl td { border:1px solid #9DB2C6; text-align:center; padding:5px 7px; vertical-align:middle; word-wrap:break-word; overflow-wrap:break-word; }
.actidtbl td.acode { color:#fff; font-weight:700; font-family:Calibri,sans-serif; font-size:11px; }
.actidtbl td.amean { color:#14324f; font-size:9.5px; line-height:1.3; }
.actidex { font-family:Calibri,sans-serif; font-weight:700; color:#1F4E79; font-size:12px; margin:6px 0 3px; }
.actidbox { display:table; margin:6px auto 4px; border:1.4px solid #1F4E79; background:#EEF3F9; color:#1F4E79; font-family:Calibri,sans-serif; font-weight:700; font-size:13px; padding:6px 18px; text-align:center; break-inside:avoid; page-break-inside:avoid; }
.actidlegend { margin:8px 0 6px; }
.actidchip { display:inline-block; width:11px; height:11px; margin:0 5px 0 8px; vertical-align:middle; border-radius:2px; }
.actidlbl { font-size:11px; color:#4A5560; margin-right:6px; vertical-align:middle; }
.actidnote { color:#1F7A3D; font-style:italic; font-size:11px; margin:4px 0 12px; }
@media print { body { background:#fff; } }
"""
