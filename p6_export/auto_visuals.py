"""Automatic VISUALS for the Word / Excel exports (owner comment 2).

"Screen = PDF = Word = HTML = Excel — same data, same format and style."  The PDF and the HTML
are the report itself.  Word and Excel are built from the report's blocks, and a chart or a row
of tiles made of styled ``<div>``s has no Word / Excel equivalent: it reached Word as loose lines
of text.  A renderer can mark such a block ``data-export="image"`` by hand (Earned Value and
Calendar Audit do).  For every other report ``mark_visuals`` does it:

  * each DESIGNED block of a section — a chart, a gauge, a row of tiles, a banner, a chain of
    boxes — is marked ``data-export="image"``, so Word receives it as a picture drawn by Chrome
    (exactly what the PDF shows, sliced at page height when tall);
  * the numbers and labels inside it are attached (``data-chart-headers`` / ``data-chart-data``)
    so Excel receives a table instead of a picture;
  * tables, headings, lists and plain paragraphs are left alone — they stay real Word tables
    and text, and real Excel rows.

Only attributes are added, and only for the Word / Excel routes; the preview, the PDF and the
HTML file are untouched.  Any doubt → the HTML is returned unchanged.
"""
import html as _html
import json
import re

from .auto_parts import _RAW, _has, _text, _tree, _walk

_PLAIN_TAGS = {'table', 'ul', 'ol', 'dl', 'p', 'br', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'svg',
               'canvas', 'img', 'thead', 'tbody', 'tr', 'td', 'th', 'pre', 'span', 'b', 'i', 'em',
               'strong', 'small', 'a', 'label', 'select', 'style', 'script', 'title'}
_DESIGN_CLASS = re.compile(
    r'chart|bar|curve|gantt|donut|pie|heat|spark|timeline|histogram|waterfall|lane|strip|kpi|tile|card|'
    r'stat|band|score|gauge|metric|dash|chain|box|pill|track|badge|banner|verdict|health|legend|prog|'
    r'hero|cost|ts\b|wrow|bc\b|tiles|top3|comp\b|grid2|msbox|cplegend', re.I)
_LAYOUT_STYLE = re.compile(r'style\s*=\s*["\'][^"\']*(?:width\s*:|height\s*:|background|flex|grid)', re.I)
MAX_COLS = 8
MAX_ROWS = 400


MAX_ITEMS = 60              # more direct children than this = a list of rows, not a layout of charts
MAX_HTML = 120_000         # a block larger than this is left as text: a picture would run for pages


def _contents(el):
    return 'display:contents' in (el.attr('style') or '').replace(' ', '')


def _designed(s, el):
    """A block drawn with layout and colour (not a table, a list or a plain sentence)."""
    if el.tag in _PLAIN_TAGS or el.tag in _RAW:
        return False
    if _has(s, el, r'<table\b'):
        return False                                   # tables stay real tables
    if el.inner_end - el.tag_end > MAX_HTML or len(el.children) > MAX_ITEMS:
        return False                                   # very many rows: a long LIST, not a chart
    if _has(s, el, r'<svg\b'):
        return True                                    # a chart with its caption / legend: one picture
    inner = s[el.tag_end:el.inner_end]
    if len(_LAYOUT_STYLE.findall(inner)) >= 2:
        return True
    return bool(_DESIGN_CLASS.search(el.cls())) and len(el.children) >= 2


def _cells(s, el):
    """The texts of one row-like element: one cell per child that carries text."""
    kids = [c for c in el.children if c.tag not in _RAW and c.tag != 'br']
    if len(kids) < 2:
        t = _text(s, el, 200)
        return [t] if t else []
    out = []
    for c in kids:
        t = _text(s, c, 200)
        if t:
            out.append(t)
    return out[:MAX_COLS]


def _chart_data(s, el):
    """(headers, rows) read from a designed block: its repeated children are the rows."""
    node = el
    for _ in range(4):
        kids = [c for c in node.children if c.tag not in _RAW and c.tag != 'br']
        if len(kids) == 1 and kids[0].children:
            node = kids[0]
            continue
        break
    kids = [c for c in node.children if c.tag not in _RAW and c.tag != 'br']
    rows = [r for r in (_cells(s, k) for k in kids[:MAX_ROWS]) if r]
    if not rows:
        t = _text(s, el, 400)
        rows = [[t]] if t else []
    if not rows:
        return None, None
    width = max(len(r) for r in rows)
    rows = [r + [''] * (width - len(r)) for r in rows]
    if width == 1:
        headers = ['Item']
    elif width == 2:
        headers = ['Item', 'Value']
    else:
        headers = ['Item'] + ['Value %d' % i for i in range(1, width)]
    return headers, rows


def _mark(s, el, edits):
    headers, rows = _chart_data(s, el)
    attrs = ' data-export="image" data-auto-visual="1"'
    if headers and rows:
        attrs += (" data-chart-headers='%s' data-chart-data='%s'"
                  % (_html.escape(json.dumps(headers, ensure_ascii=False), quote=True).replace("'", '&#39;'),
                     _html.escape(json.dumps(rows, ensure_ascii=False), quote=True).replace("'", '&#39;')))
    edits.append((el.start + 1 + len(el.tag), attrs))


def _process(s, el, edits, depth=0):
    if el.tag in _RAW or 'data-export' in el.attrs_src:
        return
    if not _contents(el) and _designed(s, el):
        _mark(s, el, edits)
        return
    if depth >= 6 or el.tag in ('table', 'svg', 'ul', 'ol'):
        return
    if len(el.children) > MAX_ITEMS:
        return                 # a long list of look-alike rows: left as text, never thousands of pictures
    for c in el.children:
        _process(s, c, edits, depth + 1)


def mark_visuals(html):
    """Report HTML → the same HTML with every designed block of every section marked as a
    picture for Word and given its numbers for Excel.  A section whose renderer already marked
    its own exports (any ``data-export`` inside) is left exactly as written.  Never raises."""
    s = html if isinstance(html, str) else ''
    if 'data-sec' not in s:
        return html
    try:
        root = _tree(s)
        edits, seen = [], set()
        for sec in _walk(root):
            if 'data-sec' not in sec.attrs_src or sec.attr('data-sec') is None:
                continue
            if id(sec) in seen:
                continue
            for d in _walk(sec):
                seen.add(id(d))                         # a nested [data-sec] is handled by its parent
            if re.search(r'\bdata-export\s*=\s*(?!["\']?table\b)', s[sec.tag_end:sec.inner_end]):
                continue                                # the renderer marked its own exports
                                                        # (a long list given as a table does not count)
            if (sec.attr('data-parts') or '').lower() == 'none' and not _has(s, sec, r'<table'):
                _mark(s, sec, edits)                    # one designed block (a card): a picture as a whole
                continue
            for c in sec.children:
                _process(s, c, edits)
        if not edits:
            return html
        out = s
        for pos, text in sorted(edits, key=lambda e: e[0], reverse=True):
            out = out[:pos] + text + out[pos:]
        return out
    except Exception:
        return html
