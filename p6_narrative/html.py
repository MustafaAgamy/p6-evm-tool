"""Render the v5 Baseline Narrative Report (a :class:`NarrativeDoc` dict) to HTML.

Used both for the on-screen tab and as the source for the PDF export. The visual
design is locked (the approved ``report_preview.py`` prototype): a bordered "paper"
page with a cover header, numbered section headings, and per-section chart layouts.

This renderer draws STRAIGHT FROM THE DOC MODEL — every number, name, tree node,
sequence step and edge is taken as-is from the payload; nothing is re-derived here.
The producer (:mod:`p6_narrative.report`) emits exactly five section kinds, in order:

  1 overview     {paragraphs, breakdown:[{world,count}], total, worldlist}
  2 ms_table     {columns, rows:[[name, date_str], …]}
  3 wbs_tree     {worlds:[{name, layout:'tree'|'columns', root:node}]}
                 node = {name, children:[node,…], more?:bool}
  4 seq          {worlds:[{world, fronts:[{title, sequence:[str],
                            instances:[str], activities:[{id,name,wbs}]}]}]}
  5 interfaces   {macro:[world,…], notes:[str], edges:[[a,b], …]}

Editable prose (the overview paragraphs, and any ``editable`` section) is wrapped in
elements carrying ``data-section`` / ``data-field`` / ``data-editable`` hooks so a
later UI layer can turn them into inline ``contenteditable`` fields. No JS is emitted.
"""
import html as _h


def _esc(x):
    return _h.escape('' if x is None else str(x))


# ── WBS nodes ────────────────────────────────────────────────────────────────
def _topdown_node(node, depth=0):
    """Small WBS: a centred top-down org-chart node (CSS ``.tree`` connectors)."""
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
    """Large WBS: one compact indented column entry (CSS ``.it-list`` guides)."""
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


# ── 1. Project Overview ──────────────────────────────────────────────────────
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


# ── 2. Major Milestones ──────────────────────────────────────────────────────
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
            '<table class="ms-table"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>'
            % (head, body))


# ── 3. Work Breakdown Structure — ADAPTIVE ───────────────────────────────────
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
            'organised; the execution order is in Section 4.</p>'
            '%s' % ''.join(charts))


# ── 4. Sequence of Work (no activity counts on screen) ───────────────────────
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
                '<table><thead><tr><th>ID</th><th>Activity</th><th>WBS</th></tr></thead>'
                '<tbody>%s</tbody></table></details></div>'
                % (_esc(number), _esc(f.get('title') or 'front'),
                   _flow(f.get('sequence') or []), applies, acts))
        blocks.append('<h3>%s</h3>%s' % (_esc(w.get('world')), ''.join(fronts)))
    return ('<p class="lead">How each scope is executed, at the major work-package level. The '
            'sequence is derived from the schedule’s own logic; the underlying P6 '
            'activities are available on demand under each block.</p>'
            '%s' % ''.join(blocks))


# ── 5. Interfaces & Dependencies ─────────────────────────────────────────────
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


_RENDER = {'overview': _overview, 'ms_table': _ms_table, 'wbs_tree': _wbs_tree,
           'seq': _seq, 'interfaces': _interfaces}


def _heading(number, title):
    return '<h2><span class="num">%s</span> %s</h2>' % (_esc(number), _esc(title))


def _section(s):
    number, title, kind = s.get('number', ''), s.get('title', ''), s.get('kind', '')
    render = _RENDER.get(kind)
    body = render(s.get('payload') or {}, number) if render else ''
    edit = ' data-editable="1"' if s.get('editable') else ''
    return ('<section class="sec" data-section="%s"%s>%s%s</section>'
            % (_esc(number), edit, _heading(number, title), body))


def render_narrative_html(doc, seq_style=None):
    """Render the narrative ``doc`` (dict) to a self-contained HTML string.

    ``seq_style`` is accepted for signature compatibility with the export path; the
    v5 report has a single sequence layout (the package flow), so it is unused.
    """
    doc = doc or {}
    meta = doc.get('meta') or {}
    project = _esc(meta.get('project_name') or 'Project')
    inner = ''.join(_section(s) for s in (doc.get('sections') or []))
    page = ('<div class="page">'
            '<div class="cover">'
            '<div class="cover-kicker">Baseline Schedule — Narrative Report</div>'
            '<div class="cover-title">%s</div>'
            '</div>%s'
            '<div class="foot">%s · Narrative Report · prepared from the P6 baseline</div>'
            '</div>' % (project, inner, project))
    return '<style>%s</style>%s' % (_CSS, page)


def page_html(doc):
    """Full standalone HTML page (Chrome → PDF source)."""
    return ('<!doctype html><html><head><meta charset="utf-8">'
            '<style>body{margin:0;background:#fff}</style></head><body>'
            + render_narrative_html(doc) + '</body></html>')


_CSS = """
:root{--ink:#1a2230;--mut:#727d8c;--line:#e2e6ec;--accent:#1f5fa8;--accent2:#2c7a4b;
      --bg:#eceef1;--paper:#fff;--chip:#eef3f8;--band:#f6f8fa;}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
  font:14px/1.6 "Segoe UI",Roboto,Helvetica,Arial,sans-serif;padding:24px;}
.page{max-width:920px;margin:0 auto;background:var(--paper);padding:52px 60px;
  border:2px solid var(--accent);box-shadow:0 2px 16px rgba(0,0,0,.12);position:relative;}
.page::before{content:"";position:absolute;inset:9px;border:1px solid var(--line);pointer-events:none;}
.cover{border-bottom:3px double var(--accent);padding-bottom:20px;margin-bottom:8px;}
.cover-kicker{letter-spacing:.16em;text-transform:uppercase;font-size:11px;color:var(--accent);font-weight:700}
.cover-title{font-size:32px;font-weight:800;margin:8px 0 2px;letter-spacing:-.01em}
h2{font-size:19px;margin:38px 0 10px;border-bottom:1px solid var(--line);padding-bottom:7px;font-weight:700}
h2 .num{display:inline-block;background:var(--accent);color:#fff;border-radius:5px;padding:0 9px;margin-right:9px;font-size:15px}
h3{font-size:14px;margin:22px 0 6px;color:var(--accent);text-transform:uppercase;letter-spacing:.04em}
p{margin:10px 0}.lead{color:var(--mut);font-size:13px;margin:4px 0 14px}
.subh{font-weight:700;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);margin:18px 0 8px}
.stats{display:flex;gap:12px;flex-wrap:wrap}
.stat{flex:1;min-width:130px;background:var(--band);border:1px solid var(--line);border-radius:10px;padding:14px 16px;text-align:center}
.stat-n{font-size:28px;font-weight:800;color:var(--accent)}.stat-l{font-weight:600;font-size:13px;color:var(--ink)}
.total{margin-top:12px;font-size:14px}
/* milestones */
.ms-table{border-collapse:collapse;width:100%;margin-top:6px}
.ms-table th{text-align:left;background:var(--band);color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.05em;padding:9px 14px;border-bottom:2px solid var(--line)}
.ms-table td{padding:9px 14px;border-bottom:1px solid var(--line);font-size:13.5px}
.ms-table tr:nth-child(even) td{background:#fafbfc}
.ms-d{color:var(--accent);font-weight:600;white-space:nowrap;width:200px}
/* WBS — small: centered top-down org-chart (fits the page, no horizontal scroll) */
.tree{padding:24px 8px;margin:14px 0;background:var(--band);border:1px solid var(--line);border-radius:10px}
.tree ul{display:flex;flex-wrap:wrap;justify-content:center;padding-top:22px;position:relative;margin:0;list-style:none}
.tree li{list-style:none;text-align:center;position:relative;padding:22px 10px 0}
.tree li::before,.tree li::after{content:"";position:absolute;top:0;right:50%;width:50%;height:22px;border-top:2px solid #c4ccd6}
.tree li::after{right:auto;left:50%;border-left:2px solid #c4ccd6}
.tree li:only-child::before,.tree li:only-child::after{display:none}
.tree li:first-child::before,.tree li:last-child::after{border:0}
.tree li:last-child::before{border-right:2px solid #c4ccd6}
.tree ul ul::before{content:"";position:absolute;top:0;left:50%;border-left:2px solid #c4ccd6;width:0;height:22px}
.tree>li{padding-top:0}
.wt-box{display:inline-block;border-radius:8px;padding:7px 14px;font-size:12.5px;font-weight:600}
.wt-root{background:var(--accent);color:#fff;font-size:14px}
.wt-l1{background:#fff;border:1.5px solid var(--accent);color:var(--accent)}
.wt-n{background:#fff;border:1px solid var(--line);color:var(--ink);font-weight:500}
.wt-more{background:transparent;color:var(--mut);font-style:italic;font-weight:500;border:1px dashed var(--line)}
/* WBS — large: compact multi-column indented tree (wraps, never scrolls) */
.wbs-lg{padding:20px 16px;margin:14px 0;background:var(--band);border:1px solid var(--line);border-radius:10px}
.wbs-lg .wt-root{display:block;width:max-content;max-width:100%;margin:0 auto 16px;text-align:center}
.wbs-cols{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-start}
.wbs-col{flex:1 1 240px;min-width:220px;background:#fff;border:1px solid var(--line);border-radius:9px;padding:12px 14px}
.it-box{font-size:12.5px}.it-l1{font-weight:700;color:var(--accent)}.it-n{color:var(--ink);font-weight:500}
.it-list{list-style:none;margin:5px 0 0;padding-left:15px;position:relative}
.it-list li{position:relative;padding:3px 0}
.it-list li::before{content:"";position:absolute;left:-9px;top:0;height:13px;width:9px;border-left:1.5px solid #c4ccd6;border-bottom:1.5px solid #c4ccd6}
.it-list li::after{content:"";position:absolute;left:-9px;top:13px;bottom:0;border-left:1.5px solid #c4ccd6}
.it-list li:last-child::after{display:none}
.it-more{color:var(--mut);font-style:italic;font-size:11px;padding:3px 0}
/* flow / sequence */
.flow{display:flex;flex-wrap:wrap;align-items:center;gap:5px;background:var(--band);border:1px solid var(--line);border-radius:8px;padding:10px 13px;margin:6px 0}
.fl-box{background:var(--chip);border:1px solid #bcd0e6;color:var(--accent);border-radius:7px;padding:4px 12px;font-weight:600;font-size:12.5px;white-space:nowrap;text-transform:capitalize}
.fl-box.world{background:#e7f2ea;border-color:#b6d8c2;color:var(--accent2)}
.fl-arr{color:var(--mut);font-size:11px}
.notes{margin:8px 0;padding-left:20px}.notes li{margin:5px 0;font-size:13px}
.edges{margin:4px 0;padding-left:20px}.edges li{margin:3px 0;font-size:13px}
.front{border:1px solid var(--line);border-radius:9px;padding:12px 16px;margin:10px 0;background:#fff}
.fr-title{font-weight:700;font-size:14px;text-transform:capitalize;margin-bottom:6px}
.fr-meta{color:var(--mut);font-size:12.5px;margin:6px 0 0}
details{margin-top:8px}summary{cursor:pointer;color:var(--accent);font-size:12px}
table{border-collapse:collapse;width:100%;margin-top:8px;font-size:12px}
th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-size:11px}.mono{font-family:ui-monospace,Consolas,monospace;color:var(--mut);white-space:nowrap}
.muted{color:var(--mut)}
.foot{margin-top:34px;border-top:1px solid var(--line);padding-top:10px;color:var(--mut);font-size:11px;text-align:center}
"""
