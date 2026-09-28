"""The final report HTML → an Excel workbook of EXACTLY the selected content.

Built from the same HTML string as the PDF / Word / HTML outputs (via
:mod:`p6_export.html_model`) and written with the shared ``write_sections_xlsx`` so it
opens with the standard header block (app — feature · project · data date · generated):

* one sheet per top-level report section (``[data-sec]``), named from the section title
  (≤ 31 chars, unique);
* every HTML table → a titled block with its header row and rows — numbers stay NUMERIC
  and keep their look (``1,234`` · ``36.8%`` · ``11-Dec-2025`` are real numbers / dates
  with the matching Excel format), text stays text;
* KPI / stat tiles → a two-column Measure | Value block (+ Note when the tile has one);
* charts → the numbers behind them (``data-chart-headers`` / ``data-chart-data``), else
  their visible labels;
* text paragraphs → a note under the next block's title (or a Notes block).
"""
import re
from datetime import datetime

from p6_evm import xlsx_writer as XW

from . import html_model as HM

_NUM_RE = re.compile(r'^([+\-−]?)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?$')
_PCT_RE = re.compile(r'^([+\-−]?)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s?%$')
_DATE_FORMS = (('%d-%b-%Y', 'dd-mmm-yyyy'), ('%d %b %Y', 'dd mmm yyyy'),
               ('%Y-%m-%d', 'yyyy-mm-dd'))
_EPOCH = datetime(1899, 12, 30)


def typed(text):
    """Display text → an Excel value that SHOWS the same text but stays sortable/summable."""
    if text is None:
        return ''
    s = str(text).strip()
    if not s:
        return ''
    m = _PCT_RE.match(s)
    if m:
        sign, whole, dec = m.groups()
        v = float(whole.replace(',', '') + ('.' + dec if dec else ''))
        if sign in ('-', '−'):
            v = -v
        nd = len(dec or '')
        fmt = {0: '0%', 1: '0.0%'}.get(nd, '0.00%')
        return XW.Styled(round(v / 100.0, nd + 4), XW.NUMFMT_STYLE[fmt], s)
    m = _NUM_RE.match(s)
    if m:
        sign, whole, dec = m.groups()
        if whole.startswith('0') and len(whole) > 1 and not dec:
            return s                                   # an ID / code like 007 — keep as text
        v = float(whole.replace(',', '') + ('.' + dec if dec else ''))
        if sign in ('-', '−'):
            v = -v
        nd = len(dec or '')
        if nd > 2:
            return v
        if ',' in whole:
            return XW.Styled(v, XW.NUMFMT_STYLE[{0: '#,##0', 1: '#,##0.0'}.get(nd, '#,##0.00')], s)
        if nd == 0:
            return int(v) if abs(v) < 1e15 else v
        return XW.Styled(v, XW.NUMFMT_STYLE[{1: '0.0'}.get(nd, '0.00')], s)
    if 8 <= len(s) <= 11:
        for pat, fmt in _DATE_FORMS:
            try:
                d = datetime.strptime(s, pat)
            except ValueError:
                continue
            return XW.Styled((d - _EPOCH).days, XW.NUMFMT_STYLE[fmt], s)
    return s


def _table_block(t, title, note=None):
    rows = [r for r in t.rows if r]
    if not rows:
        return None
    ncols = max(1, t.ncols)
    hdr_n = t.header_rows if t.header_rows and t.header_rows < len(rows) else 0
    # headers: the LAST header row (the column captions), spans expanded
    headers = []
    if hdr_n:
        for c in rows[hdr_n - 1]:
            headers.append(c.text)
            headers.extend([''] * (max(1, c.colspan) - 1))
    body = []
    for r in rows[hdr_n:]:
        vals = []
        for c in r:
            vals.append(typed(c.text) if not c.header else c.text)
            vals.extend([''] * (max(1, c.colspan) - 1))
        body.append(vals[:ncols] if len(vals) > ncols else vals)
    if not headers:
        headers = [''] * min(ncols, max((len(b) for b in body), default=0))
    blk = {'title': title or (t.caption or 'Table'), 'headers': headers, 'rows': body}
    if note:
        blk['note'] = note
    return blk


def _kpi_block(g, title, note=None):
    tiles = [t for t in g.tiles if (t.label or t.value)]
    if not tiles:
        return None
    has_note = any(t.note for t in tiles)
    headers = ['Measure', 'Value'] + (['Note'] if has_note else [])
    rows = [[t.label, typed(t.value)] + ([t.note] if has_note else []) for t in tiles]
    blk = {'title': title or 'Key figures', 'headers': headers, 'rows': rows}
    if note:
        blk['note'] = note
    return blk


def _visual_block(v, title, note=None):
    if v.data_headers and v.data_rows:
        rows = [[typed(x) if isinstance(x, str) else ('' if x is None else x) for x in r]
                for r in v.data_rows]
        blk = {'title': v.title or title or 'Chart', 'headers': [str(h) for h in v.data_headers],
               'rows': rows}
    elif v.text_lines:
        blk = {'title': v.title or title or 'Chart', 'headers': ['Chart labels'],
               'rows': [[typed(x)] for x in v.text_lines]}
    else:
        return None
    if note:
        blk['note'] = note
    return blk


def section_blocks(blocks, default_title='', part_labels=None):
    """A section's model blocks → write_sections_xlsx blocks (titled tables).

    Block title: the chart's own title → the heading above it (first block after it) →
    the part's ``data-part-label`` (first block of that part) → "<heading> (cont.)"."""
    out = []
    title = default_title
    used_title = False
    notes = []
    part_labels = part_labels or {}
    seen_parts = set()

    def take_title():
        nonlocal used_title
        t = title if not used_title else (title + ' (cont.)' if title else '')
        used_title = True
        return t

    def take_note():
        if not notes:
            return None
        n = ' '.join(notes)
        notes.clear()
        return n[:900]

    prev = cur = None
    for b in blocks:
        k = b.kind
        prev, cur = cur, b         # prev = the block before this one
        if k == 'heading':
            if notes:
                out.append({'title': take_title() or 'Notes', 'headers': [], 'rows': [],
                            'note': take_note()})
            title = b.text
            used_title = False
            continue
        if k == 'paragraph':
            txt = b.text
            if txt and txt not in ('■',):
                notes.append(txt)
            continue
        # a short label line right above the content (a sub-heading like "Key Dates") names
        # the block instead of repeating as a note
        label = None
        if (notes and len(notes[-1]) <= 80 and prev is not None and prev.kind == 'paragraph'
                and getattr(prev, 'keep_with_next', False)):
            label = notes.pop()
        blk = None
        if k == 'table':
            blk = _table_block(b, None, None)
        elif k == 'kpis':
            blk = _kpi_block(b, None, None)
        elif k == 'visual':
            blk = _visual_block(b, None, None)
        elif k == 'list':
            items = [HM.runs_text(i).strip() for i in b.items]
            blk = {'title': None, 'headers': [], 'rows': [[x] for x in items if x]}
        if blk is None:
            continue
        own = blk['title'] if k == 'visual' and blk.get('title') not in (None, 'Chart') else None
        plabel = None
        if b.part and b.part not in seen_parts:
            seen_parts.add(b.part)
            plabel = part_labels.get(b.part) or None
        if not own and used_title and (label or plabel):
            own, label = label or plabel, None
        blk['title'] = own or take_title() or plabel or blk.get('title') or 'Table'
        if label:
            notes.insert(0, label)
        n = take_note()
        if n:
            blk['note'] = n
        out.append(blk)
    if notes:
        out.append({'title': take_title() or 'Notes', 'headers': [], 'rows': [], 'note': take_note()})
    return out


def _sheet_name(title, fallback):
    name = re.sub(r'^\s*\d+\s*[·.)\-–]\s*', '', title or '').strip()
    name = re.split(r'\s+[—–]\s+', name)[0].strip() or fallback or 'Report'   # drop a sub-caption
    name = re.sub(r'[\[\]:*?/\\]', '-', name)
    if len(name) > 28:                  # the shared writer keeps 28 chars — cut at a word, not mid-word
        cut = name[:29].rsplit(' ', 1)[0] if ' ' in name[:29] else name[:28]
        cut = re.sub(r'(\s+(&|and|vs|of|the|by|to|—|–|-|·))+$', '', cut.strip(), flags=re.I)
        name = cut.strip() or name[:28]
    return name


def build_sheets(rep):
    sheets = []
    if rep.sections:
        for i, s in enumerate(rep.sections):
            blocks = section_blocks(s.blocks, s.title, rep.part_labels)
            if not blocks:
                blocks = [{'title': s.title or s.key, 'headers': [], 'rows': [],
                           'note': 'No data available'}]
            sheets.append({'name': _sheet_name(s.title, s.key or f'Section {i + 1}'),
                           'blocks': blocks})
        tail = section_blocks(rep.tail, 'Notes', rep.part_labels)
        if tail and sheets:
            sheets[-1]['blocks'].extend(tail)
    else:
        # a report without [data-sec] wrappers: one sheet of everything after the title block
        body = [b for b in rep.front + rep.tail]
        blocks = section_blocks(body, rep.title or 'Report', rep.part_labels)
        sheets.append({'name': _sheet_name(rep.title, 'Report'),
                       'blocks': blocks or [{'title': rep.title or 'Report', 'headers': [],
                                             'rows': [], 'note': 'No data available'}]})
    return sheets


def build_meta(rep, app_name='', feature='', project='', data_date='', generated=None):
    meta = rep.meta or {}
    ctx = [('Project', project or meta.get('project', '')),
           ('Data date', data_date or meta.get('data_date', '')),
           ('Schedule file', meta.get('source_file', '')),
           ('Generated', generated or datetime.now().strftime('%d-%b-%Y %H:%M'))]
    return {'app': app_name or None, 'title': feature or rep.title or 'Report',
            'context': [(k, v) for k, v in ctx if v]}


def html_to_xlsx(html, path, app_name='', feature='', project='', data_date='', sections=None):
    """The one-call path used by ``POST /api/export/xlsx``."""
    rep = HM.parse_report(html, sections=sections)
    sheets = build_sheets(rep)
    XW.write_sections_xlsx(path, sheets, meta=build_meta(rep, app_name, feature, project, data_date))
    return path
