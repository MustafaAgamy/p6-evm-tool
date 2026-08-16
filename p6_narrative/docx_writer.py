"""Write a NarrativeDoc (dict) to an editable Word (.docx) file.

Everything lands as native, editable Word content — paragraphs and tables, no
flattened images — so the planner can change any word, number, row or cell in Word
and finish it on their letterhead. The rich visual charts live in the on-screen
view and the PDF; here each becomes an editable table (work-package → steps,
WBS → cost %, period → cumulative cost).
"""
import base64
import io

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt


def _img_bytes(data_url):
    """Decode a 'data:image/...;base64,XXXX' URL (or bare base64) to a BytesIO."""
    if not data_url:
        return None
    b64 = data_url.split(',', 1)[1] if ',' in data_url else data_url
    return io.BytesIO(base64.b64decode(b64))


def _add_table(doc, headers, rows):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = 'Table Grid'
    for i, head in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = str(head)
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = '' if val is None else str(val)
    return table


def _money(v):
    try:
        return f'{float(v):,.0f}'
    except (TypeError, ValueError):
        return str(v)


def _render(doc, section):
    kind, p = section['kind'], section['payload']
    if kind == 'prose':
        for para in p.get('paragraphs', []):
            doc.add_paragraph(para)
        for bullet in p.get('bullets', []):
            doc.add_paragraph(bullet, style='List Bullet')
    elif kind == 'keyvals':
        _add_table(doc, ['Field', 'Value'], [[r['k'], r['v']] for r in p.get('rows', [])])
    elif kind == 'table' and p.get('view') == 'calendars':
        _add_table(doc, ['Calendar', 'Working days', 'Shift', 'Assigned'],
                   [[c['name'], c['working_days'], c['shift'], c['activities']]
                    for c in p.get('calendars', [])])
        if p.get('holidays'):
            doc.add_paragraph('Holidays & shutdowns:')
            _add_table(doc, ['When', 'Name', 'Days'],
                       [[h.get('range'), h.get('name'), h.get('days')] for h in p['holidays']])
    elif kind == 'table':
        rows = p.get('rows', []) or [['—'] * max(len(p.get('columns', [])), 1)]
        _add_table(doc, p.get('columns', []) or ['—'], rows)
    elif kind == 'image':
        img = _img_bytes(p.get('image'))
        if img:
            try:
                doc.add_picture(img, width=Inches(6.0))
            except Exception:
                doc.add_paragraph('[project layout image]')
        else:
            doc.add_paragraph('[project layout — add it in project setup]')
    elif kind == 'scope':
        if p.get('intro'):
            doc.add_paragraph(p['intro'])
        for b in p.get('blocks', []):
            doc.add_heading(b.get('discipline', ''), level=2)
            doc.add_paragraph(b.get('paragraph', ''))
            for pkg in b.get('packages', []):
                run = doc.add_paragraph(style='List Bullet').add_run(pkg)
                run.bold = True
    elif kind == 'wbs':
        for n in p.get('nodes', []):
            prefix = ('    ' * n.get('level', 0)) + ('› ' if n.get('level') else '')
            doc.add_paragraph(prefix + (n.get('name') or '—'))
    elif kind == 'codes':
        for tbl in p.get('tables', []):
            doc.add_heading(tbl['dimension'], level=2)
            _add_table(doc, ['Code', 'Description'],
                       [[r.get('code'), r.get('description')] for r in tbl.get('rows', [])])
    elif kind == 'sequence':
        for para in p.get('paragraphs', []):
            doc.add_paragraph(para)
        for ch in p.get('charts', []):
            doc.add_heading(
                f"{ch['discipline']} — chart {ch.get('chart_index', 1)} of {ch.get('chart_count', 1)}",
                level=2)
            _add_table(doc, ['Work-package', 'Sequence of steps'],
                       [[pk['name'], ' → '.join(st['name'] for st in pk.get('steps', []))]
                        for pk in ch.get('packages', [])])
    elif kind == 'costbars':
        _add_table(doc, ['WBS branch', 'Cost', 'Share %'],
                   [[r['name'], _money(r['cost']), f"{r['pct']}%"] for r in p.get('rows', [])])
    elif kind == 'cashflow':
        _add_table(doc, ['Date', 'Cumulative cost', '% complete'],
                   [[pt['date'], _money(pt['cumulative']), f"{pt['pct']}%"]
                    for pt in p.get('points', [])])
    elif kind == 'timeline':
        _add_table(doc, ['Date', 'Key date / milestone'],
                   [[it.get('date'), it.get('label')] for it in p.get('items', [])])
    elif kind == 'value':
        _add_table(doc, ['Branch', 'Cost', 'Share %'],
                   [[r['name'], _money(r['cost']), f"{r['pct']}%"] for r in p.get('rows', [])])
        if p.get('total') is not None:
            doc.add_paragraph(f"Total: {_money(p['total'])}")
    elif kind == 'idanatomy':
        doc.add_paragraph(f"Example activity ID: {p.get('id', '')}")
        _add_table(doc, ['Part', 'Value'],
                   [[s.get('label'), s.get('value')] for s in p.get('segments', [])])


def _add_logo_header(document, logos):
    """Put the three party logos into the page header (repeats on every page)."""
    header = document.sections[0].header
    try:
        table = header.add_table(rows=1, cols=3, width=Inches(6.4))
    except Exception:
        return
    for i, key in enumerate(('owner', 'consultant', 'contractor')):
        cell = table.rows[0].cells[i]
        para = cell.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        img = _img_bytes(logos.get(key))
        if img:
            try:
                para.add_run().add_picture(img, width=Inches(1.6))
            except Exception:
                pass


def write_docx(doc_dict, path):
    meta = doc_dict.get('meta', {})
    document = Document()
    if meta.get('logos'):
        _add_logo_header(document, meta['logos'])
    document.add_heading(meta.get('project_name', 'Baseline Narrative'), level=0)
    sub = document.add_paragraph(
        f"Detailed Baseline Narrative · generated by nPace · data date {meta.get('data_date', '—')}")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for section in doc_dict.get('sections', []):
        document.add_heading(f"{section['number']}  {section['title']}", level=1)
        if section.get('note'):
            note = document.add_paragraph(section['note'])
            for run in note.runs:
                run.italic = True
                run.font.size = Pt(8)
        _render(document, section)

    document.save(path)
    return path
