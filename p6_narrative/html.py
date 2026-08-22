"""Render the Baseline Narrative Report (a :class:`NarrativeDoc` dict) to HTML.

Used both for the on-screen tab and as the source for the PDF export (Chrome →
PDF via :func:`page_html`). One renderer, one visual spec, so Preview == PDF.

This renderer draws STRAIGHT FROM THE DOC MODEL — every number, name, tree node,
sequence step and edge is taken as-is from the payload; nothing is re-derived here.
The producer (:mod:`p6_narrative.report`) now emits the FULL professional section
set. The section KINDS handled here, and their payload shapes, are:

  overview   {paragraphs:[str], breakdown:[{world,count}], total, worldlist}   (v5)
  keyvals    {rows:[{k,v}]}
  ms_table   {columns, rows:[[name, date_str], …]}                             (v5)
  timeline   {items:[{label, date, milestone?}]}
  value      {total, rows:[{name, cost, pct}]}
  scope      {intro, blocks:[{discipline, activity_count, cost, paragraph,
                              packages:[str]}], stats:[{v, l}]}                 (editable)
  table      {columns, rows:[[…]]}  ·  or calendars view:
             {view:'calendars', calendars:[{name,working_days,shift,activities}],
              holidays:[{range,name,days}]}
  wbs_tree   {worlds:[{name, layout:'tree'|'columns', root:node}]}             (v5)
             node = {name, children:[node,…], more?:bool}
  codes      {tables:[{dimension, rows:[{code, description}]}]}
  idanatomy  {segments:[{value, label}], id}
  seq        {worlds:[{world, fronts:[{title, sequence:[str], instances:[str],
                              activities:[{id,name,wbs}]}]}]}                   (v5, editable)
  interfaces {macro:[world,…], notes:[str], edges:[[a,b], …]}                   (v5)
  prose      {paragraphs:[str], bullets?:[str]}
  costbars   {rows:[{name, pct}]}
  cashflow   {points:[{pct}]}
  image      {image: dataURL}

── Shared formatting spec (NARRATIVE_RECONCILIATION.md §B) ────────────────────
A4 portrait, ~2 cm margins, one font family (Segoe UI / Calibri), navy numbered
H1 section headings + H2 sub-headings, tables with a navy header row + thin
borders + zebra rows. See ``_CSS`` and the print notes below.

── Per-page furniture (issues #2/#4/#5) ──────────────────────────────────────
The document body is wrapped in a single ``<table class="n-doc">`` whose
``<thead>`` (logo/title band) and ``<tfoot>`` (footer band) Chrome REPEATS on
every printed page and reserves space for — so nothing overlaps. A separate
``position:fixed; inset:0`` ``.n-frame`` element draws the page border: fixed
boxes are repainted inside the page area on every Chrome-printed page, so the
frame appears on every page and can never overflow onto the next one, even when
a section straddles a page break. Page numbers: Chrome does not expose
``counter(page)`` to normal/fixed elements (only to ``@page`` margin boxes, which
Chrome does not render), so the footer carries a clearly-marked ``[[PAGE]]`` /
``[[PAGES]]`` placeholder the caller's Chrome print step can fill (or overlay via
``displayHeaderFooter`` + a ``footerTemplate`` — the ``@page`` margin leaves room).

Editable prose (overview paragraphs, scope paragraphs, any ``editable`` section)
carries ``data-section`` / ``data-field`` / ``data-editable`` hooks; sequence
packages keep ``.fl-box`` and front titles keep ``.fr-title`` so a later UI layer
can wire inline editing. No JS is emitted.
"""
import html as _h


def _esc(x):
    return _h.escape('' if x is None else str(x))


def _money(v):
    try:
        return f'{float(v):,.0f}'
    except (TypeError, ValueError):
        return _esc(v)


# ── WBS nodes (v5) ────────────────────────────────────────────────────────────
def _topdown_node(node, depth=0):
    """Small WBS: a centred top-down org-chart node (CSS ``.tree`` connectors).

    Renders the EXACT P6 hierarchy at full depth; a node's children sit under IT,
    so no false parent/sibling relationship is ever implied. ``more`` → muted chip.
    """
    name = _esc(node.get('name'))
    if node.get('more'):
        return '<div class="wt-box wt-more">%s</div>' % name
    cls = 'wt-root' if depth == 0 else ('wt-l1' if depth == 1 else 'wt-n')
    out = '<div class="wt-box %s">%s</div>' % (cls, name)
    kids = node.get('children') or []
    if kids:
        lis = ''.join('<li>%s</li>' % _topdown_node(k, depth + 1) for k in kids)
        out += '<ul>%s</ul>' % lis
    return out


def _indented_node(node, depth=1):
    """Large WBS: one compact indented column entry (CSS ``.it-list`` guides).

    Full depth, exact parent→child via the nested ``<ul>`` guides. ``more`` → muted.
    """
    name = _esc(node.get('name'))
    if node.get('more'):
        return '<span class="it-box it-more">%s</span>' % name
    cls = 'it-l1' if depth == 1 else 'it-n'
    out = '<span class="it-box %s">%s</span>' % (cls, name)
    kids = node.get('children') or []
    if kids:
        lis = ''
        for k in kids:
            if k.get('more'):
                lis += '<li class="it-more">%s</li>' % _esc(k.get('name'))
            else:
                lis += '<li>%s</li>' % _indented_node(k, depth + 1)
        out += '<ul class="it-list">%s</ul>' % lis
    return out


# ── flow chart (package sequence / macro flow) ───────────────────────────────
def _flow(seq):
    if not seq:
        return '<span class="muted">— derived from schedule logic —</span>'
    boxes = ' <span class="fl-arr">▶</span> '.join(
        '<span class="fl-box">%s</span>' % _esc(s) for s in seq)
    return '<div class="flow">%s</div>' % boxes


# ── overview (v5) ─────────────────────────────────────────────────────────────
def _overview(p, number):
    paras = ''.join(
        '<p data-section="%s" data-field="paragraphs.%d" data-editable="1">%s</p>'
        % (_esc(number), i, _esc(t)) for i, t in enumerate(p.get('paragraphs') or []))
    breakdown = p.get('breakdown') or []
    cards = ''.join(
        '<div class="stat"><div class="stat-n">%s</div><div class="stat-l">%s</div></div>'
        % (_esc(b.get('count')), _esc(b.get('world'))) for b in breakdown)
    return ('%s'
            '<div class="subh">Baseline composition</div>'
            '<div class="stats">%s</div>'
            '<div class="total">Total: <b>%s</b> baseline activities across %d major scopes.</div>'
            % (paras, cards, _esc(p.get('total')), len(breakdown)))


# ── milestones (v5) ───────────────────────────────────────────────────────────
def _ms_table(p, number):
    cols = p.get('columns') or ['Milestone', 'Date']
    head = ''.join('<th>%s</th>' % _esc(c) for c in cols)
    rows = p.get('rows') or []
    body = ''.join('<tr><td>%s</td><td class="ms-d">%s</td></tr>'
                   % (_esc(r[0] if len(r) > 0 else ''), _esc(r[1] if len(r) > 1 else ''))
                   for r in rows)
    if not body:
        body = ('<tr><td colspan="%d" class="muted">no finish milestones defined</td></tr>'
                % max(len(cols), 1))
    return ('<p class="lead">Key completion and control milestones from the baseline.</p>'
            '<table class="n-t ms-table"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>'
            % (head, body))


# ── WBS — ADAPTIVE (v5) ───────────────────────────────────────────────────────
def _wbs_tree(p, number):
    charts = []
    for w in p.get('worlds') or []:
        root = w.get('root') or {}
        if w.get('layout') == 'columns':                 # large → compact multi-column tree
            cols = ''.join('<div class="wbs-col">%s</div>' % _indented_node(c, 1)
                           for c in (root.get('children') or []))
            charts.append('<div class="wbs-lg"><div class="wt-box wt-root">%s</div>'
                          '<div class="wbs-cols">%s</div></div>'
                          % (_esc(root.get('name') or w.get('name')), cols))
        else:                                            # small → centred top-down tree
            charts.append('<div class="tree"><ul><li>%s</li></ul></div>' % _topdown_node(root, 0))
    return ('<p class="lead">The actual P6 breakdown of each scope — Project → Main WBS '
            '→ Sub-WBS → Trade/Discipline → Package. Small scopes render as a '
            'centered tree; large scopes as a compact multi-column tree — the layout adapts to '
            'fit the page (no horizontal scrolling). This view shows how the project is '
            'organised; the execution order is in the Sequence of Work section.</p>'
            '%s' % ''.join(charts))


# ── Sequence of Work (v5) ─────────────────────────────────────────────────────
def _seq(p, number):
    blocks = []
    for w in p.get('worlds') or []:
        fronts = []
        for f in w.get('fronts') or []:
            insts = f.get('instances') or []
            applies = ''
            if len(insts) >= 2:
                shown = ' · '.join(_esc(i) for i in insts[:14])
                if len(insts) > 14:
                    shown += ' <span class="muted">+%d more</span>' % (len(insts) - 14)
                applies = '<div class="fr-meta">Applies to: %s</div>' % shown
            acts = ''.join('<tr><td class="mono">%s</td><td>%s</td><td class="muted">%s</td></tr>'
                           % (_esc(a.get('id')), _esc(a.get('name')), _esc(a.get('wbs')))
                           for a in (f.get('activities') or []))
            fronts.append(
                '<div class="front" data-section="%s" data-editable="1">'
                '<div class="fr-title">%s</div>%s%s'
                '<details><summary>P6 activities</summary>'
                '<table class="n-t"><thead><tr><th>ID</th><th>Activity</th><th>WBS</th></tr></thead>'
                '<tbody>%s</tbody></table></details></div>'
                % (_esc(number), _esc(f.get('title') or 'front'),
                   _flow(f.get('sequence') or []), applies, acts))
        blocks.append('<h2 class="subh2">%s</h2>%s' % (_esc(w.get('world')), ''.join(fronts)))
    return ('<p class="lead">How each scope is executed, at the major work-package level. The '
            'sequence is derived from the schedule’s own logic; the underlying P6 '
            'activities are available on demand under each block.</p>'
            '%s' % ''.join(blocks))


# ── Interfaces & Dependencies (v5) ────────────────────────────────────────────
def _interfaces(p, number):
    macro = ' <span class="fl-arr">▶</span> '.join(
        '<span class="fl-box world">%s</span>' % _esc(x) for x in (p.get('macro') or []))
    notes = ''.join('<li>%s</li>' % _esc(n) for n in (p.get('notes') or []))
    edges = ''.join('<li><b>%s</b> <span class="fl-arr">▶</span> <b>%s</b></li>'
                    % (_esc(e[0] if len(e) > 0 else ''), _esc(e[1] if len(e) > 1 else ''))
                    for e in (p.get('edges') or []))
    if not edges:
        edges = '<li class="muted">no strong cross-front dependencies detected</li>'
    return ('<p class="lead">How the major scopes interact and hand off to each other.</p>'
            '<div class="subh">Macro execution flow</div><div class="flow">%s</div>'
            '<ul class="notes">%s</ul>'
            '<div class="subh">Key building / front dependencies</div>'
            '<ul class="edges">%s</ul>' % (macro, notes, edges))


# ── prose (restored) ──────────────────────────────────────────────────────────
def _prose(p, number):
    out = ''.join('<p>%s</p>' % _esc(t) for t in (p.get('paragraphs') or []))
    if p.get('bullets'):
        out += '<ul class="bn-bul">%s</ul>' % ''.join('<li>%s</li>' % _esc(b)
                                                      for b in p['bullets'])
    return out or '<p class="bn-empty">—</p>'


# ── keyvals (restored) ────────────────────────────────────────────────────────
def _keyvals(p, number):
    rows = ''.join('<tr><td class="bn-k">%s</td><td>%s</td></tr>'
                   % (_esc(r.get('k')), _esc(r.get('v'))) for r in (p.get('rows') or []))
    if not rows:
        rows = '<tr><td colspan="2" class="bn-empty">—</td></tr>'
    return '<div class="bn-tw"><table class="n-t bn-t">%s</table></div>' % rows


# ── table (restored) ──────────────────────────────────────────────────────────
def _table(p, number):
    cols = ''.join('<th>%s</th>' % _esc(c) for c in (p.get('columns') or []))
    body = ''.join('<tr>%s</tr>' % ''.join('<td>%s</td>' % _esc(c) for c in row)
                   for row in (p.get('rows') or []))
    if not body:
        body = ('<tr><td colspan="%d" class="bn-empty">—</td></tr>'
                % max(len(p.get('columns') or []), 1))
    head = '<thead><tr>%s</tr></thead>' % cols if cols else ''
    return '<div class="bn-tw"><table class="n-t bn-t">%s<tbody>%s</tbody></table></div>' % (head, body)


# ── calendars view (restored — dispatched from kind 'table') ──────────────────
def _calendars(p, number):
    crows = ''.join(
        '<tr><td>%s</td><td>%s</td><td>%s</td><td class="bn-num">%s</td></tr>'
        % (_esc(c.get('name')), _esc(c.get('working_days')), _esc(c.get('shift')),
           _esc(c.get('activities'))) for c in (p.get('calendars') or []))
    cal = ('<div class="bn-tw"><table class="n-t bn-t"><thead><tr><th>Calendar</th>'
           '<th>Working days</th><th>Shift</th><th>Assigned</th></tr></thead>'
           '<tbody>%s</tbody></table></div>' % crows)
    hols = p.get('holidays') or []
    if hols:
        hrows = ''.join(
            '<tr><td>%s</td><td>%s</td><td class="bn-num">%s</td></tr>'
            % (_esc(h.get('range')), _esc(h.get('name')), _esc(h.get('days'))) for h in hols)
        cal += ('<div class="bn-cap">Holidays &amp; shutdowns (named in Calendar Audit):</div>'
                '<div class="bn-tw"><table class="n-t bn-t"><thead><tr><th>When</th><th>Name</th>'
                '<th>Days</th></tr></thead><tbody>%s</tbody></table></div>' % hrows)
    return cal


# ── codes (restored) ──────────────────────────────────────────────────────────
def _codes(p, number):
    cards = ''
    for t in (p.get('tables') or []):
        rows = ''.join('<tr><td class="bn-code">%s</td><td>%s</td></tr>'
                       % (_esc(r.get('code')), _esc(r.get('description')))
                       for r in (t.get('rows') or []))
        cards += ('<div class="bn-codecard"><h4>%s</h4>'
                  '<div class="bn-tw"><table class="n-t bn-t"><thead><tr><th>Code</th>'
                  '<th>Description</th></tr></thead><tbody>%s</tbody></table></div></div>'
                  % (_esc(t.get('dimension')), rows))
    return ('<div class="bn-codes">%s</div>'
            % (cards or '<p class="bn-empty">No activity codes in the file.</p>'))


# ── costbars (restored) ───────────────────────────────────────────────────────
def _costbars(p, number):
    rows = ''
    for r in (p.get('rows') or []):
        pct = r.get('pct') or 0
        rows += ('<div class="bn-bar"><span class="bn-bn">%s</span>'
                 '<span class="bn-track"><span class="bn-fill" style="width:%s%%"></span></span>'
                 '<span class="bn-bv">%s%%</span></div>'
                 % (_esc(r.get('name')), pct, pct))
    return '<div class="bn-bars">%s</div>' % (rows or '<p class="bn-empty">—</p>')


# ── cashflow (restored) ───────────────────────────────────────────────────────
def _cashflow(p, number):
    pts = p.get('points') or []
    if not pts:
        return '<p class="bn-empty">No cost loading in the file.</p>'
    w, h = 680, 200
    n = len(pts) - 1 or 1
    coords = [(40 + i * (w - 60) / n, h - 20 - ((pt.get('pct') or 0) / 100.0) * (h - 40))
              for i, pt in enumerate(pts)]
    line = ' '.join('%.1f,%.1f' % (x, y) for x, y in coords)
    area = '40,%d %s %.1f,%d' % (h - 20, line, coords[-1][0], h - 20)
    lx, ly = coords[-1]
    return ('<div class="bn-tw"><svg class="bn-svg" viewBox="0 0 %d %d" preserveAspectRatio="xMidYMid meet">'
            '<line x1="40" y1="%d" x2="%d" y2="%d" class="bn-axis"/>'
            '<line x1="40" y1="20" x2="40" y2="%d" class="bn-axis"/>'
            '<polygon points="%s" class="bn-area"/>'
            '<polyline points="%s" class="bn-line"/>'
            '<circle cx="%.1f" cy="%.1f" r="4" class="bn-dot"/>'
            '<text x="36" y="24" text-anchor="end" class="bn-axl">100%%</text>'
            '<text x="36" y="%d" text-anchor="end" class="bn-axl">0</text></svg></div>'
            % (w, h, h - 20, w - 20, h - 20, h - 20, area, line, lx, ly, h - 16))


# ── scope (restored — editable prose) ─────────────────────────────────────────
def _scope(p, number):
    out = ''
    stats = p.get('stats') or []
    if stats:
        cards = ''.join('<div class="bn-statc"><div class="bn-statv">%s</div>'
                        '<div class="bn-statl">%s</div></div>'
                        % (_esc(s.get('v')), _esc(s.get('l'))) for s in stats)
        out += ('<div class="bn-statwrap"><div class="bn-stath">Project scope at a glance</div>'
                '<div class="bn-stats">%s</div></div>' % cards)
    if p.get('intro'):
        out += ('<p data-section="%s" data-field="scope.intro" data-editable="1">%s</p>'
                % (_esc(number), _esc(p.get('intro'))))
    for i, b in enumerate(p.get('blocks') or []):
        bullets = ''.join('<li><b>%s</b></li>' % _esc(x) for x in (b.get('packages') or []))
        cost = ''
        if b.get('cost'):
            try:
                cost = ' · %s' % _money(b.get('cost'))
            except (TypeError, ValueError):
                cost = ''
        out += ('<div class="bn-disc"><div class="bn-disch">%s'
                '<span class="bn-discm">%s activities%s</span></div>'
                '<p data-section="%s" data-field="scope.block.%d" data-editable="1">%s</p>%s</div>'
                % (_esc(b.get('discipline')), _esc(b.get('activity_count', 0)), _esc(cost),
                   _esc(number), i, _esc(b.get('paragraph', '')),
                   ('<ul class="bn-scopeul">%s</ul>' % bullets) if bullets else ''))
    return out or '<p class="bn-empty">—</p>'


# ── image (restored) ──────────────────────────────────────────────────────────
def _image(p, number):
    img = p.get('image')
    if img:
        return ('<div class="bn-tw"><img src="%s" alt="Project layout" '
                'style="max-width:100%%;border:1px solid var(--line);border-radius:8px"/></div>'
                % _esc(img))
    return '<p class="bn-empty">No layout image provided.</p>'


# ── timeline (restored) ───────────────────────────────────────────────────────
def _timeline(p, number):
    items = p.get('items') or []
    if not items:
        return '<p class="bn-empty">No key dates in the file.</p>'
    n = len(items)
    W, H, y = max(130 * n, 400), 150, 75
    x0, x1 = 30, W - 30
    step = (x1 - x0) / max(n - 1, 1)
    body = '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#3487ae" stroke-width="2"/>' % (x0, y, x1, y)
    for i, it in enumerate(items):
        x = x0 + i * step
        up = (i % 2 == 0)
        col = '#3487ae' if it.get('milestone') else '#c98a2b'
        lab = (it.get('label') or '')[:18]
        body += ('<circle cx="%.0f" cy="%d" r="5.5" fill="%s"/>'
                 '<text x="%.0f" y="%d" text-anchor="middle" font-size="9.5" fill="#1a1d21">%s</text>'
                 '<text x="%.0f" y="%d" text-anchor="middle" font-size="9" fill="#8a9099">%s</text>'
                 % (x, y, col, x, (y - 14 if up else y + 26), _esc(lab),
                    x, (y - 28 if up else y + 40), _esc(it.get('date'))))
    return ('<div class="bn-tw"><svg viewBox="0 0 %d %d" style="width:100%%;'
            'min-width:%dpx;height:auto">%s</svg></div>'
            % (int(W), H, min(int(W), 740), body))


# ── value (restored — donut + table) ──────────────────────────────────────────
def _value(p, number):
    import math
    rows = p.get('rows') or []
    if not rows:
        return '<p class="bn-empty">No cost loading in the file.</p>'
    palette = ['#1f5fa8', '#c98a2b', '#7a5aa6', '#4b9d6e', '#a35d5d', '#5a8fb0']
    circ = 2 * math.pi * 42
    off, segs = 0.0, ''
    for i, r in enumerate(rows):
        seg = circ * (r.get('pct') or 0) / 100.0
        segs += ('<circle cx="90" cy="90" r="42" fill="none" stroke="%s" stroke-width="24" '
                 'stroke-dasharray="%.1f %.1f" stroke-dashoffset="%.1f"/>'
                 % (palette[i % len(palette)], seg, circ - seg, -off))
        off += seg
    donut = ('<svg viewBox="0 0 180 180" style="width:168px;height:auto"><g transform="rotate(-90 90 90)">%s</g>'
             '<text x="90" y="86" text-anchor="middle" font-size="15" font-weight="700" fill="#1a1d21">%s</text>'
             '<text x="90" y="102" text-anchor="middle" font-size="9" fill="#8a9099">total</text></svg>'
             % (segs, _money(p.get('total'))))
    trows = ''.join('<tr><td>%s</td><td class="bn-num">%s</td><td class="bn-num">%s%%</td></tr>'
                    % (_esc(r.get('name')), _money(r.get('cost')), _esc(r.get('pct')))
                    for r in rows)
    tbl = ('<div class="bn-tw"><table class="n-t bn-t"><thead><tr><th>Branch</th><th>Cost</th>'
           '<th>%%</th></tr></thead><tbody>%s</tbody></table></div>' % trows)
    return ('<div class="bn-value">%s<div style="display:grid;place-items:center">%s</div></div>'
            % (tbl, donut))


# ── idanatomy (restored) ──────────────────────────────────────────────────────
def _idanatomy(p, number):
    segs = p.get('segments') or []
    if not segs:
        return '<p class="bn-empty">No decodable activity IDs in the file.</p>'
    palette = ['#265f7e', '#3487ae', '#5aa0c4', '#89bdd9', '#a9d0e3']
    n = len(segs)
    cells = ''
    for i, s in enumerate(segs):
        col = palette[min(i, len(palette) - 1)]
        rad = ('border-radius:6px 0 0 6px;' if i == 0
               else ('border-radius:0 6px 6px 0;' if i == n - 1 else ''))
        tcol = '#fff' if i < 3 else '#12303d'
        cells += ('<div style="background:%s;color:%s;padding:8px 12px;text-align:center;%s">'
                  '<div style="font-family:Consolas,monospace;font-size:14px;font-weight:700">%s</div>'
                  '<div style="font-size:9px;opacity:.9">%s</div></div>'
                  % (col, tcol, rad, _esc(s.get('value')), _esc(s.get('label'))))
    return ('<div class="bn-tw"><div style="display:flex;min-width:min-content">%s</div></div>'
            '<div class="bn-cap-inline">Example decoded: <code>%s</code></div>'
            % (cells, _esc(p.get('id'))))


_RENDER = {
    # v5 kinds
    'overview': _overview, 'ms_table': _ms_table, 'wbs_tree': _wbs_tree,
    'seq': _seq, 'interfaces': _interfaces,
    # restored kinds
    'prose': _prose, 'keyvals': _keyvals, 'table': _table, 'codes': _codes,
    'costbars': _costbars, 'cashflow': _cashflow, 'scope': _scope, 'image': _image,
    'timeline': _timeline, 'value': _value, 'idanatomy': _idanatomy,
}


def _heading(number, title):
    return '<h1 class="sec-h"><span class="num">%s</span> %s</h1>' % (_esc(number), _esc(title))


def _section(s, seq_style=None):
    number = s.get('number', '')
    title = s.get('title', '')
    kind = s.get('kind', '')
    payload = s.get('payload') or {}
    if kind == 'table' and payload.get('view') == 'calendars':      # calendars come through as 'table'
        body = _calendars(payload, number)
    else:
        render = _RENDER.get(kind)
        body = render(payload, number) if render else ''
    edit = ' data-editable="1"' if s.get('editable') else ''
    return ('<section class="sec" data-section="%s"%s>%s%s</section>'
            % (_esc(number), edit, _heading(number, title), body))


def _header_band(meta, project):
    """Repeating (thead) band — the three party logos when present, else a title band."""
    logos = (meta or {}).get('logos') or {}
    if logos:
        cells = ''
        for k in ('owner', 'consultant', 'contractor'):
            src = logos.get(k)
            cells += ('<td class="n-logocell">%s</td>'
                      % (('<img src="%s" alt="%s logo"/>' % (_esc(src), _esc(k))) if src else ''))
        return '<div class="n-head n-head-logos"><table class="n-logos"><tr>%s</tr></table></div>' % cells
    return ('<div class="n-head n-head-title">'
            '<span class="n-head-kicker">Baseline Schedule — Narrative Report</span>'
            '<span class="n-head-proj">%s</span></div>' % project)


def _footer_band(project):
    """Repeating (tfoot) branding band. The live 'Page X of Y' is rendered by the CSS
    ``@page`` bottom-centre counter (this Chrome DOES honour @page margin-box counters),
    so no placeholder is needed here."""
    return ('<div class="n-foot">'
            '<span class="n-foot-l">%s · Narrative Report</span>'
            '<span class="n-foot-c">prepared from the P6 baseline</span>'
            '<span class="n-foot-r">Baseline Schedule</span>'
            '</div>' % project)


def _cover(meta, project):
    """In-flow cover block — shown once at the top of page one."""
    parties = []
    for k, lbl in (('owner', 'Owner'), ('consultant', 'Consultant'), ('contractor', 'Contractor')):
        if meta.get(k):
            parties.append('%s: %s' % (lbl, _esc(meta[k])))
    meta_line = ' · '.join(parties)
    dd = meta.get('data_date')
    if dd:
        meta_line += ('%sBaseline data date: %s'
                      % (' · ' if meta_line else '', _esc(dd)))
    return ('<div class="cover">'
            '<div class="cover-kicker">Baseline Schedule — Narrative Report</div>'
            '<div class="cover-title">%s</div>'
            '%s</div>'
            % (project, ('<div class="cover-meta">%s</div>' % meta_line) if meta_line else ''))


def render_narrative_html(doc, seq_style=None):
    """Render the narrative ``doc`` (dict) to a self-contained HTML string.

    ``seq_style`` is accepted for signature compatibility with the export path; the
    current report has a single sequence layout (the package flow), so it is unused.
    """
    doc = doc or {}
    meta = doc.get('meta') or {}
    project = _esc(meta.get('project_name') or 'Project')
    inner = ''.join(_section(s, seq_style) for s in (doc.get('sections') or []))
    # One table wraps the whole body: Chrome repeats <thead>/<tfoot> on every printed
    # page AND reserves their height, so the running header/footer never overlap content.
    body_table = ('<table class="n-doc">'
                  '<thead><tr><td class="n-head-cell">%s</td></tr></thead>'
                  '<tbody><tr><td class="n-main">%s%s</td></tr></tbody>'
                  '<tfoot><tr><td class="n-foot-cell">%s</td></tr></tfoot>'
                  '</table>'
                  % (_header_band(meta, project), _cover(meta, project), inner,
                     _footer_band(project)))
    page = ('<div class="n-page">'
            '<div class="n-frame" aria-hidden="true"></div>'  # fixed → repeats + frames every printed page
            '%s</div>' % body_table)
    return '<style>%s</style>%s' % (_CSS, page)


def page_html(doc):
    """Full standalone HTML page (Chrome → PDF source)."""
    return ('<!doctype html><html><head><meta charset="utf-8">'
            '<style>html,body{margin:0;padding:0;background:#fff}</style></head><body>'
            + render_narrative_html(doc) + '</body></html>')


# ── Shared formatting spec (§B): A4 portrait · ~2 cm margins · one font family ·
#    navy numbered H1 + H2 · navy-header/zebra/thin-border tables · page frame +
#    running header/footer on every page. ────────────────────────────────────
_CSS = """
:root{
  --navy:#1f3b63;      /* headings, header rows, badges, frame */
  --navy2:#2a4d7a;
  --ink:#1f2733;       /* body text */
  --mut:#6b7480;       /* secondary text */
  --line:#d7dde5;      /* thin borders */
  --accent:#1f5fa8;    /* links / flow chips */
  --accent2:#2c7a4b;
  --band:#f4f6f9;      /* light fills */
  --zebra:#f6f8fb;     /* table zebra */
  --chip:#eef3f8;
  --paper:#fff;
}
*{box-sizing:border-box}
html,body{margin:0}
body{background:#e9ecf1;color:var(--ink);
  font-family:"Segoe UI",Calibri,"Helvetica Neue",Arial,sans-serif;
  font-size:10.5pt;line-height:1.5;padding:24px;}

/* ── the "paper" (screen) ── */
.n-page{position:relative;max-width:900px;margin:0 auto;background:var(--paper);
  border:1.6px solid var(--navy);box-shadow:0 3px 22px rgba(0,0,0,.14);}
.n-page::before{content:"";position:absolute;inset:6px;border:1px solid var(--line);
  pointer-events:none;z-index:2;}
.n-frame{display:none;}                       /* print-only page frame (see @media print) */

/* ── the wrapping table: thead=header band, tfoot=footer band (repeat per page) ── */
.n-doc{width:100%;border-collapse:collapse;table-layout:fixed;}
.n-doc>thead,.n-doc>tfoot{display:table-header-group;}   /* header/footer groups */
.n-doc>tfoot{display:table-footer-group;}
.n-head-cell{padding:16px 42px 0;}
.n-main{padding:6px 42px 8px;vertical-align:top;}
.n-foot-cell{padding:0 42px 14px;}

/* ── running header band ── */
.n-head{border-bottom:2px solid var(--navy);padding-bottom:8px;margin-bottom:4px;}
.n-head-logos .n-logos{width:100%;border-collapse:collapse;table-layout:fixed;}
.n-head-logos .n-logocell{width:33.33%;text-align:center;vertical-align:middle;padding:2px 8px;}
.n-head-logos .n-logocell img{max-height:46px;max-width:160px;object-fit:contain;}
.n-head-title{display:flex;align-items:baseline;justify-content:space-between;gap:14px;}
.n-head-kicker{letter-spacing:.12em;text-transform:uppercase;font-size:8.5pt;color:var(--navy);font-weight:700;}
.n-head-proj{font-size:10pt;font-weight:600;color:var(--mut);text-align:right;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}

/* ── running footer band ── */
.n-foot{display:flex;align-items:center;justify-content:space-between;gap:12px;
  border-top:1px solid var(--line);padding-top:8px;color:var(--mut);font-size:8.5pt;}
.n-foot-c{flex:1;text-align:center;}
.n-foot-r{white-space:nowrap;}
.n-pph{color:var(--mut);font-style:italic;}   /* clearly-marked page-number placeholder */

/* ── cover (page 1, in flow) ── */
.cover{border-bottom:3px double var(--navy);padding:8px 0 18px;margin-bottom:6px;}
.cover-kicker{letter-spacing:.16em;text-transform:uppercase;font-size:8.5pt;color:var(--accent);font-weight:700;}
.cover-title{font-size:26pt;font-weight:800;margin:6px 0 4px;letter-spacing:-.01em;color:var(--navy);line-height:1.1;}
.cover-meta{font-size:9.5pt;color:var(--mut);}

/* ── section headings (H1) + sub-headings (H2) ── */
.sec{margin:0;}
.sec-h{font-size:15pt;font-weight:800;color:var(--navy);margin:24px 0 10px;
  border-bottom:1px solid var(--line);padding-bottom:6px;break-after:avoid;line-height:1.25;}
.sec-h .num{display:inline-block;background:var(--navy);color:#fff;border-radius:5px;
  padding:1px 9px;margin-right:9px;font-size:12pt;font-weight:700;}
.subh{font-weight:700;font-size:9pt;text-transform:uppercase;letter-spacing:.05em;
  color:var(--mut);margin:16px 0 7px;break-after:avoid;}
.subh2{font-size:12pt;font-weight:700;color:var(--navy2);margin:18px 0 6px;break-after:avoid;}
h4{font-size:10.5pt;color:var(--navy);margin:0 0 6px;}
p{margin:9px 0;}
.lead{color:var(--mut);font-size:10pt;margin:2px 0 12px;}
.muted,.bn-empty{color:var(--mut);}
.bn-empty{font-style:italic;}

/* ── tables (navy header · thin borders · zebra) ── */
.n-t{border-collapse:collapse;width:100%;margin:6px 0;font-size:9.5pt;}
.n-t thead th,.n-t th{background:var(--navy);color:#fff;text-align:left;font-weight:600;
  padding:7px 12px;border:1px solid var(--navy);font-size:9pt;}
.n-t td{padding:6px 12px;border:1px solid var(--line);vertical-align:top;}
.n-t tbody tr:nth-child(even) td{background:var(--zebra);}
.bn-tw{overflow-x:auto;margin:6px 0;}
.bn-k{color:var(--navy2);font-weight:600;white-space:nowrap;width:210px;}
.bn-num{text-align:right;font-variant-numeric:tabular-nums;}
.bn-code{font-family:Consolas,"Cascadia Code",monospace;font-size:9pt;color:var(--navy2);white-space:nowrap;}
.bn-cap{font-size:9pt;color:var(--mut);margin:10px 0 4px;}
.bn-bul{margin:4px 0 8px;padding-left:20px;}

/* milestones */
.ms-table .ms-d{color:var(--navy2);font-weight:600;white-space:nowrap;width:200px;}

/* overview stat cards */
.stats{display:flex;gap:12px;flex-wrap:wrap;}
.stat{flex:1;min-width:130px;background:var(--band);border:1px solid var(--line);border-radius:10px;
  padding:12px 16px;text-align:center;break-inside:avoid;}
.stat-n{font-size:20pt;font-weight:800;color:var(--navy);}
.stat-l{font-weight:600;font-size:10pt;color:var(--ink);}
.total{margin-top:12px;}

/* WBS — small: centred top-down org-chart (fits the page, no horizontal scroll) */
.tree{padding:22px 8px;margin:12px 0;background:var(--band);border:1px solid var(--line);border-radius:10px;break-inside:avoid;}
.tree ul{display:flex;flex-wrap:wrap;justify-content:center;padding-top:22px;position:relative;margin:0;list-style:none;}
.tree li{list-style:none;text-align:center;position:relative;padding:22px 10px 0;}
.tree li::before,.tree li::after{content:"";position:absolute;top:0;right:50%;width:50%;height:22px;border-top:2px solid #b7c1cf;}
.tree li::after{right:auto;left:50%;border-left:2px solid #b7c1cf;}
.tree li:only-child::before,.tree li:only-child::after{display:none;}
.tree li:first-child::before,.tree li:last-child::after{border:0;}
.tree li:last-child::before{border-right:2px solid #b7c1cf;}
.tree ul ul::before{content:"";position:absolute;top:0;left:50%;border-left:2px solid #b7c1cf;width:0;height:22px;}
.tree>li{padding-top:0;}
.wt-box{display:inline-block;border-radius:8px;padding:6px 13px;font-size:9.5pt;font-weight:600;}
.wt-root{background:var(--navy);color:#fff;font-size:10.5pt;}
.wt-l1{background:#fff;border:1.5px solid var(--navy);color:var(--navy);}
.wt-n{background:#fff;border:1px solid var(--line);color:var(--ink);font-weight:500;}
.wt-more{background:transparent;color:var(--mut);font-style:italic;font-weight:500;border:1px dashed var(--line);}

/* WBS — large: compact multi-column indented tree (wraps, never scrolls) */
.wbs-lg{padding:18px 16px;margin:12px 0;background:var(--band);border:1px solid var(--line);border-radius:10px;}
.wbs-lg .wt-root{display:block;width:max-content;max-width:100%;margin:0 auto 16px;text-align:center;}
.wbs-cols{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-start;}
.wbs-col{flex:1 1 240px;min-width:210px;background:#fff;border:1px solid var(--line);border-radius:9px;padding:11px 14px;break-inside:avoid;}
.it-box{font-size:9.5pt;}
.it-l1{font-weight:700;color:var(--navy);}
.it-n{color:var(--ink);font-weight:500;}
.it-list{list-style:none;margin:5px 0 0;padding-left:15px;position:relative;}
.it-list li{position:relative;padding:3px 0;}
.it-list li::before{content:"";position:absolute;left:-9px;top:0;height:13px;width:9px;border-left:1.5px solid #b7c1cf;border-bottom:1.5px solid #b7c1cf;}
.it-list li::after{content:"";position:absolute;left:-9px;top:13px;bottom:0;border-left:1.5px solid #b7c1cf;}
.it-list li:last-child::after{display:none;}
.it-more{color:var(--mut);font-style:italic;font-size:8.5pt;padding:3px 0;}

/* flow / sequence */
.flow{display:flex;flex-wrap:wrap;align-items:center;gap:5px;background:var(--band);
  border:1px solid var(--line);border-radius:8px;padding:9px 12px;margin:6px 0;}
.fl-box{background:var(--chip);border:1px solid #bcd0e6;color:var(--accent);border-radius:7px;
  padding:3px 11px;font-weight:600;font-size:9.5pt;white-space:nowrap;text-transform:capitalize;}
.fl-box.world{background:#e7f2ea;border-color:#b6d8c2;color:var(--accent2);}
.fl-arr{color:var(--mut);font-size:8.5pt;}
.notes{margin:8px 0;padding-left:20px;}
.notes li{margin:5px 0;}
.edges{margin:4px 0;padding-left:20px;}
.edges li{margin:3px 0;}
.front{border:1px solid var(--line);border-radius:9px;padding:11px 15px;margin:10px 0;background:#fff;break-inside:avoid;}
.fr-title{font-weight:700;font-size:10.5pt;text-transform:capitalize;margin-bottom:6px;color:var(--navy2);}
.fr-meta{color:var(--mut);font-size:9pt;margin:6px 0 0;}
details{margin-top:8px;}
summary{cursor:pointer;color:var(--accent);font-size:9pt;}
.mono{font-family:Consolas,ui-monospace,monospace;color:var(--mut);white-space:nowrap;}

/* codes */
.bn-codes{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;}
.bn-codecard{break-inside:avoid;}

/* cost bars */
.bn-bars{display:flex;flex-direction:column;gap:8px;}
.bn-bar{display:grid;grid-template-columns:170px 1fr 56px;gap:11px;align-items:center;font-size:10pt;}
.bn-bn{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.bn-track{height:13px;background:#e7ebf1;border-radius:4px;overflow:hidden;}
.bn-fill{display:block;height:100%;background:var(--accent);border-radius:4px;}
.bn-bv{text-align:right;font-variant-numeric:tabular-nums;color:var(--navy2);}

/* cash flow svg */
.bn-svg{width:100%;min-width:520px;height:auto;}
.bn-axis{stroke:var(--line);stroke-width:1;}
.bn-area{fill:#e7f0f5;}
.bn-line{fill:none;stroke:var(--accent);stroke-width:2.5;}
.bn-dot{fill:var(--accent);}
.bn-axl{fill:var(--mut);font-size:11px;}

/* scope */
.bn-statwrap{border:1px solid var(--line);border-radius:10px;overflow:hidden;margin:6px 0 12px;}
.bn-stath{background:#e7f0f5;color:var(--navy);font-weight:600;font-size:9pt;padding:6px 13px;}
.bn-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:9px;padding:12px;}
.bn-statc{background:var(--band);border-radius:8px;padding:9px 11px;break-inside:avoid;}
.bn-statv{font-size:15pt;font-weight:700;color:var(--navy);}
.bn-statl{font-size:8.5pt;color:var(--navy2);}
.bn-disc{border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;
  padding:11px 14px;margin:9px 0;break-inside:avoid;}
.bn-disch{font-size:11pt;font-weight:700;display:flex;justify-content:space-between;gap:8px;
  align-items:center;margin-bottom:5px;color:var(--navy2);}
.bn-discm{font-family:Consolas,monospace;font-size:8.5pt;color:var(--mut);font-weight:400;}
.bn-disc p{margin:0 0 8px;}
.bn-scopeul{margin:6px 0 2px;padding-left:22px;}
.bn-scopeul li{font-size:10pt;margin:3px 0;}
.bn-scopeul li b{font-weight:600;}

/* value donut */
.bn-value{display:grid;grid-template-columns:1fr 190px;gap:14px;align-items:center;}
@media(max-width:600px){.bn-value{grid-template-columns:1fr;}}

/* id anatomy */
.bn-cap-inline{font-size:8.5pt;color:var(--mut);margin:7px 0 0;}
.bn-cap-inline code{font-family:Consolas,monospace;color:var(--navy2);background:#e7f0f5;padding:1px 6px;border-radius:4px;}

/* editable affordance (no JS) */
[data-editable]{outline:1px dashed transparent;}

/* ── PRINT: A4 · ~2 cm margins · repeating page frame + header/footer ── */
@media print{
  /* ~2 cm effective text margin = 14 mm @page margin + 6 mm cell padding.
     The 14 mm @page margin defines the page area; the fixed .n-frame is
     inset:0 within it, so the border sits at ~1.4 cm on EVERY page and is
     repainted per page — it can never overflow onto the next page. */
  @page{size:A4 portrait;margin:14mm;
    @bottom-center{content:"Page " counter(page) " of " counter(pages);
      font:8.5pt "Segoe UI",Calibri,sans-serif;color:#5a6472;}}
  html,body{background:#fff;padding:0;}
  .n-page{max-width:none;margin:0;border:0;box-shadow:none;background:#fff;}
  .n-page::before{display:none;}
  .n-frame{display:block;position:fixed;top:0;left:0;right:0;bottom:0;
    border:1.4pt solid var(--navy);pointer-events:none;z-index:0;}
  .n-frame::after{content:"";position:absolute;top:3pt;left:3pt;right:3pt;bottom:3pt;
    border:.5pt solid var(--navy);}
  /* text/tables sit ~6 mm inside the frame */
  .n-head-cell{padding:5mm 6mm 0;}
  .n-main{padding:2mm 6mm 3mm;}
  .n-foot-cell{padding:0 6mm 3mm;}
  .cover-title{font-size:24pt;}
  /* stop wide SVG/table min-widths spilling past the frame */
  .bn-svg,.n-t,.bn-t{min-width:0;}
  .bn-tw{overflow:visible;}
  tr,.stat,.front,.bn-disc,.bn-statc,.bn-codecard,.wbs-col{break-inside:avoid;}
  .sec-h,.subh,.subh2{break-after:avoid;}
}
"""
