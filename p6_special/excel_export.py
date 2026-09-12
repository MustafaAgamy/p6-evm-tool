"""Special Report Excel exporter — the SAME selected, ordered sections as the
screen preview / Chrome PDF / Word, emitted as an .xlsx workbook.

The Special Report is a user-composed cross-feature document: an ordered list of
selected results, each produced by a feature provider as a *payload* (see
``p6_special.payloads`` — kpi_group / table / bars / segbar / findings / keyvals /
text / note / group / html / no_data). ``registry.render(ctx, item_ids)`` turns
the selected ids into a ``rendered`` list of ``{id, title, feature,
feature_title, ctype, payload}`` — the exact same list the PDF/Word wrappers
consume (``render_html.document_parts`` / ``word_export.build_word_document``).

Here we turn that same ``rendered`` list into the ``sheets`` structure consumed by
``p6_evm.xlsx_writer.write_sections_xlsx``, so the workbook MIRRORS the report:

  * a small ``Report`` cover sheet (name / project / data date — like the PDF cover);
  * then ONE worksheet per selected section, in order, named by its numbered title,
    each stacking the section's payload as one or more titled tables.

Every number the payload carries as an actual number stays a numeric Excel cell
(bars values, segbar values, numeric table cells) so figures remain computable;
pre-formatted display strings (``fmt.pct01`` etc.) are kept verbatim so the
figures read exactly as on screen. Reused feature-report sections arrive as
``html`` payloads (a feature's own report markup); their real data tables are
extracted best-effort with the stdlib HTML parser, chart/layout tables skipped,
and a section that yields no extractable grid falls back to an honest pointer row.

Never raises on empty/missing data: an empty selection yields a single 'No data'
sheet; an errored producer becomes a 'No data available' row.

The client POSTs the same body it sends to ``/api/special/pdf``; the server
resolves the project, builds the context (DB is the read path — no XML re-parse
for DB-backed features), renders, and calls :func:`build_excel`.
"""
from html.parser import HTMLParser

from p6_evm.xlsx_writer import write_sections_xlsx

# Kind -> the sub-block label used when a section payload contributes more than
# one table (a `group`, or an `html` report with several data tables). The first
# block of every section is titled by the section's own (numbered) title.
_KIND_LABEL = {
    'kpi_group': 'Key figures', 'table': 'Details', 'bars': 'Comparison',
    'segbar': 'Breakdown', 'findings': 'Findings', 'keyvals': 'Summary',
    'text': 'Notes', 'note': 'Note', 'html': 'Report tables',
}


# ── small helpers ─────────────────────────────────────────────────────────────
def _cell(v):
    """Keep real numbers numeric (bars/segbar/numeric table cells stay computable);
    everything else becomes a string. Tuples are ``(text, tone)`` — drop the tone."""
    if isinstance(v, tuple):
        v = v[0] if v else ''
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return v
    return '' if v is None else str(v)


def _clean_date(v):
    """Drop any '00:00:00' time tail a stored data_date carries (matches the cover)."""
    if not v:
        return ''
    s = str(v)
    if ' ' in s:
        return s.split(' ')[0]
    if 'T' in s:
        return s.split('T')[0]
    return s


# ── payload -> list of sub-blocks {label, headers, rows, note?} ────────────────
def _no_data_block(payload):
    err = (payload or {}).get('error')
    msg = 'No data available for this result.' + (f' ({err})' if err else '')
    return [{'label': None, 'headers': ['Result'], 'rows': [[msg]]}]


def _kpi_group_block(pl):
    items = pl.get('items') or []
    if not items:
        return _no_data_block(pl)
    rows = [[_cell(it.get('label')), _cell(it.get('value')), _cell(it.get('sub'))]
            for it in items]
    return [{'label': _KIND_LABEL['kpi_group'], 'headers': ['Metric', 'Value', 'Detail'],
             'rows': rows}]


def _table_block(pl):
    cols = list(pl.get('columns') or [])
    rows = pl.get('rows') or []
    if not rows:
        return [{'label': _KIND_LABEL['table'], 'headers': cols or ['Result'],
                 'rows': [['No data available for this result.']]}]
    out_rows = [[_cell(c) for c in r] for r in rows]
    return [{'label': _KIND_LABEL['table'], 'headers': cols, 'rows': out_rows}]


def _bars_block(pl):
    series = pl.get('series') or []
    rows = pl.get('rows') or []
    if not rows or not series:
        return _no_data_block(pl)
    headers = ['Item'] + [str(s.get('label') or '') for s in series]
    out_rows = []
    for row in rows:
        vals = row.get('values') or []
        out_rows.append([_cell(row.get('label'))]
                        + [_cell(vals[i]) if i < len(vals) else '' for i in range(len(series))])
    blk = {'label': _KIND_LABEL['bars'], 'headers': headers, 'rows': out_rows}
    if pl.get('note'):
        blk['note'] = str(pl['note'])
    return [blk]


def _segbar_block(pl):
    segs = pl.get('segments') or []
    if not segs:
        return _no_data_block(pl)
    rows = [[_cell(s.get('label')), _cell(s.get('value'))] for s in segs]
    blk = {'label': _KIND_LABEL['segbar'], 'headers': ['Segment', 'Value'], 'rows': rows}
    if pl.get('note'):
        blk['note'] = str(pl['note'])
    return [blk]


def _findings_block(pl):
    items = pl.get('items') or []
    if not items:
        return [{'label': _KIND_LABEL['findings'], 'headers': ['Severity', 'Finding', 'Detail'],
                 'rows': [['—', str(pl.get('empty') or 'No findings.'), '']]}]
    rows = [[_cell(f.get('severity') or 'info'), _cell(f.get('title')), _cell(f.get('detail'))]
            for f in items]
    return [{'label': _KIND_LABEL['findings'], 'headers': ['Severity', 'Finding', 'Detail'],
             'rows': rows}]


def _keyvals_block(pl):
    pairs = pl.get('pairs') or []
    if not pairs:
        return _no_data_block(pl)
    rows = [[_cell(k), _cell(v)] for k, v in pairs]
    return [{'label': _KIND_LABEL['keyvals'], 'headers': ['Field', 'Value'], 'rows': rows}]


def _text_block(pl):
    paras = pl.get('paragraphs') or []
    if not paras:
        return _no_data_block(pl)
    return [{'label': _KIND_LABEL['text'], 'headers': ['Details'],
             'rows': [[str(p)] for p in paras]}]


def _note_block(pl):
    return [{'label': _KIND_LABEL['note'], 'headers': ['Note'],
             'rows': [[str(pl.get('message') or '')]]}]


def _group_block(pl):
    blocks = []
    for child in (pl.get('blocks') or []):
        blocks.extend(_payload_blocks(child))
    return blocks or _no_data_block(pl)


# ── reused feature-report (html) -> best-effort data-table extraction ──────────
class _TableExtractor(HTMLParser):
    """Collect grid tables from a feature-report HTML fragment. Cells go to the
    innermost open table; a table that contains a nested table is treated as a
    layout/chart wrapper and skipped, so bar-chart spacer tables never surface as
    fake data. Text is entity-decoded (convert_charrefs) and whitespace-collapsed;
    &nbsp; (\\xa0) counts as empty."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []       # open <table> frames (innermost last)
        self.tables = []      # finished, non-nested tables: list[list[(text, is_th)]]

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t == 'table':
            if self.stack:
                self.stack[-1]['nested'] = True
            self.stack.append({'rows': [], 'row': None, 'cell': None, 'th': False, 'nested': False})
        elif not self.stack:
            return
        elif t == 'tr':
            self.stack[-1]['row'] = []
        elif t in ('td', 'th'):
            top = self.stack[-1]
            if top['row'] is None:
                top['row'] = []
            top['cell'] = []
            top['th'] = (t == 'th')

    def handle_data(self, data):
        if self.stack and self.stack[-1]['cell'] is not None:
            self.stack[-1]['cell'].append(data)

    def handle_endtag(self, tag):
        t = tag.lower()
        if not self.stack:
            return
        top = self.stack[-1]
        if t in ('td', 'th') and top['cell'] is not None:
            text = ' '.join(''.join(top['cell']).replace('\xa0', ' ').split())
            (top['row'] if top['row'] is not None else top.setdefault('row', [])).append((text, top['th']))
            top['cell'] = None
        elif t == 'tr' and top['row'] is not None:
            top['rows'].append(top['row'])
            top['row'] = None
        elif t == 'table':
            self.stack.pop()
            if not top['nested']:
                self.tables.append(top['rows'])


def _qualify(rows):
    """A captured table -> (headers, data_rows) if it is a real grid, else None.

    A grid needs >= 2 columns and >= 2 rows carrying >= 2 non-empty cells (filters
    out single-column layout tables and near-empty spacer/chart tables)."""
    grid = [[txt for txt, _ in r] for r in rows]
    width = max((len(r) for r in grid), default=0)
    if width < 2:
        return None
    substantive = [r for r in grid if sum(1 for c in r if c) >= 2]
    if len(substantive) < 2:
        return None
    # header row = the first row that had <th>, else the first row
    header_idx = next((i for i, r in enumerate(rows) if any(th for _, th in r)), 0)
    headers = [c for c, _ in rows[header_idx]]
    headers = (headers + [''] * width)[:width]
    data = []
    for i, r in enumerate(grid):
        if i == header_idx:
            continue
        if not any(c for c in r):
            continue
        data.append((r + [''] * width)[:width])
    if not data:
        return None
    return headers, data


def _html_block(pl):
    ex = _TableExtractor()
    try:
        ex.feed(pl.get('html') or '')
        ex.close()
    except Exception:
        ex.tables = []
    blocks = []
    for tbl in ex.tables:
        q = _qualify(tbl)
        if q:
            headers, data = q
            blocks.append({'label': _KIND_LABEL['html'], 'headers': headers, 'rows': data})
    if blocks:
        return blocks
    return [{'label': 'Report', 'headers': ['Section'],
             'rows': [['This section is a formatted feature report — open the PDF or Word '
                       'export for its full layout (tables and charts).']]}]


_DISPATCH = {
    'kpi_group': _kpi_group_block, 'table': _table_block, 'bars': _bars_block,
    'segbar': _segbar_block, 'findings': _findings_block, 'keyvals': _keyvals_block,
    'text': _text_block, 'note': _note_block, 'group': _group_block,
    'html': _html_block, 'no_data': _no_data_block,
}


def _payload_blocks(payload):
    if not payload:
        return _no_data_block(payload)
    fn = _DISPATCH.get(payload.get('kind'))
    return fn(payload) if fn else _no_data_block(payload)


# ── section -> one worksheet ───────────────────────────────────────────────────
def _section_sheet(index, item):
    """One selected result -> one worksheet {name, blocks}. The first block carries
    the section's numbered title; a multi-table section (group/html) gets sub-labels."""
    title = item.get('title') or item.get('id') or 'Section'
    subs = _payload_blocks(item.get('payload') or {'kind': 'no_data'})
    blocks = []
    for k, s in enumerate(subs):
        if k == 0:
            btitle = f'{index}. {title}'
        else:
            btitle = f'{title} — {s["label"]}' if s.get('label') else f'{index}. {title}'
        blk = {'title': btitle, 'headers': s['headers'], 'rows': s['rows']}
        if s.get('note'):
            blk['note'] = s['note']
        blocks.append(blk)
    return {'name': f'{index}. {title}', 'blocks': blocks}


def _cover_sheet(report_name, meta, rendered, letterhead):
    lh = letterhead or {}
    pairs = [['Report', report_name]]
    if meta.get('project_name'):
        pairs.append(['Project', str(meta['project_name'])])
    dd = _clean_date(meta.get('data_date'))
    if dd:
        pairs.append(['Data date', dd])
    if lh.get('company'):
        pairs.append(['Company', str(lh['company'])])
    if lh.get('prepared_by'):
        pairs.append(['Prepared by', str(lh['prepared_by'])])
    pairs.append(['Sections', len(rendered)])          # numeric
    return {'name': 'Report',
            'blocks': [{'title': report_name, 'headers': ['Field', 'Value'], 'rows': pairs}]}


def special_sheets(rendered, report_name='Special Report', meta=None, letterhead=None):
    """(the rendered section list, report name, meta) -> ``sheets`` for
    ``write_sections_xlsx``. Pure + testable; mirrors the PDF/Word body.

    Sheet 1 'Report' is the cover (name / project / data date). Each subsequent
    sheet is one selected section, in order. Empty selection -> a single 'No data'
    sheet. Never raises."""
    report_name = report_name or 'Special Report'
    meta = meta or {}
    rendered = rendered or []
    cover = _cover_sheet(report_name, meta, rendered, letterhead)
    if not rendered:
        cover['blocks'].append({'title': 'Sections', 'headers': ['Result'],
                                'rows': [['No results selected. Pick results to build the report.']]})
        return [cover]
    sheets = [cover]
    for i, item in enumerate(rendered, 1):
        sheets.append(_section_sheet(i, item))
    return sheets


def build_excel(project_id=None, item_ids=None, report_name='Special Report', mode='light',
                meta=None, letterhead=None, inputs=None, snapshot_id=None, output_path=None):
    """Full pipeline mirroring ``assemble.build_word``: resolve project, build the
    parse-free context, render the selected items, and write the .xlsx to
    ``output_path``. DB is the read path (no XML re-parse for DB-backed features).
    Returns ``output_path``."""
    import db
    from p6_special import registry
    from p6_special.context import SpecialContext

    if not project_id and snapshot_id:
        project_id = db.get_project_id_for_snapshot(snapshot_id)
    ctx = SpecialContext(project_id, snapshot_id=snapshot_id, inputs=inputs or {},
                         mode=mode or 'light')
    rendered = registry.render(ctx, item_ids or [])
    m = dict(ctx.meta or {})
    if meta:
        m.update({k: v for k, v in meta.items() if v})
    sheets = special_sheets(rendered, report_name or 'Special Report', m, letterhead=letterhead)
    write_sections_xlsx(output_path, sheets)
    return output_path
