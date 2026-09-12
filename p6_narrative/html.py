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
  7  scope        {disciplines:[{name, pct, cost?}],
                   sections:[{discipline, buildings:[{name, elements:[str]}]}]}
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

_ARROW = '➢'         # ➢ building bullet
_CHECK = '✓'         # ✓ element bullet
_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _esc(x):
    return _h.escape('' if x is None else str(x))


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
        pct_over_fill = width >= 99.5
        pcls = ' style="color:#dbe6f2"' if pct_over_fill else ''
        out += ('<div class="bar"><div class="lab">%s</div>'
                '<div class="track"><div class="fill" style="width:%.4g%%">%s</div>'
                '<div class="pct"%s>%s%%</div></div></div>'
                % (_esc(r.get(name_key)), width, _esc(label), pcls, _fmt_pct(pct)))
    return out


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
        fig = ('<img src="%s" alt="%s" style="max-width:100%%;display:block;margin:0 auto;'
               'border:1px solid #b9c6d3;border-radius:6px">' % (_esc(img), _esc(cap)))
    else:
        fig = ('<div style="border:1px solid #b9c6d3;background:#f4f7fa;height:150px;'
               'display:flex;align-items:center;justify-content:center;color:#7a8794;'
               'font-style:italic;font-size:13px">[ site layout drawing ]</div>')
    return ('%s<div style="text-align:center;font-size:10.5px;color:#5a5f66;'
            'font-style:italic;margin-top:5px">Figure 1 &mdash; %s</div>' % (fig, _esc(cap)))


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
    banner = ('<div class="banner"><span class="l">Total Contract Value</span>'
              '<span class="v">%s</span></div>' % _fmt_full(p.get('total'), cur))
    bars = _bars(p.get('rows') or [], 'name', lambda r: _fmt_abbrev(r.get('amount'), cur))
    return ('<p>The contract value and its distribution by type of work (the discipline '
            'activity code), from cost loading.</p>%s%s' % (banner, bars))


# ── §7 Scope of Work ──────────────────────────────────────────────────────────
def _scope(p, number, title, meta, cur):
    cur = _currency_prefix(meta, p) or cur
    disciplines = p.get('disciplines') or []
    bars = _bars(disciplines, 'name',
                 lambda r: _fmt_abbrev(r.get('cost'), cur) if r.get('cost') else '')
    out = ('<p>The scope is summarised by discipline (share of contract value), then set '
           'out per building and element, read from the activity codes.</p>'
           '<div class="subblue">Scope by discipline &mdash; share of contract value</div>%s'
           % bars)
    for i, sec in enumerate(p.get('sections') or [], 1):
        disc = sec.get('discipline') or 'Works'
        out += ('<div class="subctr" data-section="%s" data-editable="1">%s.%d&nbsp;&nbsp;'
                'Detailed %s Scope of Work includes:&mdash;</div>'
                % (_esc(number), _esc(number), i, _esc(disc)))
        for b in sec.get('buildings') or []:
            out += ('<div class="arw"><span class="a">%s</span> %s</div>'
                    % (_ARROW, _esc(b.get('name'))))
            for el in b.get('elements') or []:
                out += ('<div class="chk"><span class="c">%s</span> %s</div>'
                        % (_CHECK, _esc(el)))
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
    return ('<div class="calname">%s%s</div><div class="hist">%s</div>'
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
    dash_block = '<div class="sub">8.1 &middot; Executive Dashboard</div>%s' % trows if trows else ''

    # 8.2 one stacked histogram per assigned calendar
    hists = ''.join(_cal_hist(c) for c in (p.get('calendars') or []))
    hist_block = ''
    if hists:
        legend = ('<div class="callegend"><span><i style="background:#1f7a3d"></i>Working days'
                  '</span><span><i style="background:#b23030"></i>Non-working days</span></div>')
        hist_block = ('<div class="sub">8.2 &middot; Calendar Timeline '
                      '<span style="font-weight:400;font-size:9.5px;color:#8a93a0;'
                      'text-transform:none;letter-spacing:0">&mdash; working vs non-working '
                      'days per month, for each calendar (from data date)</span></div>'
                      '%s%s' % (legend, hists))

    # 8.3 holidays (Date | Description only)
    hols = p.get('holidays') or []
    hol_block = ''
    if hols:
        hrows = ''.join('<tr><td>%s</td><td>%s</td></tr>'
                        % (_esc(h.get('date')), _esc(h.get('description'))) for h in hols)
        hol_block = ('<div class="sub">8.3 &middot; Holidays</div>'
                     '<table class="dt"><tr><th style="width:26%%">Date</th>'
                     '<th>Description</th></tr>%s</table>' % hrows)

    # 8.4 working-hours profile cards
    profs = p.get('hours_profiles') or []
    prof_block = ''
    if profs:
        cards = ''
        for pf in profs:
            sub = pf.get('sub') or pf.get('name') or ''
            cards += ('<div class="tile stat"><div class="n" style="font-size:13px">%s</div>'
                      '<div class="l">%s</div></div>' % (_esc(pf.get('hours')), _esc(sub)))
        prof_block = ('<div class="sub">8.4 &middot; Working Hours Profile</div>'
                      '<div class="tiles">%s</div>' % cards)

    return lead + dash_block + hist_block + hol_block + prof_block


# ── §9 Work Breakdown Structure ───────────────────────────────────────────────
def _wbs_tree(p, number, title, meta, cur):
    intro = ('<p>The project WBS is presented as an organisation chart, then each major '
             'branch is expanded &mdash; to Level 4 where a branch&rsquo;s Level-4 nodes '
             'are 4 or fewer, otherwise to Level 3.</p>')
    overview = p.get('overview') or {}
    boxes = ''.join('<div class="ocbox">%s</div>' % _esc(c.get('name'))
                    for c in (overview.get('children') or []))
    ov_block = ('<div class="sub">%s.1 &middot; WBS Overview</div>'
                '<div class="oc"><div class="ocroot">%s</div>'
                '<div class="ocbranch">%s</div></div>'
                % (_esc(number), _esc(overview.get('name')), boxes))

    branch_blocks = ''
    for i, br in enumerate(p.get('branches') or [], 1):
        cols = ''
        for col in br.get('columns') or []:
            l2name = col[0] if len(col) > 0 else ''
            l3list = col[1] if len(col) > 1 else []
            inner = '<div class="l2">%s</div>' % _esc(l2name)
            for l3 in l3list:
                l3name = l3[0] if len(l3) > 0 else ''
                l4names = l3[1] if len(l3) > 1 else []
                inner += '<div class="l3">%s</div>' % _esc(l3name)
                if l4names:
                    chips = ' '.join('<span class="l4">%s</span>' % _esc(x) for x in l4names)
                    inner += '<div style="text-align:center">%s</div>' % chips
            cols += '<div class="occol">%s</div>' % inner
        branch_blocks += ('<div class="sub">%s.%d &middot; %s &mdash; breakdown</div>'
                          '<div class="oc"><div class="ocroot">%s</div></div>'
                          '<div class="occols">%s</div>'
                          % (_esc(number), i + 1, _esc(br.get('name')),
                             _esc(br.get('name')), cols))
    return intro + ov_block + branch_blocks


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


_RENDER = {
    'overview': _overview,
    'image': _image,
    'keyvals': _keyvals,
    'ms_table': _ms_table,
    'value_bars': _value_bars,
    'scope': _scope,
    'wbs_tree': _wbs_tree,
    'codes': _codes,
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
    return _page(meta, head + body, footer)


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
                           'Work Breakdown Structure', 'Activity Codes')),
]


def _toc(meta, paged):
    """``paged`` = [(section, page_number), …] in body order."""
    grp_hdr = ('<div style="font-family:Calibri,sans-serif;font-size:11px;color:#8a95a1;'
               'font-weight:700;letter-spacing:.06em;margin:16px 0 5px;border-bottom:'
               '1px solid #e2e8ef;padding-bottom:3px">%s</div>')
    item = ('<div class="toc-i" style="display:flex;font-size:13px;padding:5px 0">'
            '<span style="color:#1F4E79;font-weight:700;width:34px">%s)</span>'
            '<span>%s</span><span style="flex:1;border-bottom:1.4px dotted #9aa4b0;'
            'margin:0 8px;transform:translateY(-4px)"></span><span>%s</span></div>')
    by_title = {s.get('title'): (s, pg) for s, pg in paged}
    used = set()
    out = ''
    for label, titles in _TOC_GROUPS:
        rows = ''
        for t in titles:
            if t in by_title:
                s, pg = by_title[t]
                used.add(t)
                rows += item % (_esc(s.get('number')), _esc(s.get('title')), pg)
        if rows:
            out += (grp_hdr % _h.escape(label)) + rows
    # any section not covered by a named group (defensive) → an "OTHER" trailer
    extra = ''
    for s, pg in paged:
        if s.get('title') not in used:
            extra += item % (_esc(s.get('number')), _esc(s.get('title')), pg)
    if extra:
        out += (grp_hdr % 'OTHER') + extra
    body = ('<div style="text-align:center;font-family:\'Calibri Light\',Calibri,sans-serif;'
            'color:#1F4E79;font-weight:700;font-size:24px;margin-bottom:6px">'
            'Table of Contents</div>'
            '<div style="height:2px;width:120px;background:#1F4E79;margin:0 auto 22px"></div>'
            '%s' % out)
    return _page(meta, body, '')


# ── public API ────────────────────────────────────────────────────────────────
def render_narrative_html(doc, seq_style=None):
    """Render the narrative ``doc`` (dict) to a self-contained HTML string.

    ``seq_style`` is accepted for signature compatibility with the export path; the
    redesigned report has a single fixed layout, so it is unused.
    """
    doc = doc or {}
    meta = doc.get('meta') or {}
    cur = _currency_prefix(meta)
    sections = [s for s in (doc.get('sections') or []) if s]
    paged = [(s, i) for i, s in enumerate(sections, 1)]     # body page numbering from 1

    pages = [_cover(meta), _toc(meta, paged)]
    for s, pg in paged:
        pages.append(_section_page(s, meta, cur, pg))
    return '<style>%s</style>%s' % (_CSS, ''.join(pages))


def page_html(doc):
    """Full standalone HTML page (Chrome → PDF source)."""
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<title>Baseline Narrative Report</title></head><body>'
            + render_narrative_html(doc) + '</body></html>')


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
h1.sec { font-family:'Calibri Light',Calibri,sans-serif; color:#1F4E79; font-weight:700; font-size:20px; margin:2px 0 12px; }
p { font-size:13px; line-height:1.55; margin:0 0 11px; }
.note { color:#9aa4b0; font-size:10.5px; font-style:italic; margin-top:10px; }
.sub { font-family:Calibri,sans-serif; font-size:12px; text-transform:uppercase; letter-spacing:1px; color:#17457a; border-bottom:1px solid #dbe1e8; padding-bottom:4px; margin:16px 0 12px; font-weight:700; }
.subblue { font-family:Calibri,sans-serif; font-size:11px; font-weight:700; color:#1F4E79; text-transform:uppercase; letter-spacing:.03em; margin:6px 0 8px; }
table { border-collapse: collapse; }
.kv { width:100%; font-size:12px; }
.kv td { border:1px solid #cbd8e2; padding:7px 11px; }
.kv td.k { width:36%; background:#eef3f9; color:#1F4E79; font-weight:700; }
.dt { width:100%; font-size:12px; }
.dt th { background:#26517d; color:#fff; text-align:left; padding:6px 9px; font-size:10.5px; font-family:Calibri,sans-serif; }
.dt td { border:1px solid #dbe3ec; padding:6px 9px; }
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
.banner { display:flex; justify-content:space-between; align-items:center; background:#1F4E79; color:#fff; border-radius:6px; padding:9px 14px; margin-bottom:12px; font-family:Calibri,sans-serif; }
.banner .l { font-size:11px; letter-spacing:.03em; text-transform:uppercase; }
.banner .v { font-size:18px; font-weight:800; }
.subctr { text-align:center; font-weight:700; font-size:13px; color:#14324f; text-decoration:underline; margin:14px 0 9px; }
.arw { font-size:13px; font-weight:700; margin:0 0 3px; }
.arw .a { color:#1F4E79; }
.chk { margin:0 0 1px; padding-left:24px; font-size:12.5px; }
.chk .c { color:#1f7a3d; }
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
.oc { text-align:center; }
.ocroot { display:inline-block; background:#1F4E79; color:#fff; font-weight:700; font-size:11px; padding:7px 18px; border-radius:6px; font-family:Calibri,sans-serif; }
.ocbranch { display:flex; justify-content:center; flex-wrap:wrap; gap:6px; margin-top:14px; }
.ocbox { flex:1; min-width:90px; max-width:110px; background:#DEEAF6; border:1px solid #9cbcdd; border-radius:6px; padding:7px 4px; font-size:9px; font-weight:700; color:#14324f; font-family:Calibri,sans-serif; }
.occols { display:flex; justify-content:center; flex-wrap:wrap; gap:10px; margin-top:12px; }
.occol { flex:1; min-width:120px; }
.l2 { background:#bcd3ea; border:1px solid #9cbcdd; border-radius:6px; padding:6px; font-size:10px; font-weight:700; color:#14324f; font-family:Calibri,sans-serif; }
.l3 { background:#e6eef7; border:1px solid #cdddef; border-radius:5px; padding:5px; font-size:9.5px; font-weight:600; color:#1f4e79; margin-top:8px; font-family:Calibri,sans-serif; }
.l4 { background:#fff; border:1px solid #d3ddea; border-radius:4px; padding:3px 5px; font-size:8.5px; color:#33414d; margin-top:5px; display:inline-block; font-family:Calibri,sans-serif; }
.codes { display:flex; gap:16px; margin-bottom:12px; }
.codes > div { flex:1; }
.ct { font-size:12px; font-weight:700; margin:0 0 5px; }
.codetbl { width:100%; font-size:11px; border-collapse:collapse; }
.codetbl th { background:#dbe5f1; border:1px solid #9fb2c8; padding:4px 7px; font-weight:700; color:#14324f; font-family:Calibri,sans-serif; font-size:10px; }
.codetbl td { border:1px solid #b9c6d3; padding:3px 8px; }
.codetbl td.cv { text-align:center; font-weight:600; }
.cover-t { text-align:center; }
@media print { body { background:#fff; } }
"""
