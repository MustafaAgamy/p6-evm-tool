"""Word pagination rules for the Office-HTML ``.doc`` exports (owner point 14).

The python-docx writers get the rules from :mod:`p6_export.docx_pagination`; a report that
reaches Word as Office-HTML (the Reporting Studio's own *Word* button — ``word_export``)
is paginated by Word's HTML importer instead, which ignores ``@media print`` and most of
CSS. What Word 16 DOES honour (measured through COM, see the tests):

* ``page-break-after:avoid`` on a ``<p>`` / ``<div>`` / ``<hN>`` → *Keep with next*
  (inline style always; a class rule only outside table cells);
* ``page-break-inside:avoid`` on a ``tbody`` row → the row never splits;
* ``<thead>`` rows → *Repeat as header row* on every page.

A table row is kept with the next one when a paragraph in it keeps with next — so this
pass wraps the simple cells of the right rows in ``<p style="margin:0;page-break-after:avoid">``:

* a heading table (``table.sr-sec-h`` — the Studio's numbered item title) keeps with the
  block under it;
* a short label / intro right before a table or a picture keeps with it;
* data tables: a header row made only of ``<th>`` cells becomes a ``<thead>`` (repeated);
  a small table (≤ :data:`SMALL_ROWS` body rows) is kept whole; a longer one keeps its
  first 3 and last 3 body rows together, so no page ever holds only 1–2 of its rows.

Pure string rewrite — text, values, colours and order are never changed.
"""
import re
from html.parser import HTMLParser

try:                                   # the same thresholds as the PDF / .docx rules
    import report_theme as _rt
    FIT = float(getattr(_rt, 'PAGINATION_FIT', 0.35))
    MIN_ROWS = int(getattr(_rt, 'PAGINATION_MIN_ROWS', 3))
except Exception:                      # pragma: no cover — report_theme always ships
    FIT, MIN_ROWS = 0.35, 3

ROWS_PER_PAGE = 36                     # ~A4 body height / a typical report-table row
SMALL_ROWS = int(FIT * ROWS_PER_PAGE)  # 12 — a table this short is kept on one page
LABEL_MAX_CHARS = 160                  # a label / intro line, not a body paragraph
ROW_MAX_CHARS = 600                    # a row with more text is a layout row, not data

KWN_OPEN = '<p style="margin:0;page-break-after:avoid">'
KWN_CLOSE = '</p>'
_KWN = 'page-break-after:avoid'

_BLOCK = {'p', 'div', 'table', 'ul', 'ol', 'li', 'dl', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
          'blockquote', 'pre', 'figure', 'section', 'article', 'header', 'footer', 'hr', 'img',
          'svg', 'center', 'form'}
_VOID = {'br', 'img', 'hr', 'meta', 'link', 'input', 'col', 'area', 'base', 'wbr', 'source'}
_STYLE_RE = re.compile(r'''(\sstyle\s*=\s*)(["'])(.*?)\2''', re.IGNORECASE | re.DOTALL)
_WS_RE = re.compile(r'^(?:\s|&nbsp;|&#160;|&#xa0;)*$', re.IGNORECASE)


def _with_kwn(raw):
    """``raw`` start tag with ``page-break-after:avoid`` in its inline style."""
    if _KWN in raw.replace(' ', '').lower():
        return raw
    m = _STYLE_RE.search(raw)
    if m:
        return raw[:m.start(3)] + _KWN + ';' + raw[m.start(3):]
    end = len(raw) - (2 if raw.endswith('/>') else 1)
    return raw[:end] + f' style="{_KWN}"' + raw[end:]


class _Tokens(HTMLParser):
    """Lossless-enough token stream: every token keeps its raw source text."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.toks = []                  # [kind, tag, raw, attrs]

    def handle_starttag(self, tag, attrs):
        self.toks.append(['start', tag, self.get_starttag_text(), dict(attrs)])

    def handle_startendtag(self, tag, attrs):
        self.toks.append(['startend', tag, self.get_starttag_text(), dict(attrs)])

    def handle_endtag(self, tag):
        self.toks.append(['end', tag, f'</{tag}>', None])

    def handle_data(self, data):
        self.toks.append(['data', None, data, None])

    def handle_entityref(self, name):
        self.toks.append(['data', None, f'&{name};', None])

    def handle_charref(self, name):
        self.toks.append(['data', None, f'&#{name};', None])

    def handle_comment(self, data):
        self.toks.append(['other', None, f'<!--{data}-->', None])

    def handle_decl(self, decl):
        self.toks.append(['other', None, f'<!{decl}>', None])

    def unknown_decl(self, data):
        self.toks.append(['other', None, f'<![{data}]>', None])

    def handle_pi(self, data):
        self.toks.append(['other', None, f'<?{data}>', None])


def _tokenize(html):
    p = _Tokens()
    p.feed(html)
    p.close()                           # flushes any trailing text as data
    return p.toks


class _Cell:
    __slots__ = ('start', 'end', 'tag', 'blocks', 'nested', 'img', 'block_starts', 'chars')

    def __init__(self, start, tag):
        self.start, self.end, self.tag = start, None, tag
        self.blocks = self.img = False
        self.nested = []                # nested tables (their row counts decide "layout")
        self.block_starts = []
        self.chars = 0


class _Row:
    __slots__ = ('start', 'end', 'head', 'cells')

    def __init__(self, start, head):
        self.start, self.end, self.head, self.cells = start, None, head, []


class _Table:
    __slots__ = ('start', 'cls', 'rows', 'in_head', 'has_thead', 'tbody')

    def __init__(self, start, cls):
        self.start, self.cls, self.rows = start, cls, []
        self.in_head = self.has_thead = False
        self.tbody = None


def _analyse(toks):
    tables, stack, opened, labels = [], [], [], []
    for i, (kind, tag, raw, attrs) in enumerate(toks):
        cur = stack[-1] if stack else None
        cell = cur.rows[-1].cells[-1] if cur and cur.rows and cur.rows[-1].cells else None
        cell = cell if cell is not None and cell.end is None else None
        if kind in ('start', 'startend'):
            if tag == 'table':
                if cell is not None:
                    cell.blocks = True
                t = _Table(i, (attrs or {}).get('class') or '')
                if cell is not None:
                    cell.nested.append(t)
                tables.append(t)
                if kind == 'start':
                    stack.append(t)
                continue
            if cur is not None and tag == 'thead':
                cur.in_head = cur.has_thead = True
            elif cur is not None and tag == 'tbody':
                cur.in_head = False
                if cur.tbody is None and not cur.rows:
                    cur.tbody = i
            elif cur is not None and tag == 'tr':
                cur.rows.append(_Row(i, cur.in_head))
            elif cur is not None and tag in ('td', 'th') and cur.rows:
                cur.rows[-1].cells.append(_Cell(i, tag))
            elif cell is not None and tag in _BLOCK:
                cell.blocks = True
                cell.img = cell.img or tag in ('img', 'svg')
                if tag in ('p', 'div') and kind == 'start':
                    cell.block_starts.append(i)
            if tag in ('p', 'div') and kind == 'start':
                for e in opened:
                    e[4] = True
                opened.append([i, tag, None, 0, False])    # start, tag, end, chars, has_block
            elif tag in _BLOCK:
                for e in opened:
                    e[4] = True
        elif kind == 'end':
            if tag == 'table' and stack:
                stack.pop()
            elif cur is not None and tag == 'thead':
                cur.in_head = False
            elif cur is not None and tag == 'tr' and cur.rows:
                cur.rows[-1].end = i
            elif cur is not None and tag in ('td', 'th') and cur.rows and cur.rows[-1].cells:
                c = cur.rows[-1].cells[-1]
                if c.end is None:
                    c.end = i
            if tag in ('p', 'div'):
                for k in range(len(opened) - 1, -1, -1):
                    if opened[k][1] == tag:
                        e = opened.pop(k)
                        e[2] = i
                        labels.append(e)
                        break
        elif kind == 'data':
            n = len(raw.strip())
            if cell is not None:
                cell.chars += n
            for e in opened:
                e[3] += n
    return tables, labels


def _layout_table(t):
    """A table that holds page layout (nested multi-row tables, pictures, long text),
    not data rows — its rows are left free (Word would otherwise try to keep a
    page-tall block together)."""
    for r in t.rows:
        if sum(c.chars for c in r.cells) > ROW_MAX_CHARS:
            return True
        for c in r.cells:
            if c.img or any(len(n.rows) > 1 for n in c.nested):
                return True
    return False


def _div_tree(toks):
    """Every ``<p>`` / ``<div>`` with its parent, its ``<p>``/``<div>`` children, its text size and
    whether any other block (table, list, picture, heading) sits inside it."""
    nodes, stack = [], []
    for i, (kind, tag, raw, attrs) in enumerate(toks):
        if kind == 'start' and tag in ('p', 'div'):
            node = {'start': i, 'tag': tag, 'end': None, 'chars': 0, 'kids': [], 'block': False,
                    'parent': stack[-1] if stack else None}
            if stack:
                stack[-1]['kids'].append(node)
            nodes.append(node)
            stack.append(node)
        elif kind in ('start', 'startend') and tag in _BLOCK and tag not in ('p', 'div'):
            for nd in stack:
                nd['block'] = True
        elif kind == 'end' and tag in ('p', 'div'):
            for k in range(len(stack) - 1, -1, -1):
                if stack[k]['tag'] == tag:
                    stack[k]['end'] = i
                    del stack[k:]
                    break
        elif kind == 'data':
            n = len(raw.strip())
            for nd in stack:
                nd['chars'] += n
    return nodes


def _leaf(nd):
    return nd['end'] is not None and not nd['kids'] and not nd['block']


def _line_groups(toks):
    """Start tokens to keep with the next block (Word has no flex / grid: every ``<div>`` of a
    screen row prints as its own line):

    * a LINE GROUP — a short ``<div>`` made only of 2+ one-line ``<div>``/``<p>`` children (a
      score row "Float Analysis | bar | 95.8% | 15 | 16.9", a bar row "label | bar | 0.5%", a KPI
      card "DELAY | 0 days") — keeps its lines together (all but the last keep with next), so a
      row is never cut between its name and its values;
    * a CONTAINER TITLE — a short one-line block that opens a container of further blocks (a
      card's title "Lags by WBS area" over its bar rows) — keeps with the first of them."""
    keep = []
    for nd in _div_tree(toks):
        kids = nd['kids']
        if (nd['tag'] == 'div' and nd['end'] is not None and len(kids) >= 2 and not nd['block']
                and all(_leaf(k) for k in kids) and 0 < nd['chars'] <= LABEL_MAX_CHARS
                and sum(k['chars'] for k in kids) == nd['chars']):
            keep.extend(k['start'] for k in kids[:-1])
        par = nd['parent']
        if (par is not None and _leaf(nd) and par['kids'][0] is nd and len(par['kids']) >= 2
                and 0 < nd['chars'] <= LABEL_MAX_CHARS
                and not any(toks[j][0] in ('start', 'startend') and toks[j][1] in _BLOCK
                            or (toks[j][0] == 'data' and not _WS_RE.match(toks[j][2]))
                            for j in range(par['start'] + 1, nd['start']))
                and not _opens_titled_block(par['kids'][1], toks)):
            keep.append(nd['start'])
    return keep


def _opens_titled_block(sib, toks):
    """True when ``sib`` is a block holding a table / picture that opens with its OWN short title
    (``1 · Main WBS`` over a code table). An intro over such blocks stays with the section heading
    only: chaining it into the first titled block (whose title already keeps with its table) made
    heading + intro + title + table one block Word pushed whole (GBT Studio .doc: 40 % blank)."""
    if not sib['block'] or not sib['kids']:
        return False
    s = sib
    while s['kids']:
        if any(toks[j][0] == 'data' and not _WS_RE.match(toks[j][2])
               for j in range(s['start'] + 1, s['kids'][0]['start'])):
            return False                        # text before the first child: no own title
        s = s['kids'][0]
    return _leaf(s) and 0 < s['chars'] <= LABEL_MAX_CHARS


def _unsplit_rows(toks):
    """Token ranges of the table rows set never to split (inline ``page-break-inside:avoid``)."""
    out, i = [], 0
    while i < len(toks):
        kind, tag, raw, _ = toks[i]
        if kind == 'start' and tag == 'tr' and 'page-break-inside:avoid' in raw.replace(' ', '').lower():
            depth, j = 1, i + 1
            while j < len(toks) and depth:
                if toks[j][1] == 'tr' and toks[j][0] == 'start':
                    depth += 1
                elif toks[j][1] == 'tr' and toks[j][0] == 'end':
                    depth -= 1
                j += 1
            out.append((i, j - 1))
            i = j
            continue
        i += 1
    return out


def paginate_word_html(html):
    """Return ``html`` (an Office-HTML body or whole document) with the Word keep rules
    written in as inline styles / ``<thead>`` — see the module docstring."""
    if not isinstance(html, str) or '<' not in html:
        return html
    toks = _tokenize(html)
    tables, labels = _analyse(toks)
    before, after, repl = {}, {}, {}

    def keep_row(row):
        for c in row.cells:
            if c.end is None:
                continue
            if not c.blocks:
                after[c.start] = after.get(c.start, '') + KWN_OPEN
                before[c.end] = KWN_CLOSE + before.get(c.end, '')
            else:
                for j in c.block_starts:
                    repl[j] = _with_kwn(repl.get(j, toks[j][2]))

    for t in tables:
        rows = [r for r in t.rows if r.cells]
        if not rows:
            continue
        if 'sr-sec-h' in t.cls.split():                 # a heading table: keeps with next
            for r in rows:
                keep_row(r)
            continue
        head = [r for r in rows if r.head]
        if (not head and len(rows) > 1 and rows[0].end is not None
                and all(c.tag == 'th' for c in rows[0].cells)):
            first = rows[0]                              # a <th> row → repeated header
            if t.tbody is not None:
                repl[t.tbody] = ''
                before[first.start] = before.get(first.start, '') + '<thead>'
                after[first.end] = '</thead>' + toks[t.tbody][2] + after.get(first.end, '')
            else:
                before[first.start] = before.get(first.start, '') + '<thead>'
                after[first.end] = '</thead>' + after.get(first.end, '')
            head = [first]
        body = [r for r in rows if r not in head]
        if _layout_table(t) or not body:
            continue
        for r in head:                                   # header keeps with the first row
            keep_row(r)
        n = len(body)
        if n <= 1:
            continue
        if n <= SMALL_ROWS:
            keep = body[:-1]                             # small: kept whole
        else:                                            # long: no 1-2 stranded rows
            keep = body[:MIN_ROWS - 1] + body[n - MIN_ROWS:n - 1]
        for r in keep:
            keep_row(r)

    # a screen row's lines stay together; a container's title keeps with its first block
    for j in _line_groups(toks):
        repl[j] = _with_kwn(repl.get(j, toks[j][2]))

    # a short label / intro line right before a table or a picture keeps with it
    for start, tag, end, chars, has_block in labels:
        if end is None or has_block or chars == 0 or chars > LABEL_MAX_CHARS:
            continue
        j = end + 1
        while j < len(toks):
            k, tg, raw, _ = toks[j]
            if k == 'data' and _WS_RE.match(raw):
                j += 1
            elif k == 'other' or (k == 'start' and tg in ('div', 'a', 'span', 'center')):
                j += 1
            elif k == 'startend' and tg == 'a':
                j += 1
            elif k == 'end' and tg in ('a', 'span'):
                j += 1
            else:
                break
        if j < len(toks) and toks[j][0] in ('start', 'startend') and toks[j][1] in ('table', 'img', 'svg'):
            repl[start] = _with_kwn(repl.get(start, toks[start][2]))

    # inside a layout row that never splits (``<tr style="page-break-inside:avoid">`` — a row of
    # month calendars) nothing needs keeping: Word keeps a row whose paragraphs keep-with-next
    # with the NEXT row, so keep rules inside chain every such row into one block that is
    # pushed whole, leaving a page nearly blank
    for a, b in _unsplit_rows(toks):
        for i in range(a, b + 1):
            if i in repl and repl[i] and repl[i] != toks[i][2] and repl[i] == _with_kwn(toks[i][2]):
                del repl[i]
            for d in (before, after):
                if i in d:
                    d[i] = d[i].replace(KWN_OPEN, '').replace(KWN_CLOSE, '')

    out = []
    for i, tok in enumerate(toks):
        if i in before:
            out.append(before[i])
        out.append(repl.get(i, tok[2]))
        if i in after:
            out.append(after[i])
    return ''.join(out)
